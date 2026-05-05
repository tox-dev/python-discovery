from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from python_discovery import DiskCache, PythonInfo, iter_interpreters
from python_discovery._discovery import IS_WIN

if TYPE_CHECKING:
    from collections.abc import Iterator

    import pytest
    from pytest_mock import MockerFixture


def test_iter_interpreters_with_abs_path_yields_one(session_cache: DiskCache) -> None:
    results = list(iter_interpreters(sys.executable, cache=session_cache))
    assert len(results) == 1
    assert results[0].executable == sys.executable


def test_iter_interpreters_predicate_filters_all(session_cache: DiskCache) -> None:
    results = list(iter_interpreters(sys.executable, cache=session_cache, predicate=lambda _: False))
    assert results == []


def test_iter_interpreters_predicate_keeps_all(session_cache: DiskCache) -> None:
    results = list(iter_interpreters(sys.executable, cache=session_cache, predicate=lambda _: True))
    assert len(results) == 1


def test_iter_interpreters_no_match(session_cache: DiskCache) -> None:
    results = list(iter_interpreters(uuid4().hex, cache=session_cache))
    assert results == []


def test_iter_interpreters_satisfies_filter_drops_all(session_cache: DiskCache) -> None:
    results = list(iter_interpreters(">=999", cache=session_cache))
    assert results == []


def test_iter_interpreters_no_key_includes_running_interpreter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    session_cache: DiskCache,
) -> None:
    monkeypatch.setenv("UV_PYTHON_INSTALL_DIR", str(tmp_path / "no-such-uv"))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    real_self = os.path.realpath(sys.executable)
    results = list(iter_interpreters(cache=session_cache))
    assert any(os.path.realpath(info.executable) == real_self for info in results)


def test_iter_interpreters_dedups_symlinks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    session_cache: DiskCache,
) -> None:
    suffix = ".exe" if IS_WIN else ""
    for name in ("python3", "python3.99"):
        Path(str(tmp_path / f"{name}{suffix}")).symlink_to(sys.executable)
    pyvenv_cfg = Path(sys.executable).parents[1] / "pyvenv.cfg"
    if pyvenv_cfg.exists():  # pragma: no branch
        (tmp_path / pyvenv_cfg.name).write_bytes(pyvenv_cfg.read_bytes())
    monkeypatch.setenv("UV_PYTHON_INSTALL_DIR", str(tmp_path / "no-such-uv"))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("PATH", os.pathsep.join([str(tmp_path), os.environ.get("PATH", "")]))

    real = os.path.realpath(sys.executable)
    matches = [info for info in iter_interpreters(cache=session_cache) if os.path.realpath(info.executable) == real]
    assert len(matches) == 1


def test_iter_interpreters_sequence_dedups_across_keys(session_cache: DiskCache) -> None:
    results = list(iter_interpreters([sys.executable, sys.executable], cache=session_cache))
    assert len(results) == 1


def test_iter_interpreters_try_first_with_yields_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    session_cache: DiskCache,
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("UV_PYTHON_INSTALL_DIR", str(tmp_path / "no-such-uv"))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    results = list(iter_interpreters(try_first_with=[sys.executable], cache=session_cache))
    assert results
    assert os.path.realpath(results[0].executable) == os.path.realpath(sys.executable)


def test_iter_interpreters_returns_iterator(session_cache: DiskCache) -> None:
    result: Iterator[PythonInfo] = iter_interpreters(sys.executable, cache=session_cache)
    assert iter(result) is result


def test_iter_interpreters_skips_none_from_propose(
    session_cache: DiskCache,
    mocker: MockerFixture,
) -> None:
    real_info = PythonInfo.current(session_cache)
    mocker.patch(
        "python_discovery._discovery.propose_interpreters",
        return_value=iter([(None, True), (real_info, True)]),
    )
    results = list(iter_interpreters(cache=session_cache))
    assert len(results) == 1
    assert results[0] is real_info


def test_iter_interpreters_skips_when_no_executable(
    session_cache: DiskCache,
    mocker: MockerFixture,
) -> None:
    bogus = mocker.MagicMock(spec=PythonInfo)
    bogus.system_executable = None
    bogus.executable = None
    mocker.patch(
        "python_discovery._discovery.propose_interpreters",
        return_value=iter([(bogus, True)]),
    )
    results = list(iter_interpreters(cache=session_cache))
    assert results == []


def test_iter_interpreters_uv_wide_pattern_finds_pypy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    session_cache: DiskCache,
    mocker: MockerFixture,
) -> None:
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("PATH", "")
    uv_dir = tmp_path / "uv-python"
    uv_dir.mkdir()
    monkeypatch.setenv("UV_PYTHON_INSTALL_DIR", str(uv_dir))

    pypy_bin = uv_dir / "pypy-3.10-linux-x86_64-gnu" / "bin"
    pypy_bin.mkdir(parents=True)
    pypy_exe = pypy_bin / "pypy"
    pypy_exe.touch()
    Path(str(pypy_bin / "python")).symlink_to(pypy_exe)

    mock_from_exe = mocker.patch("python_discovery._discovery.PathPythonInfo.from_exe", return_value=None)
    list(iter_interpreters(cache=session_cache))

    called_paths = {call.args[0] for call in mock_from_exe.call_args_list}
    assert str(pypy_bin / "python") in called_paths
    assert str(pypy_exe) not in called_paths
