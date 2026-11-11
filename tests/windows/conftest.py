from __future__ import annotations

import importlib
import os
import runpy
import sys
from contextlib import contextmanager
from functools import cache
from pathlib import Path
from types import ModuleType, TracebackType
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

    from pytest_mock import MockerFixture, MockType
    from typing_extensions import Self

    from python_discovery import PythonSpec


@pytest.fixture
def _mock_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    winreg = _create_winreg_mock() if sys.platform != "win32" else importlib.import_module("winreg")
    monkeypatch.setitem(sys.modules, "winreg", winreg)

    values = runpy.run_path(str(Path(__file__).parent / "winreg_mock_values.py"), init_globals={"winreg": winreg})
    enum_collect: dict[int, list[str | OSError]] = values["_ENUM_COLLECT"]
    value_collect: dict[int, dict[str, tuple[str, int] | OSError]] = values["_VALUE_COLLECT"]
    key_open: dict[int, dict[str, int]] = values["_KEY_OPEN"]
    hive_open: dict[tuple[int, str, int, int], int | OSError] = values["_HIVE_OPEN"]

    def _enum_key(key: _Key | int, at: int) -> str:
        result = enum_collect[_key_value(key)][at]
        if isinstance(result, OSError):
            raise result
        return result

    @contextmanager
    def _open_key_ex(*args: object) -> Generator[_Key | int | OSError]:
        if len(args) == 2:
            key, value = args
            result = _Key(key_open[_key_value(key)][value])
        elif len(args) == 4:
            result = hive_open[args]
        else:
            raise RuntimeError
        value = result.value if isinstance(result, _Key) else result
        if isinstance(value, OSError):
            raise value
        yield result

    def _query_value_ex(key: _Key | int, value_name: str) -> tuple[str, int]:
        result = value_collect[_key_value(key)][value_name]
        if isinstance(result, OSError):
            raise result
        return result

    monkeypatch.setattr(winreg, "EnumKey", _enum_key)
    monkeypatch.setattr(winreg, "QueryValueEx", _query_value_ex)
    monkeypatch.setattr(winreg, "OpenKeyEx", _open_key_ex)
    real_exists = os.path.exists

    def _mock_exists(path: str) -> bool:
        return (isinstance(path, str) and ("\\" in path or path.startswith(("C:", "Z:")))) or real_exists(path)

    monkeypatch.setattr("os.path.exists", _mock_exists)


# _pep514 binds winreg at import, so every test must patch the same fake module.
@cache
def _create_winreg_mock() -> ModuleType:
    # Create a mock winreg module that works on all platforms.
    winreg = ModuleType("winreg")
    winreg.HKEY_CURRENT_USER = 0x80000001  # ty: ignore[unresolved-attribute] winreg is Windows-only, so type checkers cannot resolve it
    winreg.HKEY_LOCAL_MACHINE = 0x80000002  # ty: ignore[unresolved-attribute] winreg is Windows-only, so type checkers cannot resolve it
    winreg.KEY_READ = 0x20019  # ty: ignore[unresolved-attribute] winreg is Windows-only, so type checkers cannot resolve it
    winreg.KEY_WOW64_64KEY = 0x0100  # ty: ignore[unresolved-attribute] winreg is Windows-only, so type checkers cannot resolve it
    winreg.KEY_WOW64_32KEY = 0x0200  # ty: ignore[unresolved-attribute] winreg is Windows-only, so type checkers cannot resolve it
    # the fixture swaps these for registry lookups; the attributes must exist for mocker to patch them
    winreg.EnumKey = None  # ty: ignore[unresolved-attribute] winreg is Windows-only, so type checkers cannot resolve it
    winreg.QueryValueEx = None  # ty: ignore[unresolved-attribute] winreg is Windows-only, so type checkers cannot resolve it
    winreg.OpenKeyEx = None  # ty: ignore[unresolved-attribute] winreg is Windows-only, so type checkers cannot resolve it
    return winreg


def _key_value(key: _Key | int) -> int:
    return key.value if isinstance(key, _Key) else key


class _Key:
    def __init__(self, value: int) -> None:
        self.value = value

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None
    ) -> None:
        return None


@pytest.fixture
def _populate_pyinfo_cache(monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture) -> None:
    from python_discovery._cached_py_info import _CACHE

    python_core_path = "C:\\Users\\user\\AppData\\Local\\Programs\\Python"
    interpreters = [
        ("ContinuumAnalytics", 3, 10, 32, False, "C:\\Users\\user\\Miniconda3\\python.exe"),
        ("ContinuumAnalytics", 3, 10, 64, False, "C:\\Users\\user\\Miniconda3-64\\python.exe"),
        ("PythonCore", 3, 9, 64, False, f"{python_core_path}\\Python36\\python.exe"),
        ("PythonCore", 3, 9, 64, False, f"{python_core_path}\\Python36\\python.exe"),
        ("PythonCore", 3, 5, 64, False, f"{python_core_path}\\Python35\\python.exe"),
        ("PythonCore", 3, 9, 64, False, f"{python_core_path}\\Python36\\python.exe"),
        ("PythonCore", 3, 7, 32, False, f"{python_core_path}\\Python37-32\\python.exe"),
        ("PythonCore", 3, 12, 64, False, f"{python_core_path}\\Python312\\python.exe"),
        ("PythonCore", 3, 13, 64, True, f"{python_core_path}\\Python313\\python3.13t.exe"),
        ("PythonCore", 2, 7, 64, False, "C:\\Python27\\python.exe"),
        ("PythonCore", 3, 4, 64, False, "C:\\Python34\\python.exe"),
        ("CompanyA", 3, 6, 64, False, "Z:\\CompanyA\\Python\\3.6\\python.exe"),
    ]
    for _, major, minor, arch, threaded, exe in interpreters:
        info = _mock_pyinfo(mocker, major, minor, arch, exe, threaded)
        monkeypatch.setitem(_CACHE, (Path(info.executable), None), info)


def _mock_pyinfo(mocker: MockerFixture, major: int, minor: int, arch: int, exe: str, threaded: bool) -> MockType:
    from python_discovery._py_info import PythonInfo, VersionInfo

    info = mocker.MagicMock(spec=PythonInfo, base_prefix=str(Path(exe).parent))
    info.executable = info.original_executable = info.system_executable = exe
    info.implementation = "CPython"
    info.architecture = arch
    info.version_info = VersionInfo(major, minor, 0, "final", 0)
    info.free_threaded = threaded
    info.sysconfig_platform = "win-amd64" if arch == 64 else "win32"
    info.machine = "x86_64" if arch == 64 else "x86"
    info.resolve_to_system.return_value = info

    def satisfies(spec: PythonSpec, **_kwargs: object) -> bool:
        if spec.implementation is not None and spec.implementation.lower() != "cpython":
            return False
        if spec.architecture is not None and spec.architecture != arch:
            return False
        if spec.free_threaded is not None and spec.free_threaded != threaded:
            return False
        if spec.major is not None and spec.major != major:
            return False
        return not (spec.minor is not None and spec.minor != minor)

    info.satisfies = satisfies
    return info
