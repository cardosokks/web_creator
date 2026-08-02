from flask import Flask, render_template, request, jsonify, send_from_directory, abort
from pathlib import Path
from datetime import datetime
import requests
import shutil
import os
import json
import threading
import queue
import time
import uuid

from core import BASE_DIR, sanitize_folder_name, build_browser_headers

app = Flask(__name__, template_folder="templates", static_folder="static")

# Jobs
JOBS_DIR = BASE_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)
FINISHED_JOBS_DIR = JOBS_DIR / "finished"
FINISHED_JOBS_DIR.mkdir(parents=True, exist_ok=True)
job_queue = queue.Queue()


def _job_path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def _write_job(job: dict):
    p = _job_path(job["id"])
    p.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")


def _read_job(job_id: str) -> dict:
    # Check active jobs first, then finished jobs
    active_path = _job_path(job_id)
    finished_path = FINISHED_JOBS_DIR / f"{job_id}.json"
    if active_path.exists():
        return json.loads(active_path.read_text(encoding="utf-8"))
    if finished_path.exists():
        return json.loads(finished_path.read_text(encoding="utf-8"))
    return None


def _unique_folder_path(base_name: str) -> Path:
    base = sanitize_folder_name(base_name) if base_name else "projeto"
    candidate = BASE_DIR / base
    if not candidate.exists():
        return candidate

    suffix = 2
    while True:
        candidate = BASE_DIR / f"{base}_{suffix}"
        if not candidate.exists():
            return candidate
        suffix += 1


