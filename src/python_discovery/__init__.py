"""Self-contained Python interpreter discovery."""

from __future__ import annotations

from importlib.metadata import version

from ._cache import ContentStore, DiskCache, PyInfoCache
from ._discovery import get_interpreter
from ._py_info import PythonInfo
from ._py_spec import PythonSpec

__version__ = version("python-discovery")

__all__ = [
    "ContentStore",
    "DiskCache",
    "PyInfoCache",
    "PythonInfo",
    "PythonSpec",
    "__version__",
    "get_interpreter",
]
