from __future__ import annotations

import logging
import os
import sys
from time import monotonic
from typing import TYPE_CHECKING

import pytest

from python_discovery import PythonInfo
from python_discovery._cached_py_info import _collect_query_output

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(None, 15.0, id="default"),
        pytest.param("30", 30.0, id="seconds"),
        pytest.param(" 0.5 ", 0.5, id="padded-fraction"),
        pytest.param("inf", None, id="inf"),
        pytest.param("1e30", None, id="beyond-platform-wait"),
        pytest.param("2147483.647", 2147483.647, id="wait-limit"),
        pytest.param("2147483.648", None, id="above-wait-limit"),
    ],
)
def test_from_exe_query_timeout(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture, raw: str | None, expected: float | None
) -> None:
    collect = mocker.patch("python_discovery._cached_py_info._collect_query_output", wraps=_collect_query_output)
    env = {key: value for key, value in os.environ.items() if key != "PY_DISCOVERY_TIMEOUT"}
    if raw is not None:
        env["PY_DISCOVERY_TIMEOUT"] = raw
    result = PythonInfo.from_exe(sys.executable, env=env, ignore_cache=True, resolve_to_host=False)
    assert result is not None
    assert result.version_info == sys.version_info
    assert collect.call_args_list[0].args[1] == expected
    assert not caplog.records


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("", id="empty"),
        pytest.param("abc", id="words"),
        pytest.param("0x10", id="hex"),
        pytest.param("nan", id="nan"),
        pytest.param("0", id="zero"),
        pytest.param("-1", id="negative"),
        pytest.param("-inf", id="negative-inf"),
        pytest.param("1e-999", id="underflow"),
    ],
)
def test_from_exe_invalid_timeout_warns_once(mocker: MockerFixture, caplog: pytest.LogCaptureFixture, raw: str) -> None:
    collect = mocker.patch("python_discovery._cached_py_info._collect_query_output", wraps=_collect_query_output)
    env = {**os.environ, "PY_DISCOVERY_TIMEOUT": raw}
    for _ in range(2):
        result = PythonInfo.from_exe(sys.executable, env=env, ignore_cache=True, resolve_to_host=False)
        assert result is not None
        assert result.version_info == sys.version_info
    assert [call.args[1] for call in collect.call_args_list] == [15.0] * 2
    assert [(record.levelno, record.getMessage()) for record in caplog.records] == [
        (logging.WARNING, f"ignoring PY_DISCOVERY_TIMEOUT={raw!r}, not a positive number of seconds; using 15.0")
    ]


def test_from_exe_timeout_warning_cache_is_bounded(caplog: pytest.LogCaptureFixture) -> None:
    for index in range(129):
        result = PythonInfo.from_exe(
            sys.executable,
            env={**os.environ, "PY_DISCOVERY_TIMEOUT": f"invalid-timeout-{index}"},
            ignore_cache=True,
            resolve_to_host=False,
        )
        assert result is not None
        assert result.version_info == sys.version_info
    caplog.clear()
    for raw in ("invalid-timeout-128", "invalid-timeout-0"):
        result = PythonInfo.from_exe(
            sys.executable, env={**os.environ, "PY_DISCOVERY_TIMEOUT": raw}, ignore_cache=True, resolve_to_host=False
        )
        assert result is not None
        assert result.version_info == sys.version_info
    assert [record.getMessage() for record in caplog.records] == [
        "ignoring PY_DISCOVERY_TIMEOUT='invalid-timeout-0', not a positive number of seconds; using 15.0"
    ]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell launcher")
def test_from_exe_timeout_with_inherited_pipes(tmp_path: Path) -> None:
    executable = tmp_path / "python3.11"
    executable.write_text("#!/bin/sh\n/bin/sleep 3 &\nexit 0\n")
    executable.chmod(0o755)

    started = monotonic()
    result = PythonInfo.from_exe(
        str(executable),
        env={**os.environ, "PY_DISCOVERY_TIMEOUT": "0.1"},
        ignore_cache=True,
        raise_on_error=False,
        resolve_to_host=False,
    )

    assert result is None
    assert monotonic() - started < 2.5
