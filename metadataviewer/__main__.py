"""Точка входа: python -m metadataviewer [файлы...] [опции]"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
