from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from python_discovery import DiskCache, PythonInfo
from python_discovery._cached_py_info import (
    LogCmd,
    _get_via_file_cache,
    _load_cached_py_info,
    _resolve_py_info_script,
    _run_subprocess,
    gen_cookie,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def test_gen_cookie_length() -> None:
    cookie = gen_cookie()
    assert len(cookie) == 32


def test_log_cmd_repr() -> None:
    cmd = LogCmd(["python", "-c", "print('hello')"])
    assert "python" in repr(cmd)
    assert cmd.env is None


def test_log_cmd_repr_with_env() -> None:
    cmd = LogCmd(["python", "-c", "print('hello')"], env={"FOO": "bar"})
    result = repr(cmd)
    assert "python" in result
    assert "env of" in result
    assert "FOO" in result


def test_resolve_py_info_script_file_exists() -> None:
    with _resolve_py_info_script() as script:
        assert script.exists()
        assert script.name == "_py_info.py"


def test_resolve_py_info_script_fallback_to_pkgutil(mocker: MockerFixture) -> None:
    mocker.patch("python_discovery._cached_py_info.Path.is_file", return_value=False)
    mocker.patch("pkgutil.get_data", return_value=b"# mock script")
    with _resolve_py_info_script() as script:
        assert script.exists()
        content = script.read_text(encoding="utf-8")
        assert content == "# mock script"
    assert not script.exists()


def test_resolve_py_info_script_pkgutil_returns_none(mocker: MockerFixture) -> None:
    mocker.patch("python_discovery._cached_py_info.Path.is_file", return_value=False)
    mocker.patch("pkgutil.get_data", return_value=None)
    with pytest.raises(FileNotFoundError, match="cannot locate"), _resolve_py_info_script():
        pass  # pragma: no cover


def test_run_subprocess_success() -> None:
    failure, result = _run_subprocess(PythonInfo, sys.executable, dict(os.environ))
    assert failure is None
    assert result is not None
    assert isinstance(result, PythonInfo)


def test_run_subprocess_bad_exe() -> None:
    failure, result = _run_subprocess(PythonInfo, "/nonexistent/python", dict(os.environ))
    assert failure is not None
    assert result is None
    assert isinstance(failure, RuntimeError)


def test_run_subprocess_invalid_json(mocker: MockerFixture) -> None:
    mock_process = MagicMock()
    mock_process.communicate.return_value = ("not json", "")
    mock_process.returncode = 0
    mocker.patch("python_discovery._cached_py_info.Popen", return_value=mock_process)
    failure, result = _run_subprocess(PythonInfo, sys.executable, dict(os.environ))
    assert failure is not None
    assert result is None


def test_run_subprocess_with_cookies(mocker: MockerFixture) -> None:
    start_cookie = "a" * 32
    end_cookie = "b" * 32
    payload = json.dumps(PythonInfo().to_dict())
    out = f"pre{start_cookie[::-1]}{payload}{end_cookie[::-1]}post"

    mock_process = MagicMock()
    mock_process.communicate.return_value = (out, "")
    mock_process.returncode = 0
    mocker.patch("python_discovery._cached_py_info.Popen", return_value=mock_process)
    mocker.patch("python_discovery._cached_py_info.gen_cookie", side_effect=[start_cookie, end_cookie])

    with patch("sys.stdout") as mock_stdout:
        failure, result = _run_subprocess(PythonInfo, sys.executable, dict(os.environ))

    assert failure is None
    assert result is not None
    assert mock_stdout.write.call_count == 2


def test_run_subprocess_nonzero_exit(mocker: MockerFixture) -> None:
    mock_process = MagicMock()
    mock_process.communicate.return_value = ("some output", "some error")
    mock_process.returncode = 1
    mocker.patch("python_discovery._cached_py_info.Popen", return_value=mock_process)
    failure, result = _run_subprocess(PythonInfo, sys.executable, dict(os.environ))
    assert failure is not None
    assert "failed to query" in str(failure)
    assert result is None


def test_load_cached_py_info_valid() -> None:
    store = MagicMock()
    content = PythonInfo().to_dict()
    result = _load_cached_py_info(PythonInfo, store, content)
    assert result is not None
    assert isinstance(result, PythonInfo)


def test_load_cached_py_info_bad_data() -> None:
    store = MagicMock()
    result = _load_cached_py_info(PythonInfo, store, {"bad": "data"})
    assert result is None
    store.remove.assert_called_once()


def test_load_cached_py_info_system_exe_missing(mocker: MockerFixture) -> None:
    store = MagicMock()
    content = PythonInfo().to_dict()
    content["system_executable"] = "/nonexistent/python"
    mocker.patch("os.path.exists", return_value=False)
    result = _load_cached_py_info(PythonInfo, store, content)
    assert result is None
    store.remove.assert_called_once()


def test_get_via_file_cache_uses_cached(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    path = Path(sys.executable)
    env = dict(os.environ)

    result1 = _get_via_file_cache(PythonInfo, cache, path, sys.executable, env)
    assert isinstance(result1, PythonInfo)

    result2 = _get_via_file_cache(PythonInfo, cache, path, sys.executable, env)
    assert isinstance(result2, PythonInfo)


def test_get_via_file_cache_stale_hash(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    path = Path(sys.executable)
    env = dict(os.environ)

    result1 = _get_via_file_cache(PythonInfo, cache, path, sys.executable, env)
    assert isinstance(result1, PythonInfo)

    store = cache.py_info(path)
    data = store.read()
    assert data is not None
    data["hash"] = "stale_hash"
    store.write(data)

    result2 = _get_via_file_cache(PythonInfo, cache, path, sys.executable, env)
    assert isinstance(result2, PythonInfo)


def test_get_via_file_cache_nonexistent_path(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    path = Path(tmp_path / "nonexistent")
    env = dict(os.environ)
    result = _get_via_file_cache(PythonInfo, cache, path, str(path), env)
    assert isinstance(result, (PythonInfo, Exception))


def test_from_exe_retry_on_first_failure(
    tmp_path: Path, mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    cache = DiskCache(tmp_path)
    error = RuntimeError("fail")
    mocker.patch(
        "python_discovery._cached_py_info._run_subprocess",
        side_effect=[(error, None), (None, PythonInfo())],
    )
    result = _get_via_file_cache(PythonInfo, cache, Path("/fake"), "/fake", dict(os.environ))
    assert isinstance(result, PythonInfo)
    assert any("retrying" in r.message for r in caplog.records)


def test_get_via_file_cache_hash_oserror(tmp_path: Path, mocker: MockerFixture) -> None:
    cache = DiskCache(tmp_path)
    mocker.patch("python_discovery._cached_py_info.Path.read_bytes", side_effect=OSError("permission denied"))
    result = _get_via_file_cache(PythonInfo, cache, Path(sys.executable), sys.executable, dict(os.environ))
    assert isinstance(result, PythonInfo)


def test_get_via_file_cache_py_info_none(tmp_path: Path, mocker: MockerFixture) -> None:
    cache = DiskCache(tmp_path)
    mocker.patch(
        "python_discovery._cached_py_info._run_subprocess",
        return_value=(None, None),
    )
    result = _get_via_file_cache(PythonInfo, cache, Path("/fake"), "/fake", dict(os.environ))
    assert isinstance(result, RuntimeError)
