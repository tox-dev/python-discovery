from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from io import StringIO
from os import read
from pathlib import Path
from subprocess import DEVNULL, PIPE, Popen, TimeoutExpired, list2cmdline
from threading import enumerate as active_threads
from time import monotonic
from typing import TYPE_CHECKING, Final
from unittest.mock import MagicMock, patch

import pytest

from python_discovery import DiskCache, PythonInfo
from python_discovery._cached_py_info import (
    _MAX_QUERY_OUTPUT,
    LogCmd,
    _collect_query_output,
    _get_from_cache,
    _get_via_file_cache,
    _load_cached_py_info,
    _resolve_py_info_script,
    _run_subprocess,
    _script_hash,
    gen_cookie,
)

if TYPE_CHECKING:
    from typing import IO

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
        assert script.name == "_py_info_collect.py"


def test_resolve_py_info_script_fallback_to_pkgutil(mocker: MockerFixture) -> None:
    mocker.patch("python_discovery._cached_py_info.Path.is_file", return_value=False)
    mocker.patch("pkgutil.get_data", return_value=b"# mock script")
    with _resolve_py_info_script() as script:
        assert script.exists()
        content = script.read_text(encoding="utf-8")
        assert content == "# mock script"
        assert script.parent != Path(tempfile.gettempdir())
        assert list(script.parent.iterdir()) == [script]
    assert not script.parent.exists()


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
    mocker.patch("python_discovery._cached_py_info.Popen", return_value=_mock_process("not json", "", 0))
    failure, result = _run_subprocess(PythonInfo, sys.executable, dict(os.environ))
    assert failure is not None
    assert result is None


@pytest.mark.parametrize(
    "output",
    [
        pytest.param("{}", id="empty-object"),
        pytest.param(
            '{"version_info": {"major": 3, "minor": 11, "micro": 0, "releaselevel": "final", "serial": 0}}',
            id="version-only",
        ),
        pytest.param("[]", id="array"),
    ],
)
def test_from_exe_rejects_wrong_shape_json(tmp_path: Path, mocker: MockerFixture, output: str) -> None:
    start_cookie, end_cookie = "a" * 32, "b" * 32
    wrapped = f"{start_cookie}{output}{end_cookie}"
    mocker.patch(
        "python_discovery._cached_py_info.Popen",
        side_effect=[_mock_process(wrapped, "", 0), _mock_process(wrapped, "", 0)],
    )
    mocker.patch("python_discovery._cached_py_info.gen_cookie", side_effect=[start_cookie, end_cookie] * 2)
    assert PythonInfo.from_exe(str(tmp_path / "python"), raise_on_error=False, ignore_cache=True) is None


def test_from_exe_rejects_json_without_cookies(tmp_path: Path, mocker: MockerFixture) -> None:
    output = PythonInfo().to_json()
    mocker.patch(
        "python_discovery._cached_py_info.Popen",
        side_effect=[_mock_process(output, "", 0), _mock_process(output, "", 0)],
    )
    assert PythonInfo.from_exe(str(tmp_path / "python"), raise_on_error=False, ignore_cache=True) is None


def _mock_process(out: str, err: str, code: int) -> MagicMock:
    streams: list[IO[str]] = []
    for value in (out, err):
        read_fd, write_fd = os.pipe()
        with os.fdopen(write_fd, "wb") as writer:
            writer.write(value.encode())
        streams.append(os.fdopen(read_fd, "r", encoding="utf-8"))
    return MagicMock(stdout=streams[0], stderr=streams[1], returncode=code, **{"wait.return_value": code})


def test_run_subprocess_with_cookies(mocker: MockerFixture) -> None:
    start_cookie = "a" * 32
    end_cookie = "b" * 32
    payload = json.dumps(PythonInfo().to_dict())
    out = f"pre{start_cookie[::-1]}{payload}{end_cookie[::-1]}post"

    mocker.patch("python_discovery._cached_py_info.Popen", return_value=_mock_process(out, "", 0))
    mocker.patch("python_discovery._cached_py_info.gen_cookie", side_effect=[start_cookie, end_cookie])

    with patch("sys.stdout") as mock_stdout:
        failure, result = _run_subprocess(PythonInfo, sys.executable, dict(os.environ))

    assert failure is None
    assert result is not None
    assert mock_stdout.write.call_count == 2


def test_run_subprocess_timeout(mocker: MockerFixture) -> None:
    mocker.patch("python_discovery._cached_py_info._collect_query_output", return_value=("", "timed out", -1))
    failure, result = _run_subprocess(PythonInfo, sys.executable, dict(os.environ))
    assert failure is not None
    assert "timed out" in str(failure)
    assert result is None


def test_run_subprocess_nonzero_exit(mocker: MockerFixture) -> None:
    mocker.patch("python_discovery._cached_py_info.Popen", return_value=_mock_process("some output", "some error", 1))
    failure, result = _run_subprocess(PythonInfo, sys.executable, dict(os.environ))
    assert failure is not None
    assert "failed to query" in str(failure)
    assert result is None


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX executable script")
@pytest.mark.parametrize("stream", [pytest.param("stdout", id="stdout"), pytest.param("stderr", id="stderr")])
def test_run_subprocess_rejects_large_output(tmp_path: Path, stream: str) -> None:
    exe = tmp_path / "python"
    exe.write_text(
        f"#!{sys.executable}\nimport sys\nsys.{stream}.write('x' * {_MAX_QUERY_OUTPUT + 1})\n",
        encoding="utf-8",
    )
    exe.chmod(0o755)

    failure, result = _run_subprocess(PythonInfo, str(exe), dict(os.environ))
    assert result is None
    assert failure is not None
    assert "produced more than" in str(failure)


@pytest.mark.parametrize("stream", [pytest.param("stdout", id="stdout"), pytest.param("stderr", id="stderr")])
@pytest.mark.parametrize("timeout", [pytest.param(15, id="finite-timeout"), pytest.param(None, id="no-timeout")])
def test_collect_query_output_limit(stream: str, timeout: float | None) -> None:
    code = f"import sys; sys.{stream}.write('x' * {_MAX_QUERY_OUTPUT + 1})"
    process = Popen([sys.executable, "-c", code], stdin=DEVNULL, stdout=PIPE, stderr=PIPE, text=True)
    assert _collect_query_output(process, timeout) == (
        "",
        f"produced more than {_MAX_QUERY_OUTPUT} characters of output",
        -1,
    )


def test_collect_query_output_normalizes_trailing_newline() -> None:
    assert _collect_query_output(_mock_process("\r", "", 0), 1) == ("\n", "", 0)


def test_collect_query_output_decodes_split_utf8() -> None:
    with patch("python_discovery._cached_py_info.os.read", side_effect=lambda fd, _: read(fd, 1)):
        assert _collect_query_output(_mock_process("é", "", 0), 1) == ("é", "", 0)


@pytest.mark.parametrize(
    "code",
    [
        pytest.param("import time; time.sleep(2)", id="pipes-open"),
        pytest.param("import sys,time; sys.stdout.close(); sys.stderr.close(); time.sleep(2)", id="pipes-closed"),
    ],
)
def test_collect_query_output_timeout(code: str) -> None:
    process = Popen([sys.executable, "-c", code], stdin=DEVNULL, stdout=PIPE, stderr=PIPE, text=True)
    assert _collect_query_output(process, 0.1) == ("", "timed out", -1)


