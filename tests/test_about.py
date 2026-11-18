from __future__ import annotations

from importlib.metadata import version

from python_discovery import __version__


def test_version() -> None:
    assert __version__ == version("python-discovery")
