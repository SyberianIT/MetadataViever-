"""Тесты логики извлечения метаданных (работают без GUI и дисплея)."""

import hashlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from metadataviewer import extractors  # noqa: E402


def test_human_size():
    assert extractors.human_size(0) == "0 Б"
    assert extractors.human_size(512) == "512 Б"
    assert extractors.human_size(1536) == "1.50 КБ"
    assert extractors.human_size(1024 ** 3) == "1.00 ГБ"


def test_filesystem_metadata(tmp_path):
    f = tmp_path / "hello.txt"
    f.write_text("привет мир\n", encoding="utf-8")
    cat = extractors.get_filesystem_metadata(str(f))
    assert cat.name == "Файловая система"
    assert cat.fields["Имя файла"] == "hello.txt"
    assert cat.fields["Расширение"] == ".txt"
    assert "Размер" in cat.fields


def test_hashes_match_stdlib(tmp_path):
    f = tmp_path / "data.bin"
    payload = b"metadata-viewer" * 1000
    f.write_bytes(payload)
    cat = extractors.get_hashes(str(f))
    assert cat.fields["MD5"] == hashlib.md5(payload).hexdigest()
    assert cat.fields["SHA-256"] == hashlib.sha256(payload).hexdigest()


def test_hash_progress_callback(tmp_path):
    f = tmp_path / "big.bin"
    f.write_bytes(b"x" * (3 << 20))  # 3 МБ -> несколько чанков
    seen = []
    extractors.get_hashes(str(f), chunk_size=1 << 20, progress=seen.append)
    assert seen and seen[-1] == pytest.approx(1.0)


def test_magic_detection(tmp_path):
    png = tmp_path / "fake.bin"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
    assert extractors.detect_magic_type(str(png)) == "PNG image"

    pdf = tmp_path / "doc.bin"
    pdf.write_bytes(b"%PDF-1.7\n%...")
    assert extractors.detect_magic_type(str(pdf)) == "PDF document"


def test_text_metadata(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("one two three\nfour five\n", encoding="utf-8")
    cat = extractors.get_text_metadata(str(f))
    assert cat is not None
    assert cat.fields["Строк"] == 2
    assert cat.fields["Слов"] == 5
    assert cat.fields["Кодировка"] == "utf-8"


def test_dms_to_decimal():
    # 55°45'7.2" N  ->  55.752
    assert extractors._dms_to_decimal((55, 45, 7.2), "N") == pytest.approx(55.752, abs=1e-3)
    # Западная/южная — отрицательные
    assert extractors._dms_to_decimal((37, 37, 0), "W") < 0


def test_collect_metadata_structure(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_text("hello", encoding="utf-8")
    cats = extractors.collect_metadata(str(f))
    names = [c.name for c in cats]
    assert names[0] == "Файловая система"
    assert "Контрольные суммы" in names
    assert "Текст" in names


def test_collect_metadata_missing_file():
    with pytest.raises(FileNotFoundError):
        extractors.collect_metadata("/no/such/file.xyz")


def test_module_status_keys():
    status = extractors.module_status()
    assert set(status) == {"Pillow", "mutagen", "pypdf"}
    assert all(isinstance(v, bool) for v in status.values())


# --- Архивы ----------------------------------------------------------------
def test_archive_metadata(tmp_path):
    import zipfile

    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("a.txt", "hello")
        zf.writestr("b.txt", "world!!!")
    cat = extractors.get_archive_metadata(str(archive))
    assert cat is not None
    assert cat.fields["Файлов внутри"] == 2
    assert "a.txt" in cat.fields["Содержимое"]


# --- Office ----------------------------------------------------------------
def test_office_metadata(tmp_path):
    import zipfile

    core = (
        '<?xml version="1.0"?>'
        '<cp:coreProperties xmlns:cp="x" xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:creator>Иван</dc:creator><dc:title>Отчёт</dc:title>"
        "</cp:coreProperties>"
    )
    docx = tmp_path / "doc.docx"
    with zipfile.ZipFile(docx, "w") as zf:
        zf.writestr("docProps/core.xml", core)
    cat = extractors.get_office_metadata(str(docx))
    assert cat is not None
    assert cat.fields["Автор"] == "Иван"
    assert cat.fields["Заголовок"] == "Отчёт"
    # docx не должен попадать в общий ZIP-экстрактор
    assert extractors.get_archive_metadata(str(docx)) is None


# --- Видео MP4 -------------------------------------------------------------
def _build_minimal_mp4(timescale: int, duration: int) -> bytes:
    import struct

    # mvhd (version 0): version+flags(4) + creation(4)+mod(4) + timescale(4)+duration(4)
    mvhd_payload = b"\x00\x00\x00\x00" + b"\x00" * 8 + struct.pack(">II", timescale, duration)
    mvhd = struct.pack(">I", 8 + len(mvhd_payload)) + b"mvhd" + mvhd_payload
    moov = struct.pack(">I", 8 + len(mvhd)) + b"moov" + mvhd
    ftyp = struct.pack(">I", 16) + b"ftyp" + b"isom" + b"\x00" * 4
    return ftyp + moov


def test_video_metadata(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(_build_minimal_mp4(timescale=1000, duration=5000))
    cat = extractors.get_video_metadata(str(video))
    assert cat is not None
    assert "0:05" in cat.fields["Длительность"]
    assert "5.0 c" in cat.fields["Длительность"]


def test_video_metadata_ignores_non_video(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("not a video")
    assert extractors.get_video_metadata(str(f)) is None


# --- Hex-заголовок ---------------------------------------------------------
def test_hex_header(tmp_path):
    f = tmp_path / "raw.bin"
    f.write_bytes(bytes(range(32)))
    cat = extractors.get_hex_header(str(f), length=16)
    assert cat.name == "Hex-заголовок"
    assert "0000" in cat.fields
    assert "00 01 02 03" in cat.fields["0000"]


# --- Очистка метаданных ----------------------------------------------------
@pytest.mark.skipif(not extractors.HAS_PIL, reason="нужен Pillow")
def test_strip_metadata(tmp_path):
    from PIL import Image

    src = tmp_path / "img.png"
    Image.new("RGB", (10, 10), "red").save(src)
    out = extractors.strip_metadata(str(src))
    assert os.path.isfile(out)
    with Image.open(out) as cleaned:
        assert cleaned.size == (10, 10)
        assert len(dict(cleaned.getexif())) == 0


# --- collect_metadata с hex ------------------------------------------------
def test_collect_metadata_with_hex(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"\x00\x01\x02")
    cats = extractors.collect_metadata(str(f), include_hex=True)
    assert any(c.name == "Hex-заголовок" for c in cats)


@pytest.mark.skipif(not extractors.HAS_PIL, reason="нужен Pillow")
def test_image_extractor_skips_non_image(tmp_path):
    f = tmp_path / "code.py"
    f.write_text("print('hello')\n", encoding="utf-8")
    # Не изображение -> None, без категории «Ошибка обработки»
    assert extractors.get_image_metadata(str(f)) is None
    names = [c.name for c in extractors.collect_metadata(str(f))]
    assert "Изображение" not in names


def test_metadata_to_dict(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("hi")
    d = extractors.metadata_to_dict(extractors.collect_metadata(str(f)))
    assert "Файловая система" in d
    assert isinstance(d["Файловая система"], dict)
