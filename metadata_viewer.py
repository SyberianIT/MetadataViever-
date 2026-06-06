#!/usr/bin/env python3
"""
MetadataViewer — программа для просмотра метаданных файлов с графическим интерфейсом.

Поддерживает:
  * Базовые метаданные файловой системы (размер, даты, права доступа) — всегда.
  * EXIF и свойства изображений              — при наличии Pillow.
  * Теги аудио (MP3, FLAC, OGG, M4A и др.)   — при наличии mutagen.
  * Метаданные PDF                            — при наличии pypdf.

Запуск:
    python3 metadata_viewer.py [путь_к_файлу]
"""

import datetime as _dt
import hashlib
import os
import stat
import sys
import mimetypes

import tkinter as tk
from tkinter import filedialog, ttk, messagebox

# --- Необязательные зависимости (программа работает и без них) ---------------
try:
    from PIL import Image, ExifTags

    _HAS_PIL = True
except ImportError:  # pragma: no cover
    _HAS_PIL = False

try:
    import mutagen

    _HAS_MUTAGEN = True
except ImportError:  # pragma: no cover
    _HAS_MUTAGEN = False

try:
    from pypdf import PdfReader

    _HAS_PYPDF = True
except ImportError:  # pragma: no cover
    _HAS_PYPDF = False


APP_TITLE = "MetadataViewer — просмотр метаданных файлов"


# ---------------------------------------------------------------------------
# Извлечение метаданных
# ---------------------------------------------------------------------------
def _human_size(num_bytes):
    """Преобразует размер в байтах в читаемый вид."""
    size = float(num_bytes)
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if size < 1024.0:
            return f"{size:.0f} {unit}" if unit == "Б" else f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} ПБ"


def _fmt_time(timestamp):
    return _dt.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def get_filesystem_metadata(path):
    """Базовые метаданные, доступные всегда из файловой системы."""
    st = os.stat(path)
    mime, _ = mimetypes.guess_type(path)
    data = {
        "Имя файла": os.path.basename(path),
        "Полный путь": os.path.abspath(path),
        "Размер": f"{_human_size(st.st_size)} ({st.st_size} байт)",
        "Тип (MIME)": mime or "неизвестно",
        "Создан": _fmt_time(st.st_ctime),
        "Изменён": _fmt_time(st.st_mtime),
        "Открыт": _fmt_time(st.st_atime),
        "Права доступа": stat.filemode(st.st_mode),
        "Владелец (UID)": st.st_uid,
        "Группа (GID)": st.st_gid,
    }
    return data


def get_hashes(path, chunk_size=1 << 20):
    """Контрольные суммы MD5 и SHA-256."""
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(chunk_size), b""):
                md5.update(chunk)
                sha256.update(chunk)
    except OSError as exc:
        return {"Ошибка чтения": str(exc)}
    return {"MD5": md5.hexdigest(), "SHA-256": sha256.hexdigest()}


def get_image_metadata(path):
    """EXIF и свойства изображения (требует Pillow)."""
    if not _HAS_PIL:
        return None
    try:
        with Image.open(path) as img:
            data = {
                "Формат": img.format,
                "Режим": img.mode,
                "Ширина": img.width,
                "Высота": img.height,
            }
            info_dpi = img.info.get("dpi")
            if info_dpi:
                data["DPI"] = f"{info_dpi[0]} x {info_dpi[1]}"

            exif = img.getexif()
            if exif:
                for tag_id, value in exif.items():
                    tag = ExifTags.TAGS.get(tag_id, tag_id)
                    if isinstance(value, bytes):
                        value = value.decode(errors="replace")
                    data[f"EXIF: {tag}"] = value
            return data
    except Exception as exc:  # noqa: BLE001
        return {"Ошибка обработки изображения": str(exc)}


def get_audio_metadata(path):
    """Теги аудио (требует mutagen)."""
    if not _HAS_MUTAGEN:
        return None
    try:
        audio = mutagen.File(path, easy=True)
        if audio is None:
            return None
        data = {}
        if getattr(audio, "info", None) is not None:
            info = audio.info
            if hasattr(info, "length"):
                data["Длительность"] = f"{info.length:.1f} c"
            if hasattr(info, "bitrate"):
                data["Битрейт"] = f"{info.bitrate // 1000} кбит/с"
            if hasattr(info, "sample_rate"):
                data["Частота дискретизации"] = f"{info.sample_rate} Гц"
            if hasattr(info, "channels"):
                data["Каналы"] = info.channels
        for key, value in audio.items():
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value)
            data[f"Тег: {key}"] = value
        return data or None
    except Exception as exc:  # noqa: BLE001
        return {"Ошибка обработки аудио": str(exc)}


def get_pdf_metadata(path):
    """Метаданные PDF (требует pypdf)."""
    if not _HAS_PYPDF or not path.lower().endswith(".pdf"):
        return None
    try:
        reader = PdfReader(path)
        data = {"Количество страниц": len(reader.pages)}
        if reader.metadata:
            for key, value in reader.metadata.items():
                clean_key = key[1:] if key.startswith("/") else key
                data[f"PDF: {clean_key}"] = value
        return data
    except Exception as exc:  # noqa: BLE001
        return {"Ошибка обработки PDF": str(exc)}