def _write_generation_log(folder_path: Path, *, source: str, url: str, query: str, page_name: str, folder_name: str, job_id: str = None, html: str = ""):
    payload = {
        "source": source,
        "url": url,
        "query": query,
        "page_name": page_name,
        "requested_folder_name": folder_name,
        "folder_name": folder_path.name,
        "job_id": job_id,
        "created_at": int(time.time()),
        "html_size": len(html or ""),
    }
    (folder_path / "log.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_and_queue_existing_jobs():
    """
    On startup, find any jobs that were 'queued' or 'running' and
    re-queue them for processing. This handles server restarts.
    """
    print(">>> Loading and re-queuing existing jobs...")
    for f in JOBS_DIR.glob("*.json"):
        try:
            job = json.loads(f.read_text(encoding="utf-8"))
            if job.get("status") in ("queued", "running"):
                job_queue.put(job)
                print(f"    - Re-queued job {job['id']}")
        except Exception as e:
            print(f"    - Could not load job file {f.name}: {e}")


def _worker():
    while True:
        job = job_queue.get()
        if not job:
            time.sleep(0.1)
            continue
        job_id = job["id"]
        try:
            job["status"] = "running"
            job["started_at"] = int(time.time())
            _write_job(job)

            session = requests.Session()
            resp = session.get(job["url"], params={"query": job.get("query", "")}, headers=build_browser_headers(job["url"]), timeout=(30, 600))
            resp.raise_for_status()
            html = (resp.text or "").strip()
            is_html = html.lower().lstrip().startswith(('<!doctype html', '<html'))
            if not html or not is_html:
                raise ValueError(f"Webhook returned invalid or empty HTML. Response: {html[:200]}")

            if job.get("folder_name"):
                base = sanitize_folder_name(job.get("folder_name"))
            elif job.get("page_name"):
                base = sanitize_folder_name(job.get("page_name"))
            else:
                base = "projeto"

            folder_path = _unique_folder_path(base)
            folder_path.mkdir(parents=True, exist_ok=False)
            (folder_path / "index.html").write_text(html, encoding="utf-8")
            _write_generation_log(
                folder_path,
                source="job_queue",
                url=job["url"],
                query=job.get("query", ""),
                page_name=job.get("page_name", ""),
                folder_name=job.get("folder_name", ""),
                job_id=job_id,
                html=html,
            )

            job["status"] = "success"
            job["folder"] = folder_path.name
            job["finished_at"] = int(time.time())
        except Exception as e:
            job["status"] = "failed"
            job["error"] = str(e)
            job["finished_at"] = int(time.time())
        finally:
            _write_job(job)  # Write the final state (success or failed)
            # Move finished/failed job to the archive directory
            try:
                shutil.move(_job_path(job_id), FINISHED_JOBS_DIR / f"{job_id}.json")
            except Exception as move_error:
                print(f"Error moving job {job_id} to finished folder: {move_error}")
            job_queue.task_done()


# start worker thread
_load_and_queue_existing_jobs()
threading.Thread(target=_worker, daemon=True).start()


def safe_folder_path(name: str) -> Path:
    p = (BASE_DIR / name).resolve()
    try:
        p.relative_to(BASE_DIR.resolve())
    except ValueError:
        raise ValueError("Invalid path")
    return p


@app.route("/")
def index():
    return render_template(
        "index.html", default_webhook_url=os.getenv("DEFAULT_WEBHOOK_URL", "http://krokante:9090/webhook/generate_page")
    )


@app.route("/api/jobs", methods=["GET", "POST"])
def api_jobs():
    if request.method == "POST":
        data = request.json or {}
        url_base = data.get("url")
        query = data.get("query")
        page_name = data.get("page_name")
        folder_field = data.get("folder_name")

        if not url_base or not query:
            return jsonify({"error": "url and query are required"}), 400

        job_id = uuid.uuid4().hex
        job = {
            "id": job_id,
            "url": url_base,
            "query": query,
            "page_name": page_name,
            "folder_name": folder_field,
            "status": "queued",
            "created_at": int(time.time()),
        }
        _write_job(job)
        job_queue.put(job)
        return jsonify({"ok": True, "job": job}), 201

    # GET: list jobs
    status_filter = (request.args.get("status") or "active").strip().lower()
    
    # Active jobs are read from the main jobs directory
    jobs = []
    for f in JOBS_DIR.glob("*.json"):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
            if j.get("status") in ("queued", "running"):
                jobs.append(j)
        except Exception:
            continue

    jobs.sort(key=lambda x: x.get("created_at", 0), reverse=True)
    return jsonify(jobs)


@app.route("/api/job/<job_id>")
def api_job(job_id):
    j = _read_job(job_id)
    if not j:
        return jsonify({"error": "not found"}), 404
    return jsonify(j)


@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.json or {}
    url_base = data.get("url")
    query = data.get("query")
    page_name = data.get("page_name")
    folder_field = data.get("folder_name")

    if not url_base or not query:
        return jsonify({"error": "url and query are required"}), 400

    try:
        session = requests.Session()
        response = session.get(
            url_base,
            params={"query": query},
            headers=build_browser_headers(url_base),
            timeout=(30, 240),
        )
        response.raise_for_status()
        html = response.text or ""
        if not html.strip():
            return jsonify({"error": "webhook returned no HTML"}), 500

        if folder_field:
            base = sanitize_folder_name(folder_field)
        elif page_name:
            base = sanitize_folder_name(page_name)
        else:
            base = "projeto"

        folder_path = _unique_folder_path(base)
        folder_path.mkdir(parents=True, exist_ok=False)
        (folder_path / "index.html").write_text(html, encoding="utf-8")
        _write_generation_log(
            folder_path,
            source="api_generate",
            url=url_base,
            query=query,
            page_name=page_name or "",
            folder_name=folder_field or "",
            html=html,
        )

        return jsonify({"ok": True, "folder": folder_path.name})
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/pages")
def api_pages():
    pages = []
    for folder in BASE_DIR.iterdir():
        if not folder.is_dir():
            continue
        index = folder / "index.html"
        if not index.exists():
            continue
        stat = folder.stat()
        pages.append({
            "name": folder.name,
            "modified": int(stat.st_mtime),
        })
    pages.sort(key=lambda x: x["modified"], reverse=True)
    return jsonify(pages)


@app.route("/site/<folder>/<path:filename>")
def site_files(folder, filename):
    try:
        folder_path = safe_folder_path(folder)
    except Exception:
        abort(404)
    return send_from_directory(folder_path, filename)


@app.route("/api/delete", methods=["POST"])
def api_delete():
    data = request.json or {}
    name = data.get("name")
    if not name:
        return jsonify({"error": "name required"}), 400
    try:
        path = safe_folder_path(name)
        shutil.rmtree(path)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/rename", methods=["POST"])
def api_rename():
    data = request.json or {}
    current = data.get("current")
    new_name = data.get("new_name")
    if not current or not new_name:
        return jsonify({"error": "current and new_name required"}), 400
    try:
        cur_path = safe_folder_path(current)
        safe_new = sanitize_folder_name(new_name)
        target = BASE_DIR / safe_new
        if target.exists():
            return jsonify({"error": "target exists"}), 400
        cur_path.rename(target)
        return jsonify({"ok": True, "name": target.name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print("=" * 50)
    print(">>> Servidor de Páginas Iniciado <<<")
    print(f">>> Acesse o painel em: http://127.0.0.1:{port}")
    print("=" * 50)
    app.run(
        host="0.0.0.0",
        port=port,
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )
