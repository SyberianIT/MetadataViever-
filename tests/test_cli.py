"""Тесты интерфейса командной строки (без запуска GUI)."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from metadataviewer import cli  # noqa: E402


def test_cli_text_output(tmp_path, capsys):
    f = tmp_path / "a.txt"
    f.write_text("hello world", encoding="utf-8")
    code = cli.main([str(f)])
    out = capsys.readouterr().out
    assert code == 0
    assert "Файловая система" in out
    assert "a.txt" in out


def test_cli_json_output(tmp_path, capsys):
    f = tmp_path / "a.txt"
    f.write_text("hello", encoding="utf-8")
    code = cli.main([str(f), "--json"])
    out = capsys.readouterr().out
    assert code == 0
    data = json.loads(out)
    assert str(f) in data
    assert "Файловая система" in data[str(f)]


def test_cli_output_file(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hi", encoding="utf-8")
    report = tmp_path / "report.json"
    code = cli.main([str(f), "--json", "-o", str(report)])
    assert code == 0
    assert report.is_file()
    data = json.loads(report.read_text(encoding="utf-8"))
    assert str(f) in data


def test_cli_missing_file_returns_error(capsys):
    code = cli.main(["/no/such/file.xyz"])
    err = capsys.readouterr().err
    assert code == 1
    assert "Пропущен" in err


def test_cli_no_hash_by_default(tmp_path, capsys):
    f = tmp_path / "a.txt"
    f.write_text("data", encoding="utf-8")
    cli.main([str(f)])
    out = capsys.readouterr().out
    assert "SHA-256" not in out


def test_cli_hash_flag(tmp_path, capsys):
    f = tmp_path / "a.txt"
    f.write_text("data", encoding="utf-8")
    cli.main([str(f), "--hash"])
    out = capsys.readouterr().out
    assert "SHA-256" in out


@pytest.mark.skipif(not __import__("metadataviewer.extractors", fromlist=["HAS_PIL"]).HAS_PIL,
                    reason="нужен Pillow")
def test_cli_strip(tmp_path, capsys):
    from PIL import Image

    src = tmp_path / "p.png"
    Image.new("RGB", (8, 8), "blue").save(src)
    code = cli.main([str(src), "--strip"])
    out = capsys.readouterr().out
    assert code == 0
    assert "удалены" in out
    assert (tmp_path / "p_clean.png").is_file()
