"""MetadataViewer — просмотр метаданных файлов с графическим интерфейсом."""

from .extractors import Category, collect_metadata, module_status

__version__ = "1.0.0"
__all__ = ["Category", "collect_metadata", "module_status", "__version__"]
