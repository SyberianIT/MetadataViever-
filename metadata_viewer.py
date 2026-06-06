#!/usr/bin/env python3
"""
Запуск MetadataViewer.

    python3 metadata_viewer.py [путь_к_файлу]

Это тонкая обёртка над пакетом metadataviewer. Вся логика находится в
metadataviewer/extractors.py (извлечение метаданных) и
metadataviewer/app.py (графический интерфейс).
"""

import sys

from metadataviewer.app import run

if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else None)