def collect_metadata(path):
    """Собирает все доступные метаданные в виде словаря категорий."""
    categories = {"Файловая система": get_filesystem_metadata(path)}

    for label, func in (
        ("Изображение", get_image_metadata),
        ("Аудио", get_audio_metadata),
        ("PDF-документ", get_pdf_metadata),
    ):
        result = func(path)
        if result:
            categories[label] = result

    categories["Контрольные суммы"] = get_hashes(path)
    return categories


# ---------------------------------------------------------------------------
# Графический интерфейс
# ---------------------------------------------------------------------------
class MetadataViewerApp(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)
        self.master = master
        self.current_path = None
        self.pack(fill=tk.BOTH, expand=True)
        self._build_ui()

    def _build_ui(self):
        # Верхняя панель с кнопками
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, pady=(0, 8))

        ttk.Button(toolbar, text="Открыть файл…", command=self.open_file).pack(
            side=tk.LEFT
        )
        ttk.Button(toolbar, text="Обновить", command=self.refresh).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        ttk.Button(toolbar, text="Сохранить отчёт…", command=self.export_report).pack(
            side=tk.LEFT, padx=(6, 0)
        )

        self.path_var = tk.StringVar(value="Файл не выбран")
        ttk.Label(toolbar, textvariable=self.path_var, anchor="w").pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 0)
        )

        # Таблица метаданных (дерево с категориями)
        columns = ("value",)
        self.tree = ttk.Treeview(self, columns=columns, show="tree headings")
        self.tree.heading("#0", text="Свойство")
        self.tree.heading("value", text="Значение")
        self.tree.column("#0", width=260, anchor="w")
        self.tree.column("value", width=520, anchor="w")

        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # Поддержка drag-and-drop, если доступна
        self._setup_dnd()

        # Статусная строка
        self.status_var = tk.StringVar()
        self._update_status()
        status = ttk.Label(
            self.master, textvariable=self.status_var, relief=tk.SUNKEN, anchor="w"
        )
        status.pack(side=tk.BOTTOM, fill=tk.X)

    def _setup_dnd(self):
        try:
            self.tree.drop_target_register("DND_Files")  # type: ignore[attr-defined]
            self.tree.dnd_bind("<<Drop>>", self._on_drop)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass  # tkinterdnd2 не установлен — просто пропускаем

    def _on_drop(self, event):
        path = event.data.strip().strip("{}")
        if os.path.isfile(path):
            self.load_file(path)

    def _update_status(self):
        available = []
        available.append("Pillow ✓" if _HAS_PIL else "Pillow ✗")
        available.append("mutagen ✓" if _HAS_MUTAGEN else "mutagen ✗")
        available.append("pypdf ✓" if _HAS_PYPDF else "pypdf ✗")
        self.status_var.set("Модули: " + "   ".join(available))

    # --- Действия --------------------------------------------------------
    def open_file(self):
        path = filedialog.askopenfilename(title="Выберите файл")
        if path:
            self.load_file(path)

    def refresh(self):
        if self.current_path:
            self.load_file(self.current_path)

    def load_file(self, path):
        if not os.path.isfile(path):
            messagebox.showerror("Ошибка", f"Файл не найден:\n{path}")
            return
        self.current_path = path
        self.path_var.set(path)
        self.master.title(f"{os.path.basename(path)} — {APP_TITLE}")

        # Очистка дерева
        for item in self.tree.get_children():
            self.tree.delete(item)

        try:
            categories = collect_metadata(path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Ошибка", f"Не удалось прочитать метаданные:\n{exc}")
            return

        for category, fields in categories.items():
            parent = self.tree.insert("", tk.END, text=category, open=True)
            for key, value in fields.items():
                self.tree.insert(parent, tk.END, text=key, values=(str(value),))

    def export_report(self):
        if not self.current_path:
            messagebox.showinfo("Информация", "Сначала откройте файл.")
            return
        out_path = filedialog.asksaveasfilename(
            title="Сохранить отчёт",
            defaultextension=".txt",
            filetypes=[("Текстовый файл", "*.txt"), ("Все файлы", "*.*")],
        )
        if not out_path:
            return
        try:
            categories = collect_metadata(self.current_path)
            with open(out_path, "w", encoding="utf-8") as fh:
                fh.write(f"Метаданные файла: {self.current_path}\n")
                fh.write("=" * 60 + "\n\n")
                for category, fields in categories.items():
                    fh.write(f"[{category}]\n")
                    for key, value in fields.items():
                        fh.write(f"  {key}: {value}\n")
                    fh.write("\n")
            messagebox.showinfo("Готово", f"Отчёт сохранён:\n{out_path}")
        except OSError as exc:
            messagebox.showerror("Ошибка", f"Не удалось сохранить отчёт:\n{exc}")


def main():
    # tkinterdnd2 даёт поддержку перетаскивания файлов, если установлен
    try:
        from tkinterdnd2 import TkinterDnD

        root = TkinterDnD.Tk()
    except ImportError:
        root = tk.Tk()

    root.title(APP_TITLE)
    root.geometry("860x600")
    root.minsize(640, 400)

    app = MetadataViewerApp(root)

    # Файл из аргументов командной строки
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        app.load_file(sys.argv[1])

    root.mainloop()


if __name__ == "__main__":
    main()
