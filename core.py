import os
import re
from pathlib import Path

BASE_DIR = Path(os.getenv("DATA_DIR", "paginas_geradas"))
BASE_DIR.mkdir(parents=True, exist_ok=True)

CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
)


def sanitize_folder_name(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip())
    cleaned = cleaned.strip("_")
    return cleaned or "pagina"


def build_browser_headers(url_base: str) -> dict:
    match = re.match(r"^(https?://[^/]+)", url_base.strip())
    origin = match.group(1) if match else ""
    return {
        "User-Agent": CHROME_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Origin": origin,
        "Referer": origin + "/" if origin else "",
    }


def open_file(path):
    # platform-aware open
    try:
        os.startfile(str(path))
    except Exception:
        # fallback for non-windows
        import webbrowser

        webbrowser.open(str(path))
