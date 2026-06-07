#!/usr/bin/env python3
"""
Запуск MetadataViewer.

    python3 metadata_viewer.py                 # графический интерфейс
    python3 metadata_viewer.py файл.jpg        # метаданные в терминал
    python3 metadata_viewer.py файл.jpg --gui  # открыть файл в окне
    python3 metadata_viewer.py --help          # все опции CLI

Логика разнесена по пакету metadataviewer:
    extractors.py — извлечение/очистка метаданных (без GUI, покрыто тестами);
    app.py        — графический интерфейс Tkinter;
    cli.py        — интерфейс командной строки.
"""

import sys

from metadataviewer.cli import main

if __name__ == "__main__":
    sys.exit(main())
