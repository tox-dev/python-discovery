from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from threading import Event, Thread
from typing import TYPE_CHECKING

import pytest
from filelock import FileLock

from python_discovery._cache import DiskCache, DiskContentStore, NoOpCache, NoOpContentStore

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def test_disk_content_store_read_valid_json(tmp_path: Path) -> None:
    store = DiskContentStore(tmp_path, "test")
    data = {"key": "value"}
    store.write(data)
    assert store.read() == data


def test_disk_content_store_read_invalid_json(tmp_path: Path) -> None:
    store = DiskContentStore(tmp_path, "test")
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "test.json").write_text("not json", encoding="utf-8")
    assert store.read() is None
    assert not (tmp_path / "test.json").exists()


def test_disk_content_store_read_missing_file(tmp_path: Path) -> None:
    store = DiskContentStore(tmp_path, "test")
    assert store.read() is None


def test_disk_content_store_remove(tmp_path: Path) -> None:
    store = DiskContentStore(tmp_path, "test")
    store.write({"key": "value"})
    assert store.exists()
    store.remove()
    assert not store.exists()


def test_disk_content_store_remove_missing_file(tmp_path: Path) -> None:
    store = DiskContentStore(tmp_path, "test")
    store.remove()


def test_disk_content_store_locked(tmp_path: Path) -> None:
    store = DiskContentStore(tmp_path, "test")
    with store.locked():
        store.write({"key": "value"})
    assert store.read() == {"key": "value"}


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX lock permissions")
@pytest.mark.parametrize(
    ("folder_mode", "umask", "lock_folder_mode", "lock_mode"),
    [
        pytest.param(0o755, 0o022, 0o700, 0o600, id="private"),
        pytest.param(0o770, 0o002, 0o770, 0o660, id="group-shared"),
    ],
)
def test_disk_content_store_lock_permissions(
    tmp_path: Path, folder_mode: int, umask: int, lock_folder_mode: int, lock_mode: int
) -> None:
    tmp_path.chmod(folder_mode)
    previous = os.umask(umask)
    try:
        with DiskContentStore(tmp_path, "test").locked():
            pass
    finally:
        os.umask(previous)
    assert (
        stat.S_IMODE((tmp_path / "locks-v2").stat().st_mode),
        stat.S_IMODE((tmp_path / "locks-v2" / "test.lock").stat().st_mode),
    ) == (lock_folder_mode, lock_mode)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX lock migration")
def test_disk_content_store_ignores_legacy_lock(tmp_path: Path) -> None:
    entered = Event()
    store = DiskContentStore(tmp_path, "test")

    def acquire() -> None:
        with store.locked():
            entered.set()

    thread = Thread(target=acquire)
    with FileLock(str(tmp_path / "test.lock")):
        thread.start()
        acquired = entered.wait(3)
    thread.join(timeout=3)
    assert acquired


def test_disk_content_store_keeps_lock_path_without_posix(tmp_path: Path, mocker: MockerFixture) -> None:
    platform_os = mocker.patch("python_discovery._cache.os", autospec=True)
    platform_os.name = "nt"
    with DiskContentStore(tmp_path, "test").locked():
        pass
    assert (tmp_path / "test.lock").exists()
    assert not (tmp_path / "locks-v2").exists()


def test_disk_content_store_exists(tmp_path: Path) -> None:
    store = DiskContentStore(tmp_path, "test")
    assert store.exists() is False
    store.write({"key": "value"})
    assert store.exists() is True


