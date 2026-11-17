from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from contextlib import AbstractContextManager
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from python_discovery import PythonSpec

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytest_mock import MockerFixture


@pytest.mark.skipif(sys.platform != "win32", reason="propose_interpreters calls from_exe with Windows paths")
@pytest.mark.usefixtures("_mock_registry")
@pytest.mark.usefixtures("_mock_interpreter_query")
@pytest.mark.parametrize(
    ("string_spec", "expected_exe"),
    [
        pytest.param("python3.10", "C:\\Users\\user\\Miniconda3-64\\python.exe", id="python3.10"),
        pytest.param("cpython3.10", "C:\\Users\\user\\Miniconda3-64\\python.exe", id="cpython3.10"),
        pytest.param(
            "python3.12", "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python312\\python.exe", id="python3.12"
        ),
        pytest.param(
            "cpython3.12", "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python312\\python.exe", id="cpython3.12"
        ),
        pytest.param(
            "python", "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python313\\python3.13t.exe", id="python"
        ),
        pytest.param(
            "cpython", "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python313\\python3.13t.exe", id="cpython"
        ),
        pytest.param(
            "python3", "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python312\\python.exe", id="python3"
        ),
        pytest.param(
            "cpython3", "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python312\\python.exe", id="cpython3"
        ),
        pytest.param("python3.6", "Z:\\CompanyA\\Python\\3.6\\python.exe", id="python3.6"),
        pytest.param("cpython3.6", "Z:\\CompanyA\\Python\\3.6\\python.exe", id="cpython3.6"),
        pytest.param("3t", "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python313\\python3.13t.exe", id="3t"),
        pytest.param(
            "python3.13t",
            "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python313\\python3.13t.exe",
            id="python3.13t",
        ),
    ],
)
def test_propose_interpreters(string_spec: str, expected_exe: str) -> None:
    from python_discovery._windows._propose import propose_interpreters

    interpreter = next(propose_interpreters(spec=PythonSpec.from_string_spec(string_spec), cache=None, env={}))
    assert interpreter.executable == expected_exe


@pytest.mark.usefixtures("_mock_registry")
def test_pep514_discovers_interpreters() -> None:
    from python_discovery._windows._pep514 import discover_pythons

    interpreters = list(discover_pythons())
    assert len(interpreters) == 12
    companies = {i[0] for i in interpreters}
    assert "ContinuumAnalytics" in companies
    assert "PythonCore" in companies
    assert "CompanyA" in companies


@pytest.mark.usefixtures("_mock_registry")
def test_pep514_parse_functions() -> None:
    from python_discovery._windows._pep514 import _parse_arch, _parse_version

    assert _parse_arch("64bit") == 64
    assert _parse_arch("32bit") == 32
    with pytest.raises(ValueError, match="invalid format"):
        _parse_arch("magic")
    with pytest.raises(ValueError, match="arch is not string"):
        _parse_arch(100)

    assert _parse_version("3.12") == (3, 12, None)
    assert _parse_version("3.12.1") == (3, 12, 1)
    assert _parse_version("3") == (3, None, None)
    with pytest.raises(ValueError, match="invalid format"):
        _parse_version("3.X")
    with pytest.raises(ValueError, match="version is not string"):
        _parse_version(2778)


@pytest.mark.skipif(sys.platform != "win32", reason="path joining differs on POSIX")
@pytest.mark.usefixtures("_mock_registry")
def test_pep514() -> None:
    from python_discovery._windows._pep514 import discover_pythons

    interpreters = list(discover_pythons())
    assert interpreters == [
        ("ContinuumAnalytics", 3, 10, 32, False, "C:\\Users\\user\\Miniconda3\\python.exe", None),
        ("ContinuumAnalytics", 3, 10, 64, False, "C:\\Users\\user\\Miniconda3-64\\python.exe", None),
        (
            "PythonCore",
            3,
            9,
            64,
            False,
            "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python39\\python.exe",
            None,
        ),
        (
            "PythonCore",
            3,
            9,
            64,
            False,
            "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python39\\python.exe",
            None,
        ),
        (
            "PythonCore",
            3,
            8,
            64,
            False,
            "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python38\\python.exe",
            None,
        ),
        (
            "PythonCore",
            3,
            9,
            64,
            False,
            "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python39\\python.exe",
            None,
        ),
        (
            "PythonCore",
            3,
            10,
            32,
            False,
            "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python310-32\\python.exe",
            None,
        ),
        (
            "PythonCore",
            3,
            12,
            64,
            False,
            "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python312\\python.exe",
            None,
        ),
        (
            "PythonCore",
            3,
            13,
            64,
            True,
            "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python313\\python3.13t.exe",
            None,
        ),
        ("CompanyA", 3, 6, 64, False, "Z:\\CompanyA\\Python\\3.6\\python.exe", None),
        ("PythonCore", 2, 7, 64, False, "C:\\Python27\\python.exe", None),
        ("PythonCore", 3, 7, 64, False, "C:\\Python37\\python.exe", None),
    ]


