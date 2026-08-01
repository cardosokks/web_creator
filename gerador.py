import os
import json
import re
import shutil
import threading
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, simpledialog
import tkinter as tk
from tkinter import ttk

import requests


BASE_DIR = Path(os.getenv("DATA_DIR", "paginas_geradas"))
BASE_DIR.mkdir(parents=True, exist_ok=True)

CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
)


def sanitize_folder_name(value):
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip())
    cleaned = cleaned.strip("_")
    return cleaned or "pagina"


def open_file(path):
    os.startfile(str(path))


def build_browser_headers(url_base):
    origin = re.sub(r"^(https?://[^/]+).*$", r"\1", url_base.strip())
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
        "Referer": origin + "/",
    }


def unique_folder_path(base_name):
    base = sanitize_folder_name(base_name) if base_name else "pagina"
    candidate = BASE_DIR / base
    if not candidate.exists():
        return candidate

    suffix = 2
    while True:
        candidate = BASE_DIR / f"{base}_{suffix}"
        if not candidate.exists():
            return candidate
        suffix += 1


def write_generation_log(folder_path, *, url, query, page_name, html_content):
    payload = {
        "source": "desktop_app",
        "url": url,
        "query": query,
        "page_name": page_name,
        "folder_name": folder_path.name,
        "created_at": int(datetime.now().timestamp()),
        "html_size": len(html_content),
    }
    (folder_path / "log.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class ScrollableFrame(ttk.Frame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.content = ttk.Frame(self.canvas)

        self.content.bind(
            "<Configure>",
            lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )

        self.canvas_window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.canvas.bind(
            "<Configure>",
            lambda event: self.canvas.itemconfigure(self.canvas_window, width=event.width),
        )

        self.content.bind_all("<MouseWheel>", self._on_mousewheel, add="+")

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Gerenciador de Páginas")
        self.geometry("980x720")
        self.minsize(900, 650)
        self.configure(padx=16, pady=16)

        self.page_cards = {}
        self._setup_style()
        self.setup_ui()
        self.refresh_pages()

    def _setup_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("Header.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("SubHeader.TLabel", font=("Segoe UI", 10), foreground="#4b5563")
        style.configure("Card.TFrame", background="#f8fafc", relief="solid", borderwidth=1)
        style.configure("CardTitle.TLabel", font=("Segoe UI", 11, "bold"), background="#f8fafc")
        style.configure("CardMeta.TLabel", font=("Segoe UI", 9), background="#f8fafc", foreground="#475569")
        style.configure("Primary.TButton", padding=(12, 8))
        style.configure("Action.TButton", padding=(10, 6))

    def setup_ui(self):
        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True)

        top_bar = ttk.Frame(container)
        top_bar.pack(fill=tk.X, pady=(0, 14))

        ttk.Label(top_bar, text="Gerenciador de Páginas", style="Header.TLabel").pack(anchor=tk.W)
        ttk.Label(
            top_bar,
            text="Gera páginas via webhook, salva cada uma em uma pasta própria e permite abrir o index, renomear ou excluir.",
            style="SubHeader.TLabel",
        ).pack(anchor=tk.W, pady=(2, 0))

        generate_frame = ttk.LabelFrame(container, text="Gerar nova página", padding=12)
        generate_frame.pack(fill=tk.X, pady=(0, 14))

        generate_frame.columnconfigure(1, weight=1)

        ttk.Label(generate_frame, text="URL do webhook:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.url_entry = ttk.Entry(generate_frame)
        self.url_entry.insert(0, "http://krokante:88/webhook/generate_page")
        self.url_entry.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=5)

        ttk.Label(generate_frame, text="Prompt / query:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.query_entry = ttk.Entry(generate_frame)
        self.query_entry.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=5)

        ttk.Label(generate_frame, text="Nome da página:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.name_entry = ttk.Entry(generate_frame)
        self.name_entry.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=5)

        button_row = ttk.Frame(generate_frame)
        button_row.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(10, 0))

        self.btn_generate = ttk.Button(button_row, text="Gerar página", style="Primary.TButton", command=self.generate_page)
        self.btn_generate.pack(side=tk.LEFT)

        self.btn_refresh = ttk.Button(button_row, text="Atualizar lista", style="Action.TButton", command=self.refresh_pages)
        self.btn_refresh.pack(side=tk.LEFT, padx=(10, 0))

        list_header = ttk.Frame(container)
        list_header.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(list_header, text="Páginas salvas", style="Header.TLabel").pack(anchor=tk.W)
        self.count_label = ttk.Label(list_header, text="0 páginas", style="SubHeader.TLabel")
        self.count_label.pack(anchor=tk.W)
        self.status_label = ttk.Label(list_header, text="Pronto para gerar uma página.", style="SubHeader.TLabel")
        self.status_label.pack(anchor=tk.W, pady=(2, 0))

        self.scrollable = ScrollableFrame(container)
        self.scrollable.pack(fill=tk.BOTH, expand=True)

    def generate_page(self):
        url_base = self.url_entry.get().strip()
        query = self.query_entry.get().strip()
        page_name = self.name_entry.get().strip()

        if not url_base or not query:
            messagebox.showwarning("Aviso", "Preencha a URL e a query.")
            return

        self.btn_generate.config(state=tk.DISABLED, text="Aguardando HTML...")
        self.status_label.config(text="Enviando a query para o webhook e aguardando o HTML...")

        threading.Thread(
            target=self._process_generation,
            args=(url_base, query, page_name),
            daemon=True,
        ).start()

    def _process_generation(self, url_base, query, page_name):
        try:
            session = requests.Session()
            response = session.get(
                url_base,
                params={"query": query},
                headers=build_browser_headers(url_base),
                timeout=(30, 240),
            )
            response.raise_for_status()

            html_content = response.text.strip()
            if not html_content:
                raise ValueError("O webhook respondeu sem conteúdo HTML.")

            if "quota" in html_content.lower():
                raise ValueError("O webhook devolveu uma mensagem de quota em vez do HTML.")

            folder_base = sanitize_folder_name(page_name) if page_name else "projeto"
            folder_path = unique_folder_path(folder_base)
            folder_path.mkdir(parents=True, exist_ok=False)

            index_path = folder_path / "index.html"
            index_path.write_text(html_content, encoding="utf-8")
            write_generation_log(
                folder_path,
                url=url_base,
                query=query,
                page_name=page_name,
                html_content=html_content,
            )

            self.after(0, lambda: self._finish_generation_success(folder_path.name))

        except requests.exceptions.RequestException as exc:
            self.after(0, lambda: messagebox.showerror("Erro de conexão", f"Falha ao contatar o webhook:\n{exc}"))
            self.after(0, lambda: self.status_label.config(text="Falha ao obter a página do webhook."))
        except Exception as exc:
            self.after(0, lambda: messagebox.showerror("Erro", f"Ocorreu um erro inesperado:\n{exc}"))
            self.after(0, lambda: self.status_label.config(text="Falha ao gerar a página."))
        finally:
            self.after(0, lambda: self.btn_generate.config(state=tk.NORMAL, text="Gerar página"))

    def _finish_generation_success(self, folder_name):
        self.query_entry.delete(0, tk.END)
        self.name_entry.delete(0, tk.END)
        self.refresh_pages()
        self.status_label.config(text=f"Página criada em {folder_name}.")
        messagebox.showinfo("Sucesso", f"Página criada em {folder_name}.")

    def refresh_pages(self):
        for widget in self.scrollable.content.winfo_children():
            widget.destroy()

        pages = self._load_pages()
        self.page_cards.clear()
        self.count_label.config(text=f"{len(pages)} página(s)")

        if not pages:
            empty = ttk.Label(
                self.scrollable.content,
                text="Nenhuma página salva ainda. Gere a primeira página acima.",
                style="SubHeader.TLabel",
            )
            empty.pack(anchor=tk.W, pady=16)
            return

        for page in pages:
            self._create_page_card(page)

    def _load_pages(self):
        pages = []
        for folder in BASE_DIR.iterdir():
            if not folder.is_dir():
                continue

            index_path = folder / "index.html"
            if not index_path.exists():
                continue

            stat = folder.stat()
            pages.append(
                {
                    "name": folder.name,
                    "path": folder,
                    "index": index_path,
                    "modified": datetime.fromtimestamp(stat.st_mtime),
                }
            )

        pages.sort(key=lambda item: item["modified"], reverse=True)
        return pages

    def _create_page_card(self, page):
        card = ttk.Frame(self.scrollable.content, style="Card.TFrame", padding=12)
        card.pack(fill=tk.X, pady=8)

        top_row = ttk.Frame(card)
        top_row.pack(fill=tk.X)

        ttk.Label(top_row, text=page["name"], style="CardTitle.TLabel").pack(anchor=tk.W)
        ttk.Label(top_row, text=str(page["path"]), style="CardMeta.TLabel").pack(anchor=tk.W, pady=(2, 0))
        ttk.Label(
            top_row,
            text=f"Atualizada em {page['modified'].strftime('%d/%m/%Y %H:%M:%S')}",
            style="CardMeta.TLabel",
        ).pack(anchor=tk.W, pady=(2, 0))

        action_row = ttk.Frame(card)
        action_row.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(
            action_row,
            text="Abrir index",
            style="Primary.TButton",
            command=lambda index_path=page["index"]: self.open_index(index_path),
        ).pack(side=tk.LEFT)

        ttk.Button(
            action_row,
            text="Renomear",
            style="Action.TButton",
            command=lambda current_path=page["path"]: self.rename_page(current_path),
        ).pack(side=tk.LEFT, padx=(10, 0))

        ttk.Button(
            action_row,
            text="Excluir",
            style="Action.TButton",
            command=lambda current_path=page["path"]: self.delete_page(current_path),
        ).pack(side=tk.LEFT, padx=(10, 0))

        self.page_cards[page["name"]] = card

    def open_index(self, index_path):
        if not index_path.exists():
            messagebox.showerror("Erro", "O arquivo index.html não foi encontrado.")
            return

        try:
            open_file(index_path)
        except OSError as exc:
            messagebox.showerror("Erro", f"Não foi possível abrir o arquivo:\n{exc}")

    def rename_page(self, current_path):
        new_name = simpledialog.askstring(
            "Renomear página",
            "Digite o novo nome da página:",
            initialvalue=current_path.name,
            parent=self,
        )

        if not new_name:
            return

        safe_name = sanitize_folder_name(new_name)
        if not safe_name:
            messagebox.showwarning("Aviso", "Informe um nome válido.")
            return

        target_path = BASE_DIR / safe_name
        if target_path.exists():
            messagebox.showwarning("Aviso", "Já existe uma página com esse nome.")
            return

        try:
            current_path.rename(target_path)
            self.refresh_pages()
        except OSError as exc:
            messagebox.showerror("Erro", f"Não foi possível renomear a página:\n{exc}")

    def delete_page(self, current_path):
        confirm = messagebox.askyesno(
            "Excluir página",
            f"Tem certeza que deseja excluir {current_path.name}?\nEssa ação não pode ser desfeita.",
        )

        if not confirm:
            return

        try:
            shutil.rmtree(current_path)
            self.refresh_pages()
        except OSError as exc:
            messagebox.showerror("Erro", f"Não foi possível excluir a página:\n{exc}")


if __name__ == "__main__":
    app = App()
    app.mainloop()