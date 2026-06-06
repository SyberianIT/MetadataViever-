"""
Графический интерфейс MetadataViewer (Tkinter).

Возможности:
  * превью изображений, поиск/фильтр, копирование в буфер;
  * экспорт в TXT и JSON, недавние файлы, перетаскивание (drag-and-drop);
  * светлая/тёмная тема, асинхронный подсчёт хешей.
"""

from __future__ import annotations

import json
import os
import threading

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import extractors

APP_TITLE = "MetadataViewer"
RECENT_PATH = os.path.join(os.path.expanduser("~"), ".metadataviewer_recent")
MAX_RECENT = 8

try:
    from PIL import Image, ImageTk

    _HAS_PIL = True
except ImportError:  # pragma: no cover
    _HAS_PIL = False


# Цветовые схемы тем.
THEMES = {
    "light": {
        "bg": "#f5f5f7", "fg": "#1d1d1f", "tree_bg": "#ffffff",
        "tree_fg": "#1d1d1f", "sel": "#0a84ff", "cat": "#e8e8ed",
        "status": "#e8e8ed", "preview": "#ffffff",
    },
    "dark": {
        "bg": "#1e1e1e", "fg": "#e0e0e0", "tree_bg": "#252526",
        "tree_fg": "#e0e0e0", "sel": "#0a84ff", "cat": "#333337",
        "status": "#2d2d30", "preview": "#252526",
    },
}


class MetadataViewerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.current_path: str | None = None
        self.categories: list[extractors.Category] = []
        self.theme_name = "dark"
        self._preview_img = None  # ссылка, чтобы GC не съел картинку
        self.recent = self._load_recent()

        root.title(APP_TITLE)
        root.geometry("1000x680")
        root.minsize(760, 480)

        self.style = ttk.Style()
        self._build_menu()
        self._build_toolbar()
        self._build_body()
        self._build_statusbar()
        self._apply_theme()
        self._setup_dnd()
        self._bind_keys()

    # --- Построение интерфейса ------------------------------------------
    def _build_menu(self):
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Открыть…  (Ctrl+O)", command=self.open_file)
        self.recent_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="Недавние файлы", menu=self.recent_menu)
        file_menu.add_separator()
        file_menu.add_command(label="Экспорт в TXT…", command=lambda: self.export("txt"))
        file_menu.add_command(label="Экспорт в JSON…", command=lambda: self.export("json"))
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self.root.quit)
        menubar.add_cascade(label="Файл", menu=file_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Светлая / тёмная тема  (Ctrl+T)", command=self.toggle_theme)
        view_menu.add_command(label="Развернуть всё", command=lambda: self._expand_all(True))
        view_menu.add_command(label="Свернуть всё", command=lambda: self._expand_all(False))
        view_menu.add_command(label="Обновить  (F5)", command=self.refresh)
        menubar.add_cascade(label="Вид", menu=view_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="О программе", command=self._about)
        menubar.add_cascade(label="Справка", menu=help_menu)

        self.root.config(menu=menubar)
        self._refresh_recent_menu()

    def _build_toolbar(self):
        bar = ttk.Frame(self.root, padding=(8, 6))
        bar.pack(fill=tk.X)

        ttk.Button(bar, text="📂 Открыть", command=self.open_file).pack(side=tk.LEFT)
        ttk.Button(bar, text="⟳ Обновить", command=self.refresh).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(bar, text="🌓 Тема", command=self.toggle_theme).pack(side=tk.LEFT, padx=(6, 0))

        ttk.Label(bar, text="Поиск:").pack(side=tk.LEFT, padx=(16, 4))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._apply_filter())
        entry = ttk.Entry(bar, textvariable=self.search_var, width=24)
        entry.pack(side=tk.LEFT)

        self.path_var = tk.StringVar(value="Файл не выбран — откройте или перетащите файл в окно")
        ttk.Label(bar, textvariable=self.path_var, anchor="e").pack(
            side=tk.RIGHT, fill=tk.X, expand=True, padx=(12, 0)
        )

    def _build_body(self):
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 6))

        # Левая панель: превью + краткая сводка
        left = ttk.Frame(paned, width=280)
        paned.add(left, weight=0)

        self.preview_label = tk.Label(left, text="\n\nНет превью", anchor="center")
        self.preview_label.pack(fill=tk.X, pady=(0, 8))

        self.summary = tk.Text(left, height=10, wrap="word", borderwidth=0, state="disabled")
        self.summary.pack(fill=tk.BOTH, expand=True)

        # Правая панель: дерево метаданных
        right = ttk.Frame(paned)
        paned.add(right, weight=1)

        self.tree = ttk.Treeview(right, columns=("value",), show="tree headings")
        self.tree.heading("#0", text="Свойство")
        self.tree.heading("value", text="Значение")
        self.tree.column("#0", width=240, anchor="w")
        self.tree.column("value", width=460, anchor="w")

        vsb = ttk.Scrollbar(right, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # Контекстное меню и копирование
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="Копировать значение", command=lambda: self._copy("value"))
        self.menu.add_command(label="Копировать свойство", command=lambda: self._copy("key"))
        self.menu.add_command(label="Копировать строку", command=lambda: self._copy("row"))
        self.tree.bind("<Button-3>", self._show_menu)
        self.tree.bind("<Double-1>", lambda e: self._copy("value"))

    def _build_statusbar(self):
        status = ttk.Frame(self.root)
        status.pack(side=tk.BOTTOM, fill=tk.X)

        self.status_var = tk.StringVar()
        ttk.Label(status, textvariable=self.status_var, anchor="w", padding=(8, 3)).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        mods = extractors.module_status()
        text = "  ".join(f"{n} {'✓' if ok else '✗'}" for n, ok in mods.items())
        ttk.Label(status, text=text, anchor="e", padding=(8, 3)).pack(side=tk.RIGHT)
        self._set_status("Готово")

    # --- Темы ------------------------------------------------------------
    def _apply_theme(self):
        t = THEMES[self.theme_name]
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.root.configure(bg=t["bg"])
        self.style.configure(".", background=t["bg"], foreground=t["fg"])
        self.style.configure("TFrame", background=t["bg"])
        self.style.configure("TLabel", background=t["bg"], foreground=t["fg"])
        self.style.configure("TButton", padding=4)
        self.style.configure(
            "Treeview", background=t["tree_bg"], fieldbackground=t["tree_bg"],
            foreground=t["tree_fg"], rowheight=24, borderwidth=0,
        )
        self.style.map("Treeview", background=[("selected", t["sel"])],
                       foreground=[("selected", "#ffffff")])
        self.style.configure("Treeview.Heading", background=t["cat"], foreground=t["fg"])
        self.tree.tag_configure("category", background=t["cat"],
                                font=("TkDefaultFont", 10, "bold"))
        self.preview_label.configure(bg=t["preview"], fg=t["fg"])
        self.summary.configure(bg=t["preview"], fg=t["fg"], insertbackground=t["fg"])

    def toggle_theme(self):
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self._apply_theme()

    # --- Загрузка файла --------------------------------------------------
    def load_file(self, path: str):
        if not os.path.isfile(path):
            messagebox.showerror("Ошибка", f"Файл не найден:\n{path}")
            return
        self.current_path = path
        self.path_var.set(path)
        self.root.title(f"{os.path.basename(path)} — {APP_TITLE}")
        self._add_recent(path)

        try:
            # Сначала без хешей — быстро показываем результат.
            self.categories = extractors.collect_metadata(path, include_hashes=False)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Ошибка", f"Не удалось прочитать метаданные:\n{exc}")
            return

        self._populate_tree()
        self._update_preview(path)
        self._update_summary()
        self._set_status(f"Загружено: {os.path.basename(path)}")
        self._compute_hashes_async(path)

    def _compute_hashes_async(self, path: str):
        """Хеши больших файлов считаем в фоне, не блокируя интерфейс."""
        self._set_status("Подсчёт контрольных сумм…")

        def worker():
            cat = extractors.get_hashes(path)
            if self.current_path == path:  # файл не сменили за время подсчёта
                self.root.after(0, lambda: self._add_hash_category(cat))

        threading.Thread(target=worker, daemon=True).start()

    def _add_hash_category(self, cat: extractors.Category):
        self.categories = [c for c in self.categories if c.name != cat.name]
        self.categories.append(cat)
        self._populate_tree()
        self._set_status("Готово")

    def _populate_tree(self):
        self.tree.delete(*self.tree.get_children())
        query = self.search_var.get().lower().strip()
        for cat in self.categories:
            rows = [
                (k, v) for k, v in cat.fields.items()
                if not query or query in k.lower() or query in str(v).lower()
            ]
            if not rows:
                continue
            parent = self.tree.insert("", tk.END, text=f"  {cat.name}", open=True,
                                      tags=("category",))
            for key, value in rows:
                self.tree.insert(parent, tk.END, text=f"  {key}", values=(str(value),))

    def _apply_filter(self):
        if self.categories:
            self._populate_tree()

    def _update_preview(self, path: str):
        self._preview_img = None
        if not _HAS_PIL:
            self.preview_label.configure(image="", text="\n\nНет превью\n(установите Pillow)")
            return
        try:
            with Image.open(path) as img:
                img = img.copy()
                img.thumbnail((260, 260))
                self._preview_img = ImageTk.PhotoImage(img)
                self.preview_label.configure(image=self._preview_img, text="")
                return
        except Exception:  # noqa: BLE001 — не изображение
            pass
        ext = os.path.splitext(path)[1].upper().lstrip(".") or "FILE"
        self.preview_label.configure(image="", text=f"\n\n[ {ext} ]\nнет превью")

    def _update_summary(self):
        fs = next((c for c in self.categories if c.name == "Файловая система"), None)
        self.summary.configure(state="normal")
        self.summary.delete("1.0", tk.END)
        if fs:
            for key in ("Имя файла", "Размер", "Тип (MIME)", "Тип (сигнатура)", "Изменён"):
                if key in fs.fields:
                    self.summary.insert(tk.END, f"{key}:\n  {fs.fields[key]}\n\n")
        self.summary.configure(state="disabled")

    # --- Действия --------------------------------------------------------
    def open_file(self):
        path = filedialog.askopenfilename(title="Выберите файл")
        if path:
            self.load_file(path)

    def refresh(self):
        if self.current_path:
            self.load_file(self.current_path)

    def _expand_all(self, expand: bool):
        for item in self.tree.get_children():
            self.tree.item(item, open=expand)

    def export(self, fmt: str):
        if not self.current_path:
            messagebox.showinfo("Информация", "Сначала откройте файл.")
            return
        cats = extractors.collect_metadata(self.current_path)
        if fmt == "json":
            out = filedialog.asksaveasfilename(defaultextension=".json",
                                               filetypes=[("JSON", "*.json")])
            if not out:
                return
            data = {"file": self.current_path,
                    "metadata": {c.name: {k: str(v) for k, v in c.fields.items()} for c in cats}}
            with open(out, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
        else:
            out = filedialog.asksaveasfilename(defaultextension=".txt",
                                               filetypes=[("Текст", "*.txt")])
            if not out:
                return
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(f"Метаданные файла: {self.current_path}\n{'=' * 60}\n\n")
                for c in cats:
                    fh.write(f"[{c.name}]\n")
                    for k, v in c.fields.items():
                        fh.write(f"  {k}: {v}\n")
                    fh.write("\n")
        self._set_status(f"Отчёт сохранён: {out}")
        messagebox.showinfo("Готово", f"Отчёт сохранён:\n{out}")

    # --- Копирование / контекстное меню ----------------------------------
    def _show_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.menu.tk_popup(event.x_root, event.y_root)

    def _copy(self, what: str):
        sel = self.tree.selection()
        if not sel:
            return
        key = self.tree.item(sel[0], "text").strip()
        values = self.tree.item(sel[0], "values")
        value = values[0] if values else ""
        text = {"key": key, "value": value, "row": f"{key}: {value}"}[what]
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._set_status("Скопировано в буфер обмена")

    # --- Недавние файлы --------------------------------------------------
    def _load_recent(self) -> list[str]:
        try:
            with open(RECENT_PATH, encoding="utf-8") as fh:
                return [ln.strip() for ln in fh if ln.strip() and os.path.isfile(ln.strip())]
        except OSError:
            return []

    def _add_recent(self, path: str):
        path = os.path.abspath(path)
        self.recent = [path] + [p for p in self.recent if p != path]
        self.recent = self.recent[:MAX_RECENT]
        try:
            with open(RECENT_PATH, "w", encoding="utf-8") as fh:
                fh.write("\n".join(self.recent))
        except OSError:
            pass
        self._refresh_recent_menu()

    def _refresh_recent_menu(self):
        self.recent_menu.delete(0, tk.END)
        if not self.recent:
            self.recent_menu.add_command(label="(пусто)", state="disabled")
            return
        for path in self.recent:
            self.recent_menu.add_command(
                label=os.path.basename(path), command=lambda p=path: self.load_file(p)
            )

    # --- Прочее ----------------------------------------------------------
    def _set_status(self, text: str):
        self.status_var.set(text)

    def _bind_keys(self):
        self.root.bind("<Control-o>", lambda e: self.open_file())
        self.root.bind("<Control-t>", lambda e: self.toggle_theme())
        self.root.bind("<F5>", lambda e: self.refresh())
        self.root.bind("<Control-c>", lambda e: self._copy("value"))

    def _setup_dnd(self):
        try:
            self.root.drop_target_register("DND_Files")  # type: ignore[attr-defined]
            self.root.dnd_bind("<<Drop>>", self._on_drop)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass

    def _on_drop(self, event):
        path = event.data.strip().strip("{}")
        if os.path.isfile(path):
            self.load_file(path)

    def _about(self):
        messagebox.showinfo(
            "О программе",
            f"{APP_TITLE}\n\n"
            "Просмотр метаданных файлов с графическим интерфейсом.\n"
            "Изображения (EXIF/GPS), аудио, PDF, текст, контрольные суммы.\n\n"
            "Python + Tkinter",
        )


def run(initial_file: str | None = None):
    try:
        from tkinterdnd2 import TkinterDnD

        root = TkinterDnD.Tk()
    except ImportError:
        root = tk.Tk()

    app = MetadataViewerApp(root)
    if initial_file and os.path.isfile(initial_file):
        app.load_file(initial_file)
    root.mainloop()