@pytest.mark.skipif(sys.platform != "win32", reason="path joining differs on POSIX")
@pytest.mark.usefixtures("_mock_registry")
def test_pep514_run(capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture) -> None:
    from python_discovery._windows._pep514 import _run

    _run()
    out, err = capsys.readouterr()
    py = r"C:\\Users\\user\\AppData\\Local\\Programs\\Python"
    expected = textwrap.dedent(
        rf"""
    ('CompanyA', 3, 6, 64, False, 'Z:\\CompanyA\\Python\\3.6\\python.exe', None)
    ('ContinuumAnalytics', 3, 10, 32, False, 'C:\\Users\\user\\Miniconda3\\python.exe', None)
    ('ContinuumAnalytics', 3, 10, 64, False, 'C:\\Users\\user\\Miniconda3-64\\python.exe', None)
    ('PythonCore', 2, 7, 64, False, 'C:\\Python27\\python.exe', None)
    ('PythonCore', 3, 10, 32, False, '{py}\\Python310-32\\python.exe', None)
    ('PythonCore', 3, 12, 64, False, '{py}\\Python312\\python.exe', None)
    ('PythonCore', 3, 13, 64, True, '{py}\\Python313\\python3.13t.exe', None)
    ('PythonCore', 3, 7, 64, False, 'C:\\Python37\\python.exe', None)
    ('PythonCore', 3, 8, 64, False, '{py}\\Python38\\python.exe', None)
    ('PythonCore', 3, 9, 64, False, '{py}\\Python39\\python.exe', None)
    ('PythonCore', 3, 9, 64, False, '{py}\\Python39\\python.exe', None)
    ('PythonCore', 3, 9, 64, False, '{py}\\Python39\\python.exe', None)
    """,
    ).strip()
    assert out.strip() == expected
    assert not err
    prefix = "PEP-514 violation in Windows Registry at "
    expected_logs = [
        f"{prefix}HKEY_CURRENT_USER/PythonCore/3.1/SysArchitecture error: invalid format magic",
        f"{prefix}HKEY_CURRENT_USER/PythonCore/3.2/SysArchitecture error: arch is not string: 100",
        f"{prefix}HKEY_CURRENT_USER/PythonCore/3.3 error: no ExecutablePath or default for it",
        f"{prefix}HKEY_CURRENT_USER/PythonCore/3.3 error: could not load exe with value None",
        f"{prefix}HKEY_CURRENT_USER/PythonCore/3.11/InstallPath error: missing",
        f"{prefix}HKEY_CURRENT_USER/PythonCore/3.12/SysVersion error: invalid format magic",
        f"{prefix}HKEY_CURRENT_USER/PythonCore/3.X/SysVersion error: version is not string: 2778",
        f"{prefix}HKEY_CURRENT_USER/PythonCore/3.X error: invalid format 3.X",
    ]
    assert caplog.messages == expected_logs


