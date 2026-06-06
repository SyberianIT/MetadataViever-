"""Точка входа: python -m metadataviewer [файл]"""

import sys

from .app import run


def main():
    initial = sys.argv[1] if len(sys.argv) > 1 else None
    run(initial)


if __name__ == "__main__":
    main()
