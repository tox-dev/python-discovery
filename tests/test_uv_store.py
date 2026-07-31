from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

from python_discovery import get_interpreter
from python_discovery._discovery import IS_WIN

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytest_mock import MockerFixture

# no interpreter answers to this, so discovery walks every source instead of stopping at the running one
_NO_SUCH_VERSION: Final[str] = "3.99"


@pytest.fixture
def home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A throwaway home, with every directory variable uv consults pointed into it or unset."""
    for var in ("UV_PYTHON_INSTALL_DIR", "XDG_DATA_HOME", "APPDATA"):
        monkeypatch.delenv(var, raising=False)
    for var in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(var, str(tmp_path))
    monkeypatch.setenv("PATH", "")
    return tmp_path


@pytest.fixture
def plant() -> Callable[[Path], str]:
    """Create a uv install under a store root and return the executable discovery should reach for."""

    def _plant(root: Path) -> str:
        (bin_dir := root / "some-py-impl" / "bin").mkdir(parents=True)
        (executable := bin_dir / "python").touch()
        return str(executable)

    return _plant


@pytest.fixture
def probed(mocker: MockerFixture) -> Callable[..., list[str]]:
    """Run a discovery with the interrogation subprocess stubbed out, reporting the executables it reached for."""
    from_exe = mocker.patch("python_discovery._discovery.PathPythonInfo.from_exe", return_value=None)

    def _probed(**kwargs: object) -> list[str]:
        get_interpreter(_NO_SUCH_VERSION, [], **kwargs)
        return [call.args[0] for call in from_exe.call_args_list]

    return _probed


@pytest.mark.parametrize("expand_user", [True, False], ids=["expands-user", "absolute"])
def test_uv_store_install_dir_overrides_the_platform_default(
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    plant: Callable[[Path], str],
    probed: Callable[..., list[str]],
    expand_user: bool,
) -> None:
    monkeypatch.setenv("UV_PYTHON_INSTALL_DIR", "~/store" if expand_user else str(home / "store"))
    plant(home / ".local" / "share" / "uv" / "python")
    executable = plant(home / "store")

    assert probed() == [executable]


@pytest.mark.parametrize(
    ("platform", "extra_env", "expected"),
    [
        pytest.param("win32", {"APPDATA": "~/roaming"}, ["~/roaming/uv/data", "~/roaming/uv"], id="windows"),
        pytest.param("win32", {}, ["~/AppData/Roaming/uv/data", "~/AppData/Roaming/uv"], id="windows-without-appdata"),
        pytest.param("darwin", {}, ["~/Library/Application Support/uv", "~/.local/share/uv"], id="macos"),
        pytest.param(
            "darwin",
            {"XDG_DATA_HOME": "~/xdg"},
            ["~/Library/Application Support/uv", "~/xdg/uv"],
            id="macos-with-xdg",
        ),
        pytest.param("linux", {}, ["~/.local/share/uv"], id="linux"),
        pytest.param("linux", {"XDG_DATA_HOME": "~/xdg"}, ["~/xdg/uv"], id="linux-with-xdg"),
        pytest.param("linux", {"XDG_DATA_HOME": "relative"}, ["~/.local/share/uv"], id="linux-ignores-relative-xdg"),
    ],
)
@pytest.mark.usefixtures("home")
def test_uv_store_roots_per_platform(
    monkeypatch: pytest.MonkeyPatch,
    plant: Callable[[Path], str],
    probed: Callable[..., list[str]],
    platform: str,
    extra_env: dict[str, str],
    expected: list[str],
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    for name, value in extra_env.items():
        monkeypatch.setenv(name, str(Path(value).expanduser()))
    executables = [plant(Path(state_dir).expanduser() / "python") for state_dir in expected]

    assert probed() == executables


def test_uv_store_windows_ignores_xdg_data_home(
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    plant: Callable[[Path], str],
    probed: Callable[..., list[str]],
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("XDG_DATA_HOME", str(home / "xdg"))
    plant(home / "xdg" / "uv" / "python")
    executable = plant(home / "AppData" / "Roaming" / "uv" / "python")

    assert probed() == [executable]


def test_uv_store_reads_the_env_argument(
    home: Path, plant: Callable[[Path], str], probed: Callable[..., list[str]]
) -> None:
    executable = plant(home / "store")

    assert probed(env={"PATH": "", "UV_PYTHON_INSTALL_DIR": str(home / "store")}) == [executable]


@pytest.mark.usefixtures("home")
def test_uv_store_missing_root_is_not_an_error(probed: Callable[..., list[str]]) -> None:
    assert probed() == []


def test_uv_store_is_searched_after_path(
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    plant: Callable[[Path], str],
    probed: Callable[..., list[str]],
) -> None:
    store_executable = plant(home / ".local" / "share" / "uv" / "python")
    (path_dir := home / "path-bin").mkdir()
    (path_executable := path_dir / f"python{_NO_SUCH_VERSION}{'.exe' if IS_WIN else ''}").touch()
    monkeypatch.setenv("PATH", str(path_dir))

    assert probed() == [str(path_executable), store_executable]