@pytest.mark.usefixtures("_mock_registry")
@pytest.mark.parametrize(
    ("executable_path", "install_path"),
    [
        pytest.param(r"%LOCALAPPDATA%\Programs\Python\Python311\python.exe", None, id="unexpanded-variable"),
        pytest.param("python.exe", None, id="bare-name"),
        pytest.param(r"bin\python.exe", None, id="relative"),
        pytest.param("C:python.exe", None, id="drive-relative"),
        pytest.param(r"\Python311\python.exe", None, id="current-drive"),
        pytest.param(42, None, id="integer-executable"),
        pytest.param(b"C:\\python.exe", None, id="bytes-executable"),
        pytest.param(["C:\\python.exe"], None, id="list-executable"),
        pytest.param(None, "", id="empty-install-path"),
        pytest.param(None, "Python311", id="relative-install-path"),
        pytest.param(None, 42, id="integer-install-path"),
    ],
)
def test_pep514_rejects_non_absolute_executable(
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
    executable_path: str | int | bytes | list[str] | None,
    install_path: str | int | None,
) -> None:
    from python_discovery._windows._pep514 import _load_exe

    registered = {"ExecutablePath": executable_path, None: install_path}
    mocker.patch(
        "python_discovery._windows._pep514.winreg.OpenKeyEx",
        return_value=mocker.create_autospec(AbstractContextManager, instance=True),
        autospec=True,
    )
    mocker.patch(
        "python_discovery._windows._pep514._get_value",
        side_effect=lambda _key, name: registered.get(name),
        autospec=True,
    )
    mocker.patch("python_discovery._windows._pep514.Path.exists", return_value=True, autospec=True)

    assert _load_exe("HKCU", "PythonCore", object(), "3.11") is None
    assert "expected an absolute executable path" in caplog.text


@pytest.fixture
def load_exe_with_args(mocker: MockerFixture) -> Callable[[str | int | None], tuple[str, str | None] | None]:
    from python_discovery._windows._pep514 import _load_exe

    mocker.patch(
        "python_discovery._windows._pep514.winreg.OpenKeyEx",
        return_value=mocker.create_autospec(AbstractContextManager, instance=True),
        autospec=True,
    )
    mocker.patch("python_discovery._windows._pep514._resolve_exe", return_value=r"C:\py.exe", autospec=True)
    mocker.patch("python_discovery._windows._pep514.Path.exists", return_value=True, autospec=True)

    def load(registered: str | int | None) -> tuple[str, str | None] | None:
        mocker.patch("python_discovery._windows._pep514._get_value", return_value=registered, autospec=True)
        return _load_exe("HKCU", "PythonCore", object(), "3.11")

    return load


@pytest.mark.usefixtures("_mock_registry")
@pytest.mark.parametrize(
    ("registered", "expected"),
    [
        pytest.param('-3.11 --config "a b"', '-3.11 --config "a b"', id="kept"),
        pytest.param(None, None, id="missing"),
        pytest.param("", None, id="empty"),
        pytest.param("   ", None, id="blank"),
    ],
)
def test_pep514_loads_executable_arguments(
    load_exe_with_args: Callable[[str | int | None], tuple[str, str | None] | None],
    registered: str | None,
    expected: str | None,
) -> None:
    assert load_exe_with_args(registered) == (r"C:\py.exe", expected)


@pytest.mark.usefixtures("_mock_registry")
def test_pep514_rejects_non_string_executable_arguments(
    load_exe_with_args: Callable[[str | int | None], tuple[str, str | None] | None],
) -> None:
    assert load_exe_with_args(42) is None


def _launcher_selects_311() -> bool:
    launcher = shutil.which("py")
    return launcher is not None and subprocess.run([launcher, "-3.11", "-c", "pass"], check=False).returncode == 0


@pytest.mark.skipif(
    sys.platform != "win32" or not _launcher_selects_311(), reason="requires the Windows launcher with Python 3.11"
)
def test_pep514_launcher_arguments_select_interpreter(mocker: MockerFixture, tmp_path: Path) -> None:
    from python_discovery import DiskCache
    from python_discovery._windows._propose import propose_interpreters

    launcher = shutil.which("py")
    assert launcher is not None
    script = (
        "import json, struct, sys; print(json.dumps([sys.executable, *sys.version_info[:2], struct.calcsize('P') * 8]))"
    )
    probe = subprocess.run([launcher, "-3.11", "-c", script], capture_output=True, text=True, check=True)
    selected, major, minor, arch = json.loads(probe.stdout)
    mocker.patch(
        "python_discovery._windows._propose.discover_pythons",
        return_value=[("PythonCore", major, minor, arch, False, launcher, "-3.11")],
        autospec=True,
    )

    info = next(propose_interpreters(PythonSpec.from_string_spec("python3.11"), DiskCache(tmp_path), os.environ))

    assert Path(info.executable).samefile(selected)
