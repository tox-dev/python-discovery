from __future__ import annotations

import logging
from pathlib import Path

import pytest

from python_discovery import DiskCache, PythonInfo
from python_discovery._compat import fs_is_case_sensitive
from python_discovery._discovery import IS_WIN
from python_discovery._py_info import EXTENSIONS

_CURRENT = PythonInfo.current()


def _fs_supports_symlink() -> bool:
    return not IS_WIN


def test_discover_empty_folder(tmp_path: Path, session_cache: DiskCache) -> None:
    with pytest.raises(RuntimeError):
        _CURRENT.discover_exe(session_cache, prefix=str(tmp_path))


def _discover_base_folders() -> tuple[str, ...]:
    exe_dir = str(Path(_CURRENT.executable).parent)
    folders: dict[str, None] = {}
    if exe_dir.startswith(_CURRENT.prefix):  # pragma: no branch
        relative = exe_dir[len(_CURRENT.prefix) :].lstrip("/\\")
        if relative:  # pragma: no branch
            folders[relative] = None
    folders["."] = None
    return tuple(folders)


_BASE = _discover_base_folders()


@pytest.mark.skipif(not _fs_supports_symlink(), reason="symlink is not supported")
@pytest.mark.parametrize("suffix", sorted({".exe", ""} & set(EXTENSIONS) if IS_WIN else [""]))
@pytest.mark.parametrize("into", _BASE)
@pytest.mark.parametrize("arch", [_CURRENT.architecture, ""])
@pytest.mark.parametrize("version", [".".join(str(i) for i in _CURRENT.version_info[0:i]) for i in range(3, 0, -1)])
@pytest.mark.parametrize("impl", [_CURRENT.implementation, "python"])
def test_discover_ok(
    tmp_path: Path,
    suffix: str,
    impl: str,
    version: str,
    *,
    arch: int | str,
    into: str,
    caplog: pytest.LogCaptureFixture,
    session_cache: DiskCache,
) -> None:
    caplog.set_level(logging.DEBUG)
    folder = tmp_path / into
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{impl}{version}{'t' if _CURRENT.free_threaded else ''}"
    if arch:
        name += f"-{arch}"
    name += suffix
    dest = folder / name
    Path(str(dest)).symlink_to(_CURRENT.executable)
    pyvenv = Path(_CURRENT.executable).parents[1] / "pyvenv.cfg"
    if pyvenv.exists():  # pragma: no branch
        (folder / pyvenv.name).write_text(pyvenv.read_text(encoding="utf-8"), encoding="utf-8")
    inside_folder = str(tmp_path)
    found = _CURRENT.discover_exe(session_cache, inside_folder).executable
    dest_str = str(dest)
    if not fs_is_case_sensitive():  # pragma: win32 cover
        found = found.lower()
        dest_str = dest_str.lower()
    assert found == dest_str
    assert len(caplog.messages) >= 1, caplog.text
    assert "get interpreter info via cmd: " in caplog.text

    dest.rename(dest.parent / (f"{dest.name}-1"))
    _CURRENT._cache_exe_discovery.clear()
    with pytest.raises(RuntimeError):
        _CURRENT.discover_exe(session_cache, inside_folder)
