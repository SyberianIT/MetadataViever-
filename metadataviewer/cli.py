"""
Интерфейс командной строки MetadataViewer.

Без аргументов (или с --gui) запускает графический интерфейс.
С указанием файлов выводит метаданные в терминал / JSON или чистит их.

Примеры:
    metadataviewer                          # окно GUI
    metadataviewer photo.jpg                # метаданные в терминал
    metadataviewer *.jpg --json -o out.json # в JSON-файл
    metadataviewer photo.jpg --strip        # удалить EXIF/GPS (копия *_clean)
    metadataviewer file.bin --hex --hash    # с hex-заголовком и хешами
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__, extractors


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="metadataviewer",
        description="Просмотр и очистка метаданных файлов (GUI и CLI).",
    )
    p.add_argument("files", nargs="*", help="файлы для анализа (если нет — запуск GUI)")
    p.add_argument("--gui", action="store_true", help="принудительно запустить GUI")
    p.add_argument("--json", action="store_true", help="вывод в формате JSON")
    p.add_argument("-o", "--output", metavar="FILE", help="записать отчёт в файл")
    p.add_argument("--hash", action="store_true", help="считать MD5/SHA-256")
    p.add_argument("--no-hash", action="store_true", help="не считать хеши (по умолчанию для CLI)")
    p.add_argument("--hex", action="store_true", help="показать hex-заголовок файла")
    p.add_argument("--strip", action="store_true",
                   help="удалить метаданные из изображений (создаёт *_clean копию)")
    p.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _render_text(path: str, categories) -> str:
    out = [f"Метаданные файла: {path}", "=" * 60, ""]
    for cat in categories:
        out.append(f"[{cat.name}]")
        width = max((len(str(k)) for k in cat.fields), default=0)
        for key, value in cat.fields.items():
            out.append(f"  {str(key):<{width}} : {value}")
        out.append("")
    return "\n".join(out)


def run_cli(args: argparse.Namespace) -> int:
    include_hashes = args.hash and not args.no_hash
    results: dict[str, list] = {}
    exit_code = 0

    for path in args.files:
        if not os.path.isfile(path):
            print(f"Пропущен (не файл): {path}", file=sys.stderr)
            exit_code = 1
            continue

        if args.strip:
            try:
                out = extractors.strip_metadata(path)
                print(f"Метаданные удалены: {path} -> {out}")
            except Exception as exc:  # noqa: BLE001
                print(f"Ошибка очистки {path}: {exc}", file=sys.stderr)
                exit_code = 1
            continue

        cats = extractors.collect_metadata(
            path, include_hashes=include_hashes, include_hex=args.hex
        )
        results[path] = cats

    if args.strip or not results:
        return exit_code

    if args.json:
        payload = {p: extractors.metadata_to_dict(c) for p, c in results.items()}
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        text = "\n".join(_render_text(p, c) for p, c in results.items())

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"Отчёт сохранён: {args.output}", file=sys.stderr)
    else:
        print(text)

    return exit_code


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    # Нет файлов или явный --gui -> графический интерфейс.
    if args.gui or not args.files:
        from .app import run

        run(args.files[0] if args.files else None)
        return 0

    return run_cli(args)


if __name__ == "__main__":
    sys.exit(main())