def test_collect_query_output_timeout_reaps_readers() -> None:
    code = (
        "import subprocess, sys\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(10)'], "
        "stdin=subprocess.DEVNULL, stdout=sys.stdout, stderr=sys.stderr)\n"
    )
    process = Popen([sys.executable, "-c", code], stdin=DEVNULL, stdout=PIPE, stderr=PIPE, text=True)
    process.wait(timeout=5)
    before = set(active_threads())
    started = monotonic()

    assert _collect_query_output(process, 0.1) == ("", "timed out", -1)
    assert monotonic() - started < 2.5
    assert not set(active_threads()) - before


def test_collect_query_output_timeout_after_eof(mocker: MockerFixture) -> None:
    process = Popen([sys.executable, "-c", ""], stdin=DEVNULL, stdout=PIPE, stderr=PIPE, text=True)
    process.wait(timeout=5)
    mocker.patch.object(process, "wait", side_effect=[TimeoutExpired("python", 0), 0])
    mocker.patch.object(process, "kill")

    assert _collect_query_output(process, 1) == ("", "timed out", -1)
    process.kill.assert_called_once()


def test_collect_query_output_read_error(mocker: MockerFixture) -> None:
    process = Popen([sys.executable, "-c", ""], stdin=DEVNULL, stdout=PIPE, stderr=PIPE, text=True)
    process.wait(timeout=5)
    mocker.patch("python_discovery._cached_py_info.os.read", side_effect=OSError("broken pipe"))
    mocker.patch.object(process, "kill")

    with pytest.raises(OSError, match="broken pipe"):
        _collect_query_output(process, 1)
    process.kill.assert_called()


@pytest.mark.parametrize(
    ("stdout", "stderr"),
    [
        pytest.param(None, StringIO(""), id="stdout"),
        pytest.param(StringIO(""), None, id="stderr"),
    ],
)
def test_collect_query_output_requires_pipes(stdout: StringIO | None, stderr: StringIO | None) -> None:
    process = MagicMock(stdout=stdout, stderr=stderr)

    with pytest.raises(ValueError, match="query output pipes are required"):
        _collect_query_output(process, 1)


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
    _script_hash.cache_clear()
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


def _write_fake_python(tmp_path: Path, stderr: str, code: int = 79) -> Path:
    """A stand-in interpreter: logs every invocation, then fails interrogation with the given stderr and exit code."""
    exe = tmp_path / "python"
    exe.write_text(f'#!/bin/sh\necho "$@" >> "$0.log"\necho "{stderr}" >&2\nexit {code}\n')
    exe.chmod(0o755)
    return exe


def _interrogations(exe: Path) -> list[str]:
    return Path(f"{exe}.log").read_text(encoding="utf-8").splitlines()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell fake interpreter")
