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
