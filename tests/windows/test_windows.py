from __future__ import annotations

import sys
from pathlib import Path

import pytest

from python_discovery import PythonSpec, get_interpreter


@pytest.mark.skipif(sys.platform != "win32", reason="Windows executable alias")
def test_discovery_via_path_literal_symlink(tmp_path: Path) -> None:
    link = tmp_path / "python_custom.exe"
    link.symlink_to(Path(sys.base_prefix) / "python.exe")

    interpreter = get_interpreter("python_custom", [], env={"PATH": f"{tmp_path};{sys.base_prefix}"})

    assert interpreter is not None
    assert interpreter.executable == str(link)


@pytest.mark.skipif(sys.platform != "win32", reason="propose_interpreters calls from_exe with Windows paths")
@pytest.mark.usefixtures("_mock_registry")
@pytest.mark.usefixtures("_populate_pyinfo_cache")
@pytest.mark.parametrize(
    ("string_spec", "expected_exe"),
    [
        ("python3.10", "C:\\Users\\user\\Miniconda3-64\\python.exe"),
        ("cpython3.10", "C:\\Users\\user\\Miniconda3-64\\python.exe"),
        ("python3.12", "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python312\\python.exe"),
        ("cpython3.12", "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python312\\python.exe"),
        ("python", "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python313\\python3.13t.exe"),
        ("cpython", "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python313\\python3.13t.exe"),
        ("python3", "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python312\\python.exe"),
        ("cpython3", "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python312\\python.exe"),
        ("python3.6", "Z:\\CompanyA\\Python\\3.6\\python.exe"),
        ("cpython3.6", "Z:\\CompanyA\\Python\\3.6\\python.exe"),
        ("3t", "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python313\\python3.13t.exe"),
        ("python3.13t", "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python313\\python3.13t.exe"),
    ],
)
def test_propose_interpreters(string_spec: str, expected_exe: str) -> None:
    from python_discovery._windows import propose_interpreters

    spec = PythonSpec.from_string_spec(string_spec)
    interpreter = next(propose_interpreters(spec=spec, cache=None, env={}))
    assert interpreter.executable == expected_exe