def test_from_exe_too_old_python_warns(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    exe = _write_fake_python(tmp_path, stderr="unsupported Python version 3.5.10")
    assert PythonInfo.from_exe(str(exe), raise_on_error=False, ignore_cache=True) is None
    record = next(iter(caplog.records))
    assert record.levelno == logging.WARNING
    assert record.getMessage() == f"{exe} is Python 3.5.10, older than the minimum 3.6 python-discovery can query"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell fake interpreter")
def test_from_exe_too_old_python_skips_retry(tmp_path: Path) -> None:
    exe = _write_fake_python(tmp_path, stderr="unsupported Python version 3.5.10")
    PythonInfo.from_exe(str(exe), raise_on_error=False, ignore_cache=True)
    assert len(_interrogations(exe)) == 1


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell fake interpreter")
def test_from_exe_too_old_python_raises_by_default(tmp_path: Path) -> None:
    exe = _write_fake_python(tmp_path, stderr="unsupported Python version 3.5.10")
    with pytest.raises(RuntimeError, match=r"older than the minimum 3\.6 python-discovery can query"):
        PythonInfo.from_exe(str(exe), ignore_cache=True)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell fake interpreter")
def test_from_exe_too_old_python_verdict_cached(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    cache = DiskCache(tmp_path / "cache")
    exe = _write_fake_python(tmp_path, stderr="unsupported Python version 3.5.10\n$0")
    assert PythonInfo.from_exe(str(exe), cache, raise_on_error=False, ignore_cache=True) is None
    assert PythonInfo.from_exe(str(exe), cache, raise_on_error=False, ignore_cache=True) is None
    assert len(_interrogations(exe)) == 1
    assert len([record for record in caplog.records if record.levelno == logging.WARNING]) == 1


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell fake interpreter")
def test_from_exe_too_old_python_shim_verdict_not_cached(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path / "cache")
    exe = _write_fake_python(tmp_path, stderr=f"unsupported Python version 3.5.10\n{sys.executable}")

    assert PythonInfo.from_exe(str(exe), cache, raise_on_error=False, ignore_cache=True) is None
    assert PythonInfo.from_exe(str(exe), cache, raise_on_error=False, ignore_cache=True) is None
    assert len(_interrogations(exe)) == 2


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX executable script")
@pytest.mark.parametrize("ignore_cache", [pytest.param(False, id="memory"), pytest.param(True, id="disk")])
def test_from_exe_shim_result_changes_with_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ignore_cache: bool
) -> None:
    shim = tmp_path / "shim"
    shim.write_text(
        f"#!{sys.executable}\n"
        "from runpy import run_path\nimport sys\nfrom pathlib import Path\n"
        "sys.prefix = (Path.cwd() / '.python-version').read_text(encoding='utf-8').strip()\n"
        "run_path(sys.argv.pop(1), run_name='__main__')\n",
        encoding="utf-8",
    )
    shim.chmod(0o755)
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / ".python-version").write_text(str(first), encoding="utf-8")
    (second / ".python-version").write_text(str(second), encoding="utf-8")
    cache = DiskCache(tmp_path / "cache")

    monkeypatch.chdir(first)
    earlier = PythonInfo.from_exe(str(shim), cache, ignore_cache=ignore_cache, resolve_to_host=False)
    monkeypatch.chdir(second)
    later = PythonInfo.from_exe(str(shim), cache, ignore_cache=ignore_cache, resolve_to_host=False)

    assert earlier is not None
    assert later is not None
    assert (earlier.prefix, later.prefix) == (str(first), str(second))


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell fake interpreter")
def test_from_exe_marker_without_version(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    exe = _write_fake_python(tmp_path, stderr="unsupported Python version ")
    assert PythonInfo.from_exe(str(exe), raise_on_error=False, ignore_cache=True) is None
    record = next(iter(caplog.records))
    assert record.getMessage() == f"{exe} is Python unknown, older than the minimum 3.6 python-discovery can query"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell fake interpreter")
@pytest.mark.parametrize(
    ("stderr", "code"),
    [
        pytest.param("SyntaxError: invalid syntax", 1, id="syntax-error"),
        pytest.param("unsupported Python version 3.5.10", 1, id="marker-wrong-exit-code"),
        pytest.param("something crashed", 79, id="exit-code-without-marker"),
    ],
)
def test_from_exe_query_failure_retries(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, stderr: str, code: int
) -> None:
    caplog.set_level(logging.INFO)
    exe = _write_fake_python(tmp_path, stderr=stderr, code=code)
    assert PythonInfo.from_exe(str(exe), raise_on_error=False, ignore_cache=True) is None
    assert not [record for record in caplog.records if record.levelno == logging.WARNING]
    assert any("failed to query" in record.getMessage() for record in caplog.records)
    assert len(_interrogations(exe)) == 2


def test_from_exe_cache_entry_with_bad_content(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    path = Path(sys.executable)
    env = dict(os.environ)
    result = _get_via_file_cache(PythonInfo, cache, path, sys.executable, env)
    assert isinstance(result, PythonInfo)

    store = cache.py_info(path)
    data = store.read()
    assert data is not None
    data["content"] = "garbage"
    store.write(data)

    required = _get_via_file_cache(PythonInfo, cache, path, sys.executable, env)
    assert isinstance(required, PythonInfo)
    assert isinstance(store.read(), dict)


@pytest.mark.parametrize(
    ("folder", "suffix"),
    [
        pytest.param(".", ".json", id="entry"),
        pytest.param("locks-v2" if os.name == "posix" else ".", ".lock", id="lock"),
    ],
)
def test_from_exe_recovers_unusable_cache_path(tmp_path: Path, folder: str, suffix: str) -> None:
    cache = DiskCache(tmp_path)
    expected = PythonInfo.from_exe(sys.executable, cache, ignore_cache=True, resolve_to_host=False)
    assert expected is not None
    entry = next(tmp_path.rglob("*.json"))
    blocked = entry.parent / folder / f"{entry.stem}{suffix}"
    blocked.unlink(missing_ok=True)
    blocked.mkdir()

    result = PythonInfo.from_exe(sys.executable, cache, ignore_cache=True, resolve_to_host=False)
    assert result is not None
    assert result.version_info == expected.version_info


_LAUNCHER: Final[str] = r"C:\Program Files\Python Launcher\py.exe"
_ARGS: Final[str] = '-3.11 --config "settings folder\\python.json"'
_SELECTED: Final[str] = r"C:\Python311\python.exe"


@pytest.fixture
def popen(mocker: MockerFixture) -> MagicMock:
    start, end = "a" * 32, "b" * 32
    mocker.patch("python_discovery._cached_py_info.gen_cookie", side_effect=[start, end])
    info = PythonInfo()
    info.executable = _SELECTED
    out = f"{start[::-1]}{info.to_json()}{end[::-1]}"
    process = _mock_process(out, "", 0)
    return mocker.patch("python_discovery._cached_py_info.Popen", return_value=process)


def test_executable_args_precede_query_script(popen: MagicMock) -> None:
    _run_subprocess(PythonInfo, _LAUNCHER, dict(os.environ), _ARGS)

    cmd = popen.call_args.args[0]
    assert cmd.startswith(f"{list2cmdline([_LAUNCHER])} {_ARGS} ")
    assert cmd.endswith(f" {'a' * 32} {'b' * 32}")


@pytest.mark.usefixtures("popen")
def test_executable_args_report_the_selected_interpreter() -> None:
    failure, result = _run_subprocess(PythonInfo, _LAUNCHER, dict(os.environ), _ARGS)

    assert failure is None
    assert result is not None
    assert result.executable == _SELECTED


def test_executable_args_disk_entry_not_reused_without_args(tmp_path: Path, mocker: MockerFixture) -> None:
    with_args, without_args = PythonInfo(), PythonInfo()
    with_args.executable = "selected"
    query = mocker.patch(
        "python_discovery._cached_py_info._run_subprocess",
        side_effect=[(None, with_args), (None, without_args)],
    )
    cache, path, env = DiskCache(tmp_path), Path(sys.executable), dict(os.environ)
    _get_via_file_cache(PythonInfo, cache, path, sys.executable, env, executable_args=_ARGS)

    result = _get_via_file_cache(PythonInfo, cache, path, sys.executable, env)

    assert result is without_args
    assert query.call_count == 2


def test_executable_args_memory_cache_keyed_by_args(tmp_path: Path, mocker: MockerFixture) -> None:
    mocker.patch.dict("python_discovery._cached_py_info._CACHE", clear=True)
    first, second = PythonInfo(), PythonInfo()
    query = mocker.patch("python_discovery._cached_py_info._get_via_file_cache", side_effect=[first, second])
    cache, env = DiskCache(tmp_path), dict(os.environ)

    results = [
        _get_from_cache(PythonInfo, cache, sys.executable, env, ignore_cache=False, executable_args=args)
        for args in ("-3.11", "-3.12", "-3.11")
    ]

    assert results == [first, second, first]
    assert query.call_count == 2
