"""MetadataViewer — просмотр метаданных файлов с графическим интерфейсом."""

__version__ = "1.1.0"

from .extractors import (  # noqa: E402
    Category,
    collect_metadata,
    metadata_to_dict,
    module_status,
    strip_metadata,
)

__all__ = [
    "Category",
    "collect_metadata",
    "metadata_to_dict",
    "strip_metadata",
    "module_status",
    "__version__",
]