def test_disk_cache_py_info(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    store = cache.py_info(Path("/some/path"))
    assert isinstance(store, DiskContentStore)


def test_disk_cache_py_info_clear(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    store = cache.py_info(Path("/some/path"))
    store.write({"key": "value"})
    assert store.exists()
    cache.py_info_clear()
    assert not store.exists()


def test_disk_cache_py_info_clear_empty(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    cache.py_info_clear()


def test_disk_cache_py_info_clear_skips_non_json(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    py_info_dir = tmp_path / "py_info" / "4"
    py_info_dir.mkdir(parents=True)
    (py_info_dir / "test.json").write_text("{}", encoding="utf-8")
    (py_info_dir / "notjson.txt").touch()
    cache.py_info_clear()
    remaining = [entry.name for entry in py_info_dir.iterdir()]
    assert "notjson.txt" in remaining
    assert "test.json" not in remaining


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX ownership and modes")
@pytest.mark.parametrize("unsafe", [pytest.param("", id="root"), pytest.param("py_info/4", id="entry-dir")])
def test_disk_cache_skips_writable_directory(tmp_path: Path, unsafe: str) -> None:
    folder = tmp_path / unsafe
    folder.mkdir(parents=True, exist_ok=True)
    folder.chmod(0o777)
    assert isinstance(DiskCache(tmp_path).py_info(Path("/some/path")), NoOpContentStore)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX ownership and modes")
def test_disk_cache_skips_linked_directory(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (tmp_path / "py_info").symlink_to(target, target_is_directory=True)
    assert isinstance(DiskCache(tmp_path).py_info(Path("/some/path")), NoOpContentStore)
    assert not (target / "4").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX ownership and modes")
def test_disk_cache_skips_writable_ancestor(tmp_path: Path) -> None:
    ancestor = tmp_path / "shared"
    ancestor.mkdir()
    ancestor.chmod(0o777)
    assert isinstance(DiskCache(ancestor / "cache").py_info(Path("/some/path")), NoOpContentStore)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX ownership and modes")
def test_disk_cache_skips_file_as_root(tmp_path: Path) -> None:
    root = tmp_path / "file"
    root.touch()
    assert isinstance(DiskCache(root).py_info(Path("/some/path")), NoOpContentStore)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX ownership and modes")
def test_disk_cache_skips_uncreatable_directory(tmp_path: Path, mocker: MockerFixture) -> None:
    mocker.patch.object(Path, "mkdir", side_effect=PermissionError)
    assert isinstance(DiskCache(tmp_path / "cache").py_info(Path("/some/path")), NoOpContentStore)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX ownership and modes")
def test_disk_cache_skips_foreign_directory(tmp_path: Path, mocker: MockerFixture) -> None:
    status = list(tmp_path.stat())
    status[4] = os.geteuid() + 1
    mocker.patch.object(Path, "lstat", return_value=os.stat_result(status))
    assert isinstance(DiskCache(tmp_path).py_info(Path("/some/path")), NoOpContentStore)


def test_disk_cache_works_without_posix_ownership(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(os, "geteuid", raising=False)
    assert isinstance(DiskCache(tmp_path).py_info(Path("/some/path")), DiskContentStore)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX ownership and modes")
def test_disk_cache_keeps_validated_relative_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    safe = tmp_path / "safe"
    unsafe = tmp_path / "unsafe"
    safe.mkdir()
    unsafe.mkdir()
    unsafe.chmod(0o777)
    monkeypatch.chdir(safe)
    store = DiskCache(Path("cache")).py_info(Path("/some/path"))
    monkeypatch.chdir(unsafe)
    store.write({"key": "value"})
    assert (len(list(safe.rglob("*.json"))), list(unsafe.rglob("*.json"))) == (1, [])


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX ownership and modes")
def test_disk_cache_clear_skips_writable_directory(tmp_path: Path) -> None:
    folder = tmp_path / "py_info" / "4"
    folder.mkdir(parents=True)
    entry = folder / "entry.json"
    entry.write_text("{}", encoding="utf-8")
    tmp_path.chmod(0o777)
    DiskCache(tmp_path).py_info_clear()
    assert entry.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symbolic links")
def test_disk_cache_clear_does_not_follow_linked_directory(tmp_path: Path) -> None:
    target = tmp_path / "target" / "4"
    target.mkdir(parents=True)
    entry = target / "credentials.json"
    entry.write_text("{}", encoding="utf-8")
    (tmp_path / "py_info").symlink_to(target.parent, target_is_directory=True)
    DiskCache(tmp_path).py_info_clear()
    assert entry.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX ownership and modes")
@pytest.mark.parametrize(
    ("owner_offset", "mode"),
    [pytest.param(1, 0o600, id="foreign-owner"), pytest.param(0, 0o660, id="group-writable")],
)
def test_disk_content_store_rejects_untrusted_entry(
    tmp_path: Path, mocker: MockerFixture, owner_offset: int, mode: int
) -> None:
    store = DiskContentStore(tmp_path, "entry")
    store.write({"key": "value"})
    status = list((tmp_path / "entry.json").stat())
    status[0], status[4] = stat.S_IFREG | mode, os.geteuid() + owner_offset
    mocker.patch("python_discovery._cache.os.fstat", return_value=os.stat_result(status))
    assert store.read() is None
    assert not store.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symbolic links")
def test_disk_content_store_does_not_follow_entry_link(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text('{"key": "target"}', encoding="utf-8")
    entry = tmp_path / "entry.json"
    entry.symlink_to(target)
    store = DiskContentStore(tmp_path, "entry")
    assert store.read() is None


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX FIFOs")
def test_disk_content_store_skips_fifo(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "entry.json")
    store = DiskContentStore(tmp_path, "entry")
    assert store.read() is None
    assert not store.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symbolic links")
def test_disk_content_store_write_replaces_entry_link(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text('{"key": "target"}', encoding="utf-8")
    (tmp_path / "entry.json").symlink_to(target)
    store = DiskContentStore(tmp_path, "entry")
    store.write({"key": "value"})
    assert (target.read_text(encoding="utf-8"), store.read()) == ('{"key": "target"}', {"key": "value"})


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
def test_disk_content_store_write_is_private_with_lax_umask(tmp_path: Path) -> None:
    previous = os.umask(0)
    try:
        DiskContentStore(tmp_path, "entry").write({"key": "value"})
    finally:
        os.umask(previous)
    assert stat.S_IMODE((tmp_path / "entry.json").stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "target",
    [
        pytest.param("python_discovery._cache.NamedTemporaryFile", id="create"),
        pytest.param("pathlib.Path.replace", id="replace"),
    ],
)
def test_disk_content_store_write_skips_io_failure(tmp_path: Path, mocker: MockerFixture, target: str) -> None:
    mocker.patch(target, side_effect=PermissionError)
    DiskContentStore(tmp_path, "entry").write({"key": "value"})
    assert list(tmp_path.iterdir()) == []


def test_noop_content_store_exists() -> None:
    assert NoOpContentStore().exists() is False


def test_noop_content_store_read() -> None:
    assert NoOpContentStore().read() is None


def test_noop_content_store_write() -> None:
    NoOpContentStore().write({"key": "value"})


def test_noop_content_store_remove() -> None:
    NoOpContentStore().remove()


def test_noop_content_store_locked() -> None:
    with NoOpContentStore().locked():
        pass


def test_noop_cache_py_info() -> None:
    cache = NoOpCache()
    store = cache.py_info(Path("/some/path"))
    assert isinstance(store, NoOpContentStore)


def test_noop_cache_py_info_clear() -> None:
    NoOpCache().py_info_clear()
