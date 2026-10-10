from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

import pytest

from python_discovery import DiskCache, PythonInfo

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("[]", id="list"),
        pytest.param('"python"', id="string"),
        pytest.param("3", id="number"),
        pytest.param("true", id="bool"),
        pytest.param("null", id="null"),
    ],
)
def test_from_exe_recovers_non_object_cache(cached_interpreter: tuple[DiskCache, Path, dict], payload: str) -> None:
    cache, cache_file, expected = cached_interpreter
    cache_file.write_text(payload, encoding="utf-8")
    result = PythonInfo.from_exe(sys.executable, cache, ignore_cache=True, resolve_to_host=False)
    assert result is not None
    assert (json.loads(result.to_json()), json.loads(cache_file.read_text(encoding="utf-8"))) == (
        expected["content"],
        expected,
    )


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(None, id="missing"),
        pytest.param("5", id="int"),
        pytest.param('["python"]', id="list"),
        pytest.param("{}", id="dict"),
        pytest.param("true", id="bool"),
        pytest.param('""', id="empty"),
        pytest.param('"."', id="directory"),
        pytest.param('"missing-python"', id="nonexistent"),
        pytest.param('"python\\u0000"', id="nul"),
        pytest.param(json.dumps("a" * 1024), id="path-too-long"),
    ],
)
def test_from_exe_recovers_invalid_system_executable(
    cached_interpreter: tuple[DiskCache, Path, dict], payload: str | None
) -> None:
    cache, cache_file, expected = cached_interpreter
    data = json.loads(cache_file.read_text(encoding="utf-8"))
    if payload is None:
        del data["content"]["system_executable"]
    else:
        data["content"]["system_executable"] = json.loads(payload)
    cache_file.write_text(json.dumps(data), encoding="utf-8")
    result = PythonInfo.from_exe(sys.executable, cache, ignore_cache=True, resolve_to_host=False)
    assert result is not None
    assert (json.loads(result.to_json()), json.loads(cache_file.read_text(encoding="utf-8"))) == (
        expected["content"],
        expected,
    )


@pytest.fixture
def cached_interpreter(tmp_path: Path) -> tuple[DiskCache, Path, dict]:
    cache = DiskCache(tmp_path)
    assert PythonInfo.from_exe(sys.executable, cache, ignore_cache=True, resolve_to_host=False) is not None
    cache_file = next(tmp_path.rglob("*.json"))
    return cache, cache_file, json.loads(cache_file.read_text(encoding="utf-8"))
