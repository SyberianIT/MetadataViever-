"""
Извлечение метаданных из файлов.

Модуль не зависит от GUI и полностью тестируется в headless-среде.
Сторонние библиотеки (Pillow, mutagen, pypdf, hachoir) подключаются
по возможности; без них доступны базовые метаданные и контрольные суммы.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import mimetypes
import os
import stat
import struct
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from typing import Callable, Optional

# --- Необязательные зависимости ---------------------------------------------
try:
    from PIL import Image, ExifTags

    HAS_PIL = True
except ImportError:  # pragma: no cover
    HAS_PIL = False

try:
    import mutagen

    HAS_MUTAGEN = True
except ImportError:  # pragma: no cover
    HAS_MUTAGEN = False

try:
    from pypdf import PdfReader

    HAS_PYPDF = True
except ImportError:  # pragma: no cover
    HAS_PYPDF = False


# Сигнатуры файлов (magic bytes) для определения типа без расширения.
_MAGIC_SIGNATURES = (
    (b"\xff\xd8\xff", "JPEG image"),
    (b"\x89PNG\r\n\x1a\n", "PNG image"),
    (b"GIF87a", "GIF image"),
    (b"GIF89a", "GIF image"),
    (b"BM", "BMP image"),
    (b"%PDF-", "PDF document"),
    (b"PK\x03\x04", "ZIP / Office Open XML"),
    (b"\x1f\x8b", "GZIP archive"),
    (b"7z\xbc\xaf\x27\x1c", "7-Zip archive"),
    (b"Rar!\x1a\x07", "RAR archive"),
    (b"\x00\x00\x00\x18ftyp", "MP4 / MOV video"),
    (b"\x1aE\xdf\xa3", "Matroska / WebM"),
    (b"ID3", "MP3 audio (ID3)"),
    (b"OggS", "OGG container"),
    (b"fLaC", "FLAC audio"),
    (b"RIFF", "RIFF (WAV/AVI)"),
    (b"\x7fELF", "ELF executable"),
    (b"MZ", "Windows executable"),
)


@dataclass
class Category:
    """Группа метаданных, отображаемая отдельной веткой в дереве."""

    name: str
    fields: dict = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.fields)


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------
def human_size(num_bytes: int) -> str:
    """Размер в байтах -> читаемая строка."""
    size = float(num_bytes)
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if size < 1024.0:
            return f"{size:.0f} {unit}" if unit == "Б" else f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} ПБ"


def _fmt_time(timestamp: float) -> str:
    return _dt.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def detect_magic_type(path: str) -> Optional[str]:
    """Определяет тип файла по сигнатуре в начале (magic bytes)."""
    try:
        with open(path, "rb") as fh:
            header = fh.read(16)
    except OSError:
        return None
    for signature, label in _MAGIC_SIGNATURES:
        if header.startswith(signature):
            return label
    # ftyp может быть не с самого начала для некоторых mp4
    if b"ftyp" in header:
        return "MP4 / MOV video"
    return None


# ---------------------------------------------------------------------------
# Экстракторы
# ---------------------------------------------------------------------------
def get_filesystem_metadata(path: str) -> Category:
    st = os.stat(path)
    mime, _ = mimetypes.guess_type(path)
    magic = detect_magic_type(path)
    _, ext = os.path.splitext(path)
    fields = {
        "Имя файла": os.path.basename(path),
        "Папка": os.path.dirname(os.path.abspath(path)),
        "Расширение": ext.lower() or "—",
        "Размер": f"{human_size(st.st_size)} ({st.st_size:,} байт)".replace(",", " "),
        "Тип (MIME)": mime or "неизвестно",
        "Тип (сигнатура)": magic or "не распознан",
        "Создан": _fmt_time(st.st_ctime),
        "Изменён": _fmt_time(st.st_mtime),
        "Открыт": _fmt_time(st.st_atime),
        "Права доступа": stat.filemode(st.st_mode),
        "Владелец (UID)": st.st_uid,
        "Группа (GID)": st.st_gid,
        "Inode": st.st_ino,
    }
    return Category("Файловая система", fields)


def get_hashes(
    path: str,
    chunk_size: int = 1 << 20,
    progress: Optional[Callable[[float], None]] = None,
) -> Category:
    """MD5 и SHA-256 с опциональным колбэком прогресса (0.0–1.0)."""
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    total = max(os.path.getsize(path), 1)
    read = 0
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(chunk_size), b""):
                md5.update(chunk)
                sha256.update(chunk)
                read += len(chunk)
                if progress:
                    progress(min(read / total, 1.0))
    except OSError as exc:
        return Category("Контрольные суммы", {"Ошибка чтения": str(exc)})
    return Category(
        "Контрольные суммы",
        {"MD5": md5.hexdigest(), "SHA-256": sha256.hexdigest()},
    )


def _dms_to_decimal(dms, ref) -> Optional[float]:
    """Преобразует EXIF GPS (градусы, минуты, секунды) в десятичные градусы."""
    try:
        degrees, minutes, seconds = (float(x) for x in dms)
        decimal = degrees + minutes / 60.0 + seconds / 3600.0
        if ref in ("S", "W"):
            decimal = -decimal
        return round(decimal, 6)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _extract_gps(exif) -> dict:
    """Достаёт GPS-координаты из EXIF и формирует ссылку на карту."""
    try:
        gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo)
    except Exception:  # noqa: BLE001
        return {}
    if not gps_ifd:
        return {}
    tags = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps_ifd.items()}
    lat = _dms_to_decimal(tags.get("GPSLatitude"), tags.get("GPSLatitudeRef"))
    lon = _dms_to_decimal(tags.get("GPSLongitude"), tags.get("GPSLongitudeRef"))
    out: dict = {}
    if lat is not None and lon is not None:
        out["GPS координаты"] = f"{lat}, {lon}"
        out["GPS на карте"] = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=15/{lat}/{lon}"
    if "GPSAltitude" in tags:
        out["GPS высота"] = f"{float(tags['GPSAltitude']):.1f} м"
    return out


def get_image_metadata(path: str) -> Optional[Category]:
    if not HAS_PIL:
        return None
    try:
        with Image.open(path) as img:
            fields = {
                "Формат": img.format,
                "Режим": img.mode,
                "Размеры": f"{img.width} x {img.height} px",
                "Мегапиксели": f"{img.width * img.height / 1e6:.1f} Мп",
            }
            if "dpi" in img.info:
                dpi = img.info["dpi"]
                fields["DPI"] = f"{dpi[0]} x {dpi[1]}"
            if img.mode in ("RGBA", "LA", "PA"):
                fields["Прозрачность"] = "да"

            exif = img.getexif()
            if exif:
                for tag_id, value in exif.items():
                    tag = ExifTags.TAGS.get(tag_id, str(tag_id))
                    if isinstance(value, bytes):
                        value = value.decode(errors="replace").strip("\x00")
                    text = str(value)
                    if len(text) > 200:
                        text = text[:200] + "…"
                    fields[f"EXIF: {tag}"] = text
                fields.update(_extract_gps(exif))
            return Category("Изображение", fields)
    except Image.UnidentifiedImageError:
        return None  # не изображение — молча пропускаем
    except Exception as exc:  # noqa: BLE001
        return Category("Изображение", {"Ошибка обработки": str(exc)})


def get_audio_metadata(path: str) -> Optional[Category]:
    if not HAS_MUTAGEN:
        return None
    try:
        audio = mutagen.File(path, easy=True)
        if audio is None:
            return None
        fields: dict = {}
        info = getattr(audio, "info", None)
        if info is not None:
            if hasattr(info, "length"):
                mins, secs = divmod(int(info.length), 60)
                fields["Длительность"] = f"{mins}:{secs:02d} ({info.length:.1f} c)"
            if getattr(info, "bitrate", 0):
                fields["Битрейт"] = f"{info.bitrate // 1000} кбит/с"
            if hasattr(info, "sample_rate"):
                fields["Частота дискретизации"] = f"{info.sample_rate} Гц"
            if hasattr(info, "channels"):
                fields["Каналы"] = info.channels
        for key, value in audio.items():
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value)
            fields[f"Тег: {key}"] = value
        return Category("Аудио", fields) if fields else None
    except Exception as exc:  # noqa: BLE001
        return Category("Аудио", {"Ошибка обработки": str(exc)})


def get_pdf_metadata(path: str) -> Optional[Category]:
    if not HAS_PYPDF or not path.lower().endswith(".pdf"):
        return None
    try:
        reader = PdfReader(path)
        fields: dict = {
            "Количество страниц": len(reader.pages),
            "Зашифрован": "да" if reader.is_encrypted else "нет",
        }
        if reader.metadata:
            for key, value in reader.metadata.items():
                clean = key[1:] if key.startswith("/") else key
                fields[f"PDF: {clean}"] = value
        return Category("PDF-документ", fields)
    except Exception as exc:  # noqa: BLE001
        return Category("PDF-документ", {"Ошибка обработки": str(exc)})


def get_text_metadata(path: str) -> Optional[Category]:
    """Для текстовых файлов: число строк/слов/символов и кодировка."""
    mime, _ = mimetypes.guess_type(path)
    is_textual = (mime and mime.startswith("text")) or os.path.splitext(path)[1].lower() in {
        ".txt", ".md", ".csv", ".json", ".xml", ".html", ".py", ".js", ".c", ".cpp",
        ".java", ".go", ".rs", ".sh", ".ini", ".cfg", ".yml", ".yaml", ".log",
    }
    if not is_textual:
        return None
    if os.path.getsize(path) > 50 * 1024 * 1024:  # не читаем огромные файлы целиком
        return None
    for encoding in ("utf-8", "cp1251", "latin-1"):
        try:
            with open(path, "r", encoding=encoding) as fh:
                content = fh.read()
            lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
            return Category(
                "Текст",
                {
                    "Кодировка": encoding,
                    "Строк": lines,
                    "Слов": len(content.split()),
                    "Символов": len(content),
                },
            )
        except (UnicodeDecodeError, OSError):
            continue
    return None


def _iter_boxes(fh, start: int, end: int):
    """Итерирует ISO-BMFF (MP4/MOV) боксы в диапазоне [start, end)."""
    fh.seek(start)
    while fh.tell() < end:
        pos = fh.tell()
        header = fh.read(8)
        if len(header) < 8:
            break
        size = int.from_bytes(header[:4], "big")
        box_type = header[4:8]
        header_len = 8
        if size == 1:  # 64-битный размер
            size = int.from_bytes(fh.read(8), "big")
            header_len = 16
        elif size == 0:  # бокс до конца файла
            size = end - pos
        if size < header_len:
            break
        yield pos, box_type, header_len, size
        fh.seek(pos + size)


def get_video_metadata(path: str) -> Optional[Category]:
    """Длительность и размеры видео MP4/MOV (парсинг moov без зависимостей)."""
    if os.path.splitext(path)[1].lower() not in {".mp4", ".m4v", ".mov"}:
        return None
    try:
        fields: dict = {}
        file_size = os.path.getsize(path)
        with open(path, "rb") as fh:
            for pos, btype, hlen, size in _iter_boxes(fh, 0, file_size):
                if btype != b"moov":
                    continue
                for mpos, mtype, mhlen, msize in _iter_boxes(fh, pos + hlen, pos + size):
                    if mtype == b"mvhd":
                        fh.seek(mpos + mhlen)
                        version = fh.read(1)[0]
                        fh.read(3)  # flags
                        if version == 1:
                            fh.read(16)  # creation + modification (8+8)
                            timescale = int.from_bytes(fh.read(4), "big")
                            duration = int.from_bytes(fh.read(8), "big")
                        else:
                            fh.read(8)  # creation + modification (4+4)
                            timescale = int.from_bytes(fh.read(4), "big")
                            duration = int.from_bytes(fh.read(4), "big")
                        if timescale:
                            secs = duration / timescale
                            mins, s = divmod(int(secs), 60)
                            hours, mins = divmod(mins, 60)
                            fields["Длительность"] = (
                                f"{hours}:{mins:02d}:{s:02d}" if hours
                                else f"{mins}:{s:02d}"
                            ) + f" ({secs:.1f} c)"
                    elif mtype == b"trak":
                        for tpos, ttype, thlen, tsize in _iter_boxes(fh, mpos + mhlen, mpos + msize):
                            if ttype == b"tkhd":
                                fh.seek(tpos + thlen)
                                payload = fh.read(tsize - thlen)
                                if len(payload) >= 8:
                                    w = int.from_bytes(payload[-8:-4], "big") >> 16
                                    h = int.from_bytes(payload[-4:], "big") >> 16
                                    if w and h:
                                        fields.setdefault("Размеры", f"{w} x {h} px")
                break
        return Category("Видео", fields) if fields else None
    except Exception as exc:  # noqa: BLE001
        return Category("Видео", {"Ошибка обработки": str(exc)})


# Имена тегов Office Open XML -> человекочитаемые подписи.
_OFFICE_TAGS = {
    "title": "Заголовок", "subject": "Тема", "creator": "Автор",
    "keywords": "Ключевые слова", "description": "Описание",
    "lastModifiedBy": "Изменил", "revision": "Ревизия",
    "created": "Создан", "modified": "Изменён", "category": "Категория",
    "Application": "Приложение", "Company": "Компания", "Pages": "Страниц",
    "Words": "Слов", "Characters": "Символов", "Lines": "Строк",
    "Paragraphs": "Абзацев", "Slides": "Слайдов", "AppVersion": "Версия приложения",
}


def get_office_metadata(path: str) -> Optional[Category]:
    """Метаданные документов Office Open XML (docx, xlsx, pptx) — без зависимостей."""
    if os.path.splitext(path)[1].lower() not in {".docx", ".xlsx", ".pptx"}:
        return None
    try:
        fields: dict = {}
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            for part in ("docProps/core.xml", "docProps/app.xml"):
                if part not in names:
                    continue
                root = ET.fromstring(zf.read(part))
                for elem in root.iter():
                    tag = elem.tag.split("}")[-1]  # убираем namespace
                    if tag in _OFFICE_TAGS and elem.text and elem.text.strip():
                        fields[_OFFICE_TAGS[tag]] = elem.text.strip()
        return Category("Документ Office", fields) if fields else None
    except (zipfile.BadZipFile, ET.ParseError, OSError) as exc:
        return Category("Документ Office", {"Ошибка обработки": str(exc)})


def get_archive_metadata(path: str) -> Optional[Category]:
    """Содержимое ZIP-архива (и форматов на его основе) — без зависимостей."""
    if not zipfile.is_zipfile(path):
        return None
    # Office-документы тоже ZIP, но для них есть отдельный экстрактор.
    if os.path.splitext(path)[1].lower() in {".docx", ".xlsx", ".pptx"}:
        return None
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
            total = sum(i.file_size for i in infos)
            compressed = sum(i.compress_size for i in infos)
            ratio = (1 - compressed / total) * 100 if total else 0
            sample = ", ".join(i.filename for i in infos[:5])
            if len(infos) > 5:
                sample += f" … (+{len(infos) - 5})"
            return Category(
                "Архив (ZIP)",
                {
                    "Файлов внутри": len(infos),
                    "Размер распакованный": human_size(total),
                    "Размер сжатый": human_size(compressed),
                    "Степень сжатия": f"{ratio:.1f} %",
                    "Содержимое": sample or "(пусто)",
                },
            )
    except (zipfile.BadZipFile, OSError) as exc:
        return Category("Архив (ZIP)", {"Ошибка обработки": str(exc)})


def get_hex_header(path: str, length: int = 64) -> Category:
    """Hex-дамп первых байтов файла."""
    try:
        with open(path, "rb") as fh:
            data = fh.read(length)
    except OSError as exc:
        return Category("Hex-заголовок", {"Ошибка чтения": str(exc)})
    lines = {}
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines[f"{i:04x}"] = f"{hex_part:<47}  {ascii_part}"
    return Category("Hex-заголовок", lines or {"(пусто)": ""})


# Порядок имеет значение: специфичные экстракторы идут после файловой системы.
_EXTRACTORS = (
    get_image_metadata,
    get_audio_metadata,
    get_video_metadata,
    get_pdf_metadata,
    get_office_metadata,
    get_archive_metadata,
    get_text_metadata,
)


def collect_metadata(
    path: str, include_hashes: bool = True, include_hex: bool = False
) -> list[Category]:
    """Собирает все доступные метаданные в виде списка категорий."""
    if not os.path.isfile(path):
        raise FileNotFoundError(path)

    categories: list[Category] = [get_filesystem_metadata(path)]
    for extractor in _EXTRACTORS:
        result = extractor(path)
        if result:
            categories.append(result)
    if include_hashes:
        categories.append(get_hashes(path))
    if include_hex:
        categories.append(get_hex_header(path))
    return categories


def metadata_to_dict(categories: list[Category]) -> dict:
    """Категории -> вложенный словарь (для JSON-экспорта)."""
    return {c.name: {k: str(v) for k, v in c.fields.items()} for c in categories}


def strip_metadata(path: str, out_path: Optional[str] = None) -> str:
    """
    Удаляет метаданные (EXIF/GPS и пр.) из изображения, сохраняя пиксели.
    Возвращает путь к очищенной копии. Требует Pillow.

    Полезно для приватности: убирает геолокацию, модель камеры, даты съёмки.
    """
    if not HAS_PIL:
        raise RuntimeError("Для очистки метаданных нужна библиотека Pillow")
    if out_path is None:
        base, ext = os.path.splitext(path)
        out_path = f"{base}_clean{ext}"
    with Image.open(path) as img:
        # Пересоздаём изображение только из пиксельных данных — метаданные теряются.
        clean = Image.frombytes(img.mode, img.size, img.tobytes())
        if img.mode == "P":
            clean.putpalette(img.getpalette())
        clean.save(out_path)
    return out_path


def module_status() -> dict[str, bool]:
    """Какие необязательные библиотеки доступны."""
    return {"Pillow": HAS_PIL, "mutagen": HAS_MUTAGEN, "pypdf": HAS_PYPDF}
