"""Windows-specific Python discovery via PEP 514 registry entries."""

from __future__ import annotations

__lazy_modules__ = [
    f"{__spec__.parent}._cancel_io",  # ty: ignore[unresolved-attribute]  # imported modules have a spec
    f"{__spec__.parent}._propose",  # ty: ignore[unresolved-attribute]  # imported modules have a spec
]

from ._cancel_io import stop_query_reader
from ._propose import propose_interpreters

__all__ = [
    "propose_interpreters",
    "stop_query_reader",
]
