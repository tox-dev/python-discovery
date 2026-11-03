from __future__ import annotations

import logging
import os
import stat
import sys
from copy import deepcopy
from pathlib import Path
from subprocess import check_call, check_output
from typing import TYPE_CHECKING, Final
from unittest.mock import patch
from uuid import uuid4

import pytest

from python_discovery import DiskCache, PythonInfo, PythonSpec, SimpleSpecifierSet, get_interpreter, iter_interpreters
from python_discovery._discovery import IS_WIN, LazyPathDump, get_paths, propose_interpreters

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytest_mock import MockerFixture


@pytest.mark.graalpy
@pytest.mark.skipif(not Path(sys.executable).is_symlink() and not Path(sys.executable).is_file(), reason="no symlink")
@pytest.mark.parametrize("case", ["mixed", "lower", "upper"])
@pytest.mark.parametrize("specificity", ["more", "less", "none"])
def test_discovery_via_path(
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    specificity: str,
    *,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    session_cache: DiskCache,
) -> None:
    caplog.set_level(logging.DEBUG)
    current = PythonInfo.current_system(session_cache)
    name = "somethingVeryCryptic"
    threaded = "t" if current.free_threaded else ""
    if case == "lower":
        name = name.lower()
    elif case == "upper":
        name = name.upper()
    if specificity == "more":
        core_ver = current.version_info.major
        exe_ver = ".".join(str(i) for i in current.version_info[0:2]) + threaded
    elif specificity == "less":
        core_ver = ".".join(str(i) for i in current.version_info[0:3])
        exe_ver = current.version_info.major
    elif specificity == "none":  # pragma: no branch
        core_ver = ".".join(str(i) for i in current.version_info[0:3])
        exe_ver = ""
    core = "" if specificity == "none" else f"{name}{core_ver}{threaded}"
    exe_name = f"{name}{exe_ver}{'.exe' if sys.platform == 'win32' else ''}"
    target = tmp_path / current.install_path("scripts")
    target.mkdir(parents=True)
    executable = target / exe_name
    Path(str(executable)).symlink_to(sys.executable)
    pyvenv_cfg = Path(sys.executable).parents[1] / "pyvenv.cfg"
    if pyvenv_cfg.exists():  # pragma: no branch
        (target / pyvenv_cfg.name).write_bytes(pyvenv_cfg.read_bytes())
    new_path = os.pathsep.join([str(target), *os.environ.get("PATH", "").split(os.pathsep)])
    monkeypatch.setenv("PATH", new_path)
    interpreter = get_interpreter(core, [])

    assert interpreter is not None


def test_discovery_via_path_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    interpreter = get_interpreter(uuid4().hex, [])
    assert interpreter is None


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlink names")
def test_discovery_via_path_literal_symlink(tmp_path: Path) -> None:
    link = tmp_path / "python_custom"
    link.symlink_to(sys.executable)

    interpreter = get_interpreter("python_custom", [], env={"PATH": str(tmp_path)})

    assert interpreter is not None
    assert interpreter.executable == str(link)


@pytest.mark.skipif(sys.implementation.name != "cpython", reason="requires CPython")
@pytest.mark.parametrize("name", [pytest.param("pypy", id="pypy"), pytest.param("Python", id="mixed-case-python")])
def test_pypy_spec_rejects_cpython_alias(name: str, tmp_path: Path, session_cache: DiskCache) -> None:
    threaded = "t" if PythonInfo.current_system(session_cache).free_threaded else ""
    version = f"{sys.version_info.major}.{sys.version_info.minor}{threaded}"
    (tmp_path / f"{name}{version}{'.exe' if IS_WIN else ''}").symlink_to(sys.executable)
    env = {"PATH": str(tmp_path), "UV_PYTHON_INSTALL_DIR": str(tmp_path / "missing")}

    selected = get_interpreter(f"pypy{version}", [], cache=session_cache, env=env)
    assert selected is None or selected.implementation == "PyPy"
    assert all(
        info.implementation == "PyPy" for info in iter_interpreters(f"pypy{version}", cache=session_cache, env=env)
    )


@pytest.mark.skipif(sys.implementation.name != "cpython", reason="requires CPython")
def test_generic_python_spec_accepts_mixed_case_alias(tmp_path: Path, session_cache: DiskCache) -> None:
    threaded = "t" if PythonInfo.current_system(session_cache).free_threaded else ""
    version = f"{sys.version_info.major}.{sys.version_info.minor}{threaded}"
    alias = tmp_path / f"Python{version}{'.exe' if IS_WIN else ''}"
    alias.symlink_to(sys.executable)

    selected = get_interpreter(
        f"Python{version}",
        [],
        cache=session_cache,
        env={"PATH": str(tmp_path), "UV_PYTHON_INSTALL_DIR": str(tmp_path / "missing")},
    )

    assert selected is not None
    assert (selected.executable, selected.implementation) == (str(alias), "CPython")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell script")
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
def test_discovery_skips_candidate_with_wrong_shape_json(tmp_path: Path, output: str) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    name = "python_custom"
    fake = first / name
    fake.write_text(f"#!/bin/sh\nprintf '%s\\n' '{output}'\n", encoding="utf-8")
    fake.chmod(0o755)
    real = second / name
    real.symlink_to(sys.executable)

    interpreter = get_interpreter(
        name,
        cache=DiskCache(tmp_path / "cache"),
        env={"PATH": os.pathsep.join([str(first), str(second)]), "HOME": "/nonexistent"},
    )

    assert interpreter is not None
    assert interpreter.executable == str(real)


def test_discovery_via_path_in_nonbrowseable_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bad_perm = tmp_path / "bad_perm"
    bad_perm.mkdir(mode=0o000)
    monkeypatch.setenv("PATH", str(bad_perm))
    interpreter = get_interpreter(uuid4().hex, [])
    assert interpreter is None
    monkeypatch.setenv("PATH", str(bad_perm / "bin"))
    interpreter = get_interpreter(uuid4().hex, [])
    assert interpreter is None


def test_relative_path(session_cache: DiskCache, monkeypatch: pytest.MonkeyPatch) -> None:
    sys_executable = Path(PythonInfo.current_system(session_cache).system_executable)
    cwd = sys_executable.parents[1]
    monkeypatch.chdir(str(cwd))
    relative = str(sys_executable.relative_to(cwd))
    result = get_interpreter(relative, [], session_cache)
    assert result is not None


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("3.14.0rc1", id="prerelease"),
        pytest.param("python3.13-arm64-64", id="swapped-platform"),
        pytest.param("python_d", id="executable-name"),
    ],
)
def test_bare_name_spec_does_not_probe_cwd(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
) -> None:
    (tmp_path / name).touch(mode=0o755)
    monkeypatch.chdir(tmp_path)
    from_exe = mocker.patch("python_discovery._discovery.PythonInfo.from_exe", return_value=None)

    assert get_interpreter(name, [], env={"PATH": "", "UV_PYTHON_INSTALL_DIR": str(tmp_path / "uv")}) is None
    from_exe.assert_not_called()


@pytest.mark.parametrize(
    "sep",
    [
        pytest.param("/", id="slash"),
        pytest.param("\\", id="backslash", marks=pytest.mark.skipif(not IS_WIN, reason="Windows separator")),
    ],
)
def test_relative_path_with_parent_reference(
    session_cache: DiskCache, monkeypatch: pytest.MonkeyPatch, sep: str
) -> None:
    sys_executable = Path(PythonInfo.current_system(session_cache).system_executable)
    monkeypatch.chdir(str(sys_executable.parent))
    relative = sep.join((os.pardir, sys_executable.parent.name, sys_executable.name))
    result = get_interpreter(relative, [], session_cache)
    assert result is not None
    assert os.pardir not in Path(result.executable).parts
    assert Path(result.executable).samefile(sys_executable)


def test_discovery_fallback_fail(session_cache: DiskCache, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    result = get_interpreter(["magic-one", "magic-two"], cache=session_cache)
    assert result is None
    assert "accepted" not in caplog.text


@pytest.mark.parametrize("missing", ["magic-one", "python."])
def test_discovery_fallback_ok(missing: str, session_cache: DiskCache, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    result = get_interpreter([missing, sys.executable], cache=session_cache)
    assert result is not None, caplog.text
    assert result.executable == sys.executable, caplog.text
    assert "accepted" in caplog.text


def test_discovery_invalid_specifier_raises(session_cache: DiskCache) -> None:
    with pytest.raises(ValueError, match=r"^invalid version specifier '>=3\.12 <4'$"):
        get_interpreter([">=3.12 <4", sys.executable], cache=session_cache)


@pytest.mark.parametrize(
    "use_iterator",
    [pytest.param(False, id="list"), pytest.param(True, id="iterator")],
)
def test_discovery_fallback_reuses_preferred_paths(
    tmp_path: Path, session_cache: DiskCache, mocker: MockerFixture, *, use_iterator: bool
) -> None:
    executable = tmp_path / "preferred" / ("Scripts/python.exe" if IS_WIN else "bin/python")
    executable.parent.mkdir(parents=True)
    executable.touch()
    preferred_info = deepcopy(PythonInfo.current_system(session_cache))
    preferred_info.executable = str(executable)
    mocker.patch.object(PythonInfo, "from_exe", return_value=preferred_info)
    paths = [str(executable)]
    result = get_interpreter(
        ["missing-interpreter", ">=3"],
        try_first_with=iter(paths) if use_iterator else paths,
        cache=session_cache,
        env={**os.environ, "PATH": str(tmp_path), "UV_PYTHON_INSTALL_DIR": str(tmp_path / "missing")},
        predicate=lambda info: Path(info.executable) == executable,
    )
    assert result is not None
    assert Path(result.executable) == executable


def test_discovery_stops_reading_preferred_paths_after_match(session_cache: DiskCache) -> None:
    preferred_paths = iter([sys.executable, "unneeded"])
    result = get_interpreter(">=3", try_first_with=preferred_paths, cache=session_cache)
    assert result is not None
    assert next(preferred_paths) == "unneeded"


@pytest.fixture
def mock_find_interpreter(mocker: MockerFixture) -> None:
    mocker.patch(
        "python_discovery._discovery._find_interpreter",
        lambda key, *_args, **_kwargs: getattr(mocker.sentinel, key),
    )


@pytest.mark.usefixtures("mock_find_interpreter")
def test_returns_first_python_specified(mocker: MockerFixture) -> None:
    result = get_interpreter(["python_from_cli"])
    assert result == mocker.sentinel.python_from_cli


def test_discovery_absolute_path_with_try_first(
    tmp_path: Path,
    session_cache: DiskCache,
) -> None:
    good_env = tmp_path / "good"
    bad_env = tmp_path / "bad"

    check_call([sys.executable, "-m", "venv", str(good_env)])
    check_call([sys.executable, "-m", "venv", str(bad_env)])

    scripts_dir = "Scripts" if IS_WIN else "bin"
    exe_name = "python.exe" if IS_WIN else "python"
    good_exe = good_env / scripts_dir / exe_name
    bad_exe = bad_env / scripts_dir / exe_name

    interpreter = get_interpreter(
        str(good_exe),
        try_first_with=[str(bad_exe)],
        cache=session_cache,
    )

    assert interpreter is not None
    assert Path(interpreter.executable) == good_exe


def test_discovery_venvs_on_one_base_keep_their_executable(tmp_path: Path, session_cache: DiskCache) -> None:
    scripts_dir = "Scripts" if IS_WIN else "bin"
    exe_name = "python.exe" if IS_WIN else "python"
    exes = [tmp_path / name / scripts_dir / exe_name for name in ("a", "b")]
    for exe in exes:
        check_call([sys.executable, "-m", "venv", "--without-pip", str(exe.parents[1])])

    found = [get_interpreter(str(exe), cache=session_cache) for exe in exes]

    assert [Path(info.executable) for info in found if info is not None] == exes


def test_discovery_try_first_with_keeps_venv(tmp_path: Path, session_cache: DiskCache) -> None:
    venv = tmp_path / "preferred"
    check_call([sys.executable, "-m", "venv", "--without-pip", str(venv)])
    exe = venv / ("Scripts/python.exe" if IS_WIN else "bin/python")

    info = get_interpreter(
        ">=3",
        try_first_with=[str(exe)],
        cache=session_cache,
        env={**os.environ, "PATH": "", "UV_PYTHON_INSTALL_DIR": str(tmp_path / "missing")},
    )

    assert info is not None
    assert (
        info.executable,
        check_output([info.executable, "-c", "import sys; print(sys.prefix)"], text=True).strip(),
    ) == (str(exe), str(venv))


def test_discovery_try_first_with_skips_broken_symlink(tmp_path: Path, session_cache: DiskCache) -> None:
    broken = tmp_path / "missing-python"
    broken.symlink_to(tmp_path / "missing")

    info = get_interpreter(
        ">=3",
        try_first_with=[str(broken)],
        cache=session_cache,
        env={**os.environ, "PATH": "", "UV_PYTHON_INSTALL_DIR": str(tmp_path / "missing")},
    )

    assert info is not None
    assert info.executable == PythonInfo.current_system(session_cache).executable


def test_discovery_via_path_with_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    a_file = tmp_path / "a_file"
    a_file.touch()
    monkeypatch.setenv("PATH", str(a_file))
    interpreter = get_interpreter(uuid4().hex, [])
    assert interpreter is None


def test_get_paths_no_path_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PATH", raising=False)
    assert all(path.is_absolute() for path in get_paths({}))


@pytest.mark.parametrize("relative", [".", "bin", "~/.local/bin"])
def test_get_paths_skips_relative_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relative: str) -> None:
    monkeypatch.chdir(tmp_path)
    relative_dir = tmp_path / relative
    relative_dir.mkdir(parents=True, exist_ok=True)
    (relative_dir / "python3").touch()
    absolute_dir = tmp_path / "absolute"
    absolute_dir.mkdir()
    (absolute_dir / "python3").touch()

    assert list(get_paths({"PATH": f"{relative}{os.pathsep}{absolute_dir}"})) == [absolute_dir]


def test_get_paths_skips_relative_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "python3").touch()
    absolute_dir = tmp_path / "absolute"
    absolute_dir.mkdir()
    (absolute_dir / "python3").touch()

    with (
        patch("python_discovery._discovery.os.confstr", side_effect=AttributeError, create=True),
        patch("python_discovery._discovery.os.defpath", f".{os.pathsep}{absolute_dir}"),
    ):
        assert list(get_paths({})) == [absolute_dir]


@pytest.mark.parametrize(
    ("raw_path", "expected"),
    [
        pytest.param("{first}{sep}", ["first"], id="trailing"),
        pytest.param("{sep}{first}", ["first"], id="leading"),
        pytest.param("{first}{sep}{sep}{second}", ["first", "second"], id="doubled"),
    ],
)
def test_get_paths_skips_empty_entries(tmp_path: Path, raw_path: str, expected: list[str]) -> None:
    """An empty PATH entry means "current directory" - it must never be searched for interpreters."""
    dirs = {}
    for name in ("first", "second"):
        dirs[name] = tmp_path / name
        dirs[name].mkdir()
        (dirs[name] / "dummy").touch()

    paths = list(get_paths({"PATH": raw_path.format(first=dirs["first"], second=dirs["second"], sep=os.pathsep)}))

    assert paths == [dirs[name] for name in expected]


def test_get_paths_empty_entry_does_not_yield_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reproduces the exploit: an empty PATH entry used to resolve to the caller's CWD."""
    cwd_marker = tmp_path / "python3.11"
    cwd_marker.touch(mode=0o755)
    monkeypatch.chdir(tmp_path)

    paths = list(get_paths({"PATH": f"{os.pathsep}"}))

    assert not any(path.resolve() == tmp_path.resolve() for path in paths)


def test_lazy_path_dump_debug(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("_VIRTUALENV_DEBUG", "1")
    a_dir = tmp_path
    executable_file = "a_file.exe" if IS_WIN else "a_file"
    (a_dir / executable_file).touch(mode=0o755)
    (a_dir / "b_file").touch(mode=0o644)
    dumper = LazyPathDump(0, a_dir, os.environ)
    output = repr(dumper)
    assert executable_file in output
    assert "b_file" not in output


def test_discovery_via_version_specifier(session_cache: DiskCache) -> None:
    current = PythonInfo.current_system(session_cache)
    major, minor = current.version_info.major, current.version_info.minor

    spec = f">={major}.{minor}"
    interpreter = get_interpreter(spec, [], session_cache)
    assert interpreter is not None
    assert interpreter.version_info.major == major
    assert interpreter.version_info.minor >= minor

    spec = f">={major}.{minor},<{major}.{minor + 10}"
    interpreter = get_interpreter(spec, [], session_cache)
    assert interpreter is not None
    assert interpreter.version_info.major == major
    assert minor <= interpreter.version_info.minor < minor + 10

    spec = f"cpython>={major}.{minor}"
    interpreter = get_interpreter(spec, [], session_cache)
    if current.implementation == "CPython":  # pragma: no branch
        assert interpreter is not None
        assert interpreter.implementation == "CPython"


_POSIX_PERMISSIONS: Final[pytest.MarkDecorator] = pytest.mark.skipif(
    IS_WIN or os.geteuid() == 0, reason="POSIX file permissions, which root bypasses"
)


def _create_version_manager(tmp_path: Path, env_var: str) -> Path:
    root = tmp_path / env_var.lower()
    root.mkdir()
    (root / "shims").mkdir()
    return root


def _create_versioned_binary(root: Path, versions_path: tuple[str, ...], version: str, exe_name: str) -> Path:
    bin_dir = root.joinpath(*versions_path, version, "bin")
    bin_dir.mkdir(parents=True, exist_ok=True)
    exe = bin_dir / (f"{exe_name}.exe" if IS_WIN else exe_name)
    exe.touch()
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return exe


@pytest.mark.parametrize(
    ("env_var", "versions_path"),
    [
        pytest.param("PYENV_ROOT", ("versions",), id="pyenv"),
        pytest.param("MISE_DATA_DIR", ("installs", "python"), id="mise"),
        pytest.param("ASDF_DATA_DIR", ("installs", "python"), id="asdf"),
    ],
)
def test_shim_resolved_to_real_binary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_var: str,
    versions_path: tuple[str, ...],
) -> None:
    root = _create_version_manager(tmp_path, env_var)
    real_binary = _create_versioned_binary(root, versions_path, "2.7.18", "python2.7")
    shim = root / "shims" / ("python2.7.exe" if IS_WIN else "python2.7")
    shim.touch(mode=0o755)

    monkeypatch.setenv("PATH", str(root / "shims"))
    monkeypatch.setenv(env_var, str(root))
    monkeypatch.setenv("PYENV_VERSION", "2.7.18")
    monkeypatch.delenv("MISE_DATA_DIR", raising=False) if env_var != "MISE_DATA_DIR" else None
    monkeypatch.delenv("ASDF_DATA_DIR", raising=False) if env_var != "ASDF_DATA_DIR" else None
    monkeypatch.delenv("PYENV_ROOT", raising=False) if env_var != "PYENV_ROOT" else None

    with patch("python_discovery._discovery.PathPythonInfo.from_exe") as mock_from_exe:
        mock_from_exe.return_value = None
        get_interpreter("python2.7", [])
        assert mock_from_exe.call_args_list[0][0][0] == str(real_binary)


def test_shim_not_resolved_without_version_manager_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shims_dir = tmp_path / "shims"
    shims_dir.mkdir()
    shim = shims_dir / ("python2.7.exe" if IS_WIN else "python2.7")
    shim.touch(mode=0o755)

    monkeypatch.setenv("PATH", str(shims_dir))
    monkeypatch.delenv("PYENV_ROOT", raising=False)
    monkeypatch.delenv("MISE_DATA_DIR", raising=False)
    monkeypatch.delenv("ASDF_DATA_DIR", raising=False)

    with patch("python_discovery._discovery.PathPythonInfo.from_exe") as mock_from_exe:
        mock_from_exe.return_value = None
        get_interpreter("python2.7", [])
        assert mock_from_exe.call_args_list[0][0][0] == str(shim)


def test_shim_falls_through_when_binary_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _create_version_manager(tmp_path, "PYENV_ROOT")
    shim = root / "shims" / ("python2.7.exe" if IS_WIN else "python2.7")
    shim.touch(mode=0o755)

    monkeypatch.setenv("PATH", str(root / "shims"))
    monkeypatch.setenv("PYENV_ROOT", str(root))
    monkeypatch.setenv("PYENV_VERSION", "2.7.18")

    with patch("python_discovery._discovery.PathPythonInfo.from_exe") as mock_from_exe:
        mock_from_exe.return_value = None
        get_interpreter("python2.7", [])
        assert mock_from_exe.call_args_list[0][0][0] == str(shim)


def test_shim_uses_python_version_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _create_version_manager(tmp_path, "PYENV_ROOT")
    real_binary = _create_versioned_binary(root, ("versions",), "2.7.18", "python2.7")
    shim = root / "shims" / ("python2.7.exe" if IS_WIN else "python2.7")
    shim.touch(mode=0o755)
    (tmp_path / ".python-version").write_text(encoding="utf-8", data="2.7.18\n")

    monkeypatch.setenv("PATH", str(root / "shims"))
    monkeypatch.setenv("PYENV_ROOT", str(root))
    monkeypatch.delenv("PYENV_VERSION", raising=False)
    monkeypatch.chdir(tmp_path)

    with patch("python_discovery._discovery.PathPythonInfo.from_exe") as mock_from_exe:
        mock_from_exe.return_value = None
        get_interpreter("python2.7", [])
        assert mock_from_exe.call_args_list[0][0][0] == str(real_binary)


@pytest.mark.parametrize(
    ("version", "target"),
    [
        pytest.param("{outside}", "outside", id="absolute"),
        pytest.param("../../outside", "outside", id="traversal"),
        pytest.param("..", "root", id="parent"),
        pytest.param(".", "versions", id="current"),
        pytest.param("2.7.18/subdir", "nested", id="nested"),
    ],
)
def test_shim_skips_path_like_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version: str, target: str
) -> None:
    root = _create_version_manager(tmp_path, "PYENV_ROOT")
    real_binary = _create_versioned_binary(root, ("versions",), "2.7.18", "python2.7")
    outside = tmp_path / "outside"
    attack_root = {
        "outside": outside,
        "root": root,
        "versions": root / "versions",
        "nested": root / "versions" / "2.7.18" / "subdir",
    }[target]
    _create_versioned_binary(attack_root, (), "", "python2.7")
    shim = root / "shims" / ("python2.7.exe" if IS_WIN else "python2.7")
    shim.touch(mode=0o755)
    (tmp_path / ".python-version").write_text(f"{version.format(outside=outside)}\n2.7.18\n", encoding="utf-8")

    monkeypatch.setenv("PATH", str(root / "shims"))
    monkeypatch.setenv("PYENV_ROOT", str(root))
    monkeypatch.delenv("PYENV_VERSION", raising=False)
    monkeypatch.chdir(tmp_path)

    with patch("python_discovery._discovery.PathPythonInfo.from_exe") as mock_from_exe:
        mock_from_exe.return_value = None
        get_interpreter("python2.7", [])
        assert mock_from_exe.call_args_list[0][0][0] == str(real_binary)


def test_shim_skips_empty_environment_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _create_version_manager(tmp_path, "PYENV_ROOT")
    real_binary = _create_versioned_binary(root, ("versions",), "2.7.18", "python2.7")
    _create_versioned_binary(root / "versions", (), "", "python2.7")
    shim = root / "shims" / ("python2.7.exe" if IS_WIN else "python2.7")
    shim.touch(mode=0o755)

    monkeypatch.setenv("PATH", str(root / "shims"))
    monkeypatch.setenv("PYENV_ROOT", str(root))
    monkeypatch.setenv("PYENV_VERSION", ":2.7.18")

    with patch("python_discovery._discovery.PathPythonInfo.from_exe") as mock_from_exe:
        mock_from_exe.return_value = None
        get_interpreter("python2.7", [])
        assert mock_from_exe.call_args_list[0][0][0] == str(real_binary)


@pytest.mark.parametrize(
    ("length", "version"),
    [pytest.param(4096, "2.7.18", id="at-limit"), pytest.param(4097, "2.7.15", id="over-limit")],
)
def test_shim_oversized_python_version_file_is_skipped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pyenv_probed: Callable[[], tuple[str, ...]],
    length: int,
    version: str,
) -> None:
    root = Path(os.environ["PYENV_ROOT"])
    _create_versioned_binary(root, ("versions",), "2.7.15", "python2.7")
    (root / "version").write_text("2.7.15\n", encoding="utf-8")
    (tmp_path / ".python-version").write_text("2.7.18\n#" + "x" * (length - 8), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert pyenv_probed() == ("versions", version)


def test_shim_python_version_file_keeps_unicode_separator_in_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pyenv_probed: Callable[[], tuple[str, ...]]
) -> None:
    (tmp_path / ".python-version").write_text("2.7.18\u2028ignored\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert pyenv_probed() == ("shims", "python2.7.exe" if IS_WIN else "python2.7")


def test_shim_python_version_file_not_utf8(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pyenv_probed: Callable[[], tuple[str, ...]]
) -> None:
    (tmp_path / ".python-version").write_bytes(b"# pinned by M\xfcller\n2.7.18\n")
    monkeypatch.chdir(tmp_path)

    assert pyenv_probed() == ("versions", "2.7.18")


@_POSIX_PERMISSIONS
def test_shim_unreadable_python_version_file_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pyenv_probed: Callable[[], tuple[str, ...]]
) -> None:
    (tmp_path / ".python-version").write_text("2.7.18\n", encoding="utf-8")
    (unreadable := tmp_path / "child" / ".python-version").parent.mkdir()
    unreadable.write_text("3.12.0\n", encoding="utf-8")
    unreadable.chmod(0)
    monkeypatch.chdir(unreadable.parent)

    assert pyenv_probed() == ("versions", "2.7.18")


@_POSIX_PERMISSIONS
def test_shim_unsearchable_directory_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pyenv_probed: Callable[[], tuple[str, ...]]
) -> None:
    (tmp_path / ".python-version").write_text("2.7.18\n", encoding="utf-8")
    (work := tmp_path / "locked" / "work").mkdir(parents=True)
    monkeypatch.chdir(work)
    work.parent.chmod(0o600)
    try:
        assert pyenv_probed() == ("versions", "2.7.18")
    finally:
        work.parent.chmod(0o700)


@pytest.fixture
def pyenv_probed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
) -> Callable[[], tuple[str, ...]]:
    root = _create_version_manager(tmp_path, "PYENV_ROOT")
    _create_versioned_binary(root, ("versions",), "2.7.18", "python2.7")
    (root / "shims" / ("python2.7.exe" if IS_WIN else "python2.7")).touch(mode=0o755)
    monkeypatch.setenv("PATH", str(root / "shims"))
    monkeypatch.setenv("PYENV_ROOT", str(root))
    monkeypatch.delenv("PYENV_VERSION", raising=False)
    from_exe = mocker.patch("python_discovery._discovery.PathPythonInfo.from_exe", return_value=None)

    def _probed() -> tuple[str, ...]:
        get_interpreter("python2.7", [])
        return Path(from_exe.call_args_list[0].args[0]).relative_to(root).parts[:2]

    return _probed


def test_shim_pyenv_version_env_takes_priority_over_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _create_version_manager(tmp_path, "PYENV_ROOT")
    _create_versioned_binary(root, ("versions",), "2.7.18", "python2.7")
    env_binary = _create_versioned_binary(root, ("versions",), "2.7.15", "python2.7")
    shim = root / "shims" / ("python2.7.exe" if IS_WIN else "python2.7")
    shim.touch(mode=0o755)
    (tmp_path / ".python-version").write_text(encoding="utf-8", data="2.7.18\n")

    monkeypatch.setenv("PATH", str(root / "shims"))
    monkeypatch.setenv("PYENV_ROOT", str(root))
    monkeypatch.setenv("PYENV_VERSION", "2.7.15")
    monkeypatch.chdir(tmp_path)

    with patch("python_discovery._discovery.PathPythonInfo.from_exe") as mock_from_exe:
        mock_from_exe.return_value = None
        get_interpreter("python2.7", [])
        assert mock_from_exe.call_args_list[0][0][0] == str(env_binary)


def test_shim_uses_global_version_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _create_version_manager(tmp_path, "PYENV_ROOT")
    real_binary = _create_versioned_binary(root, ("versions",), "2.7.18", "python2.7")
    shim = root / "shims" / ("python2.7.exe" if IS_WIN else "python2.7")
    shim.touch(mode=0o755)
    (root / "version").write_text(encoding="utf-8", data="2.7.18\n")
    workdir = tmp_path / "workdir"
    workdir.mkdir()

    monkeypatch.setenv("PATH", str(root / "shims"))
    monkeypatch.setenv("PYENV_ROOT", str(root))
    monkeypatch.delenv("PYENV_VERSION", raising=False)
    monkeypatch.chdir(workdir)

    with patch("python_discovery._discovery.PathPythonInfo.from_exe") as mock_from_exe:
        mock_from_exe.return_value = None
        get_interpreter("python2.7", [])
        assert mock_from_exe.call_args_list[0][0][0] == str(real_binary)


def test_shim_colon_separated_pyenv_version_picks_first_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _create_version_manager(tmp_path, "PYENV_ROOT")
    _create_versioned_binary(root, ("versions",), "2.7.18", "python2.7")
    second_binary = _create_versioned_binary(root, ("versions",), "2.7.15", "python2.7")
    shim = root / "shims" / ("python2.7.exe" if IS_WIN else "python2.7")
    shim.touch(mode=0o755)

    monkeypatch.setenv("PATH", str(root / "shims"))
    monkeypatch.setenv("PYENV_ROOT", str(root))
    monkeypatch.setenv("PYENV_VERSION", "3.9.1:2.7.15")

    with patch("python_discovery._discovery.PathPythonInfo.from_exe") as mock_from_exe:
        mock_from_exe.return_value = None
        get_interpreter("python2.7", [])
        assert mock_from_exe.call_args_list[0][0][0] == str(second_binary)


def test_predicate_filters_interpreters(session_cache: DiskCache) -> None:
    result = get_interpreter(sys.executable, [], session_cache, predicate=lambda _: False)
    assert result is None


def test_predicate_accepts_interpreter(session_cache: DiskCache) -> None:
    result = get_interpreter(sys.executable, [], session_cache, predicate=lambda _: True)
    assert result is not None
    assert result.executable == sys.executable


def test_predicate_none_is_noop(session_cache: DiskCache) -> None:
    result = get_interpreter(sys.executable, [], session_cache, predicate=None)
    assert result is not None
    assert result.executable == sys.executable


def test_predicate_with_fallback_specs(session_cache: DiskCache) -> None:
    current = PythonInfo.current_system(session_cache)
    major, minor = current.version_info.major, current.version_info.minor
    proposed: list[str] = []

    def reject_first(info: PythonInfo) -> bool:
        proposed.append(str(info.executable))
        return len(proposed) > 1

    threaded = "t" if current.free_threaded else ""
    result = get_interpreter([f"{major}.{minor}{threaded}", sys.executable], [], session_cache, predicate=reject_first)
    # rejecting the first proposal must not abort discovery; a later proposal (same or fallback spec) is accepted -
    # on hosts where every alias resolves to one interpreter the fallback re-proposes it, so executables may match
    assert result is not None
    assert len(proposed) > 1
    assert str(result.executable) == proposed[-1]


# no interpreter answers to this, so discovery walks every source instead of stopping at the running one
_NO_UV_MATCH: Final[str] = "3.99"


@pytest.fixture
def uv_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A throwaway home, with every directory variable uv consults pointed into it or unset."""
    for var in ("UV_PYTHON_INSTALL_DIR", "XDG_DATA_HOME", "APPDATA"):
        monkeypatch.delenv(var, raising=False)
    for var in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(var, str(tmp_path))
    monkeypatch.setenv("PATH", "")
    return tmp_path


@pytest.fixture
def uv_plant() -> Callable[[Path], str]:
    """Create a uv install under a store root and return the executable discovery should reach for."""

    def _plant(root: Path) -> str:
        (bin_dir := root / "some-py-impl" / "bin").mkdir(parents=True)
        (executable := bin_dir / "python").touch()
        return str(executable)

    return _plant


@pytest.fixture
def uv_probed(mocker: MockerFixture) -> Callable[..., list[str]]:
    """Run a discovery with the interrogation subprocess stubbed out, reporting the executables it reached for."""
    from_exe = mocker.patch("python_discovery._discovery.PathPythonInfo.from_exe", return_value=None)

    def _probed(**kwargs: object) -> list[str]:
        get_interpreter(_NO_UV_MATCH, [], **kwargs)
        return [call.args[0] for call in from_exe.call_args_list]

    return _probed


@pytest.mark.parametrize("expand_user", [True, False], ids=["expands-user", "absolute"])
def test_discovery_uv_store_install_dir_overrides_the_platform_default(
    uv_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    uv_plant: Callable[[Path], str],
    uv_probed: Callable[..., list[str]],
    expand_user: bool,
) -> None:
    monkeypatch.setenv("UV_PYTHON_INSTALL_DIR", "~/store" if expand_user else str(uv_home / "store"))
    uv_plant(uv_home / ".local" / "share" / "uv" / "python")
    executable = uv_plant(uv_home / "store")

    assert uv_probed() == [executable]


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
@pytest.mark.usefixtures("uv_home")
def test_discovery_uv_store_roots_per_platform(
    monkeypatch: pytest.MonkeyPatch,
    uv_plant: Callable[[Path], str],
    uv_probed: Callable[..., list[str]],
    platform: str,
    extra_env: dict[str, str],
    expected: list[str],
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    for name, value in extra_env.items():
        monkeypatch.setenv(name, str(Path(value).expanduser()))
    executables = [uv_plant(Path(state_dir).expanduser() / "python") for state_dir in expected]

    assert uv_probed() == executables


@pytest.mark.parametrize(
    ("appdata", "store"),
    [
        pytest.param("", "uv/data", id="empty"),
        pytest.param("relative", "relative/uv/data", id="relative"),
    ],
)
def test_discovery_uv_store_invalid_appdata_uses_profile_default(
    uv_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    uv_plant: Callable[[Path], str],
    uv_probed: Callable[..., list[str]],
    appdata: str,
    store: str,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", appdata)
    (checkout := uv_home / "checkout").mkdir()
    monkeypatch.chdir(checkout)
    uv_plant(checkout / store / "python")
    profile_executable = uv_plant(uv_home / "AppData" / "Roaming" / "uv" / "data" / "python")

    assert uv_probed() == [profile_executable]


@pytest.mark.parametrize(
    ("platform", "profile_var", "store"),
    [
        pytest.param("win32", "USERPROFILE", "relative/AppData/Roaming/uv/data", id="windows"),
        pytest.param("linux", "HOME", "relative/.local/share/uv", id="linux"),
        pytest.param("darwin", "HOME", "relative/Library/Application Support/uv", id="macos"),
    ],
)
def test_discovery_uv_store_skips_relative_profile(
    uv_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    uv_plant: Callable[[Path], str],
    uv_probed: Callable[..., list[str]],
    platform: str,
    profile_var: str,
    store: str,
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setenv(profile_var, "relative")
    (checkout := uv_home / "checkout").mkdir()
    monkeypatch.chdir(checkout)
    uv_plant(checkout / store / "python")

    assert uv_probed() == []


def test_discovery_uv_store_windows_ignores_xdg_data_home(
    uv_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    uv_plant: Callable[[Path], str],
    uv_probed: Callable[..., list[str]],
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("XDG_DATA_HOME", str(uv_home / "xdg"))
    uv_plant(uv_home / "xdg" / "uv" / "python")
    executable = uv_plant(uv_home / "AppData" / "Roaming" / "uv" / "python")

    assert uv_probed() == [executable]


def test_discovery_uv_store_reads_the_env_argument(
    uv_home: Path, uv_plant: Callable[[Path], str], uv_probed: Callable[..., list[str]]
) -> None:
    executable = uv_plant(uv_home / "store")

    assert uv_probed(env={"PATH": "", "UV_PYTHON_INSTALL_DIR": str(uv_home / "store")}) == [executable]


@pytest.mark.parametrize(
    ("platform", "store"),
    [
        pytest.param("win32", "AppData/Roaming/uv/data", id="windows"),
        pytest.param("darwin", "Library/Application Support/uv", id="macos"),
        pytest.param("linux", ".local/share/uv", id="linux"),
    ],
)
def test_discovery_uv_store_ignores_process_home_without_mapped_home(
    uv_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    uv_plant: Callable[[Path], str],
    uv_probed: Callable[..., list[str]],
    platform: str,
    store: str,
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    uv_plant(uv_home / store / "python")

    assert uv_probed(env={"PATH": ""}) == []


@pytest.mark.parametrize(
    ("platform", "variable", "store"),
    [
        pytest.param("win32", "APPDATA", "uv/data", id="windows-appdata"),
        pytest.param("darwin", "XDG_DATA_HOME", "uv", id="macos-xdg"),
        pytest.param("linux", "XDG_DATA_HOME", "uv", id="linux-xdg"),
    ],
)
def test_discovery_uv_store_uses_mapped_directory_without_home(
    uv_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    uv_plant: Callable[[Path], str],
    uv_probed: Callable[..., list[str]],
    platform: str,
    variable: str,
    store: str,
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    mapped = uv_home / "mapped"
    executable = uv_plant(mapped / store / "python")

    assert uv_probed(env={"PATH": "", variable: str(mapped)}) == [executable]


@pytest.mark.usefixtures("uv_home")
def test_discovery_uv_store_missing_root_is_not_an_error(uv_probed: Callable[..., list[str]]) -> None:
    assert uv_probed() == []


def test_discovery_uv_store_is_searched_after_path(
    uv_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    uv_plant: Callable[[Path], str],
    uv_probed: Callable[..., list[str]],
) -> None:
    store_executable = uv_plant(uv_home / ("AppData/Roaming/uv/data" if IS_WIN else ".local/share/uv") / "python")
    (path_dir := uv_home / "path-bin").mkdir()
    (path_executable := path_dir / f"python{_NO_UV_MATCH}{'.exe' if IS_WIN else ''}").touch()
    monkeypatch.setenv("PATH", str(path_dir))

    assert uv_probed() == [str(path_executable), store_executable]


@pytest.mark.parametrize(
    ("spec", "install_version", "releaselevel", "expected"),
    [
        pytest.param("==3.99", "3.99.2", "final", True, id="minor-equality"),
        pytest.param(">=3.99,<3.100", "3.99.2", "final", True, id="minor-range"),
        pytest.param("==3.98", "3.99.2", "final", False, id="different-minor"),
        pytest.param(">=3.99a1", "3.99a2", "alpha", True, id="alpha"),
        pytest.param(">=3.99", "3.99a2", "alpha", True, id="alpha-minor-bound"),
        pytest.param(">=3.99b1", "3.99b2", "beta", True, id="beta"),
        pytest.param(">=3.99rc1", "3.99rc2", "candidate", True, id="candidate"),
    ],
)
def test_discovery_uv_patch_release_matches_minor_spec(
    tmp_path: Path, mocker: MockerFixture, spec: str, install_version: str, releaselevel: str, expected: bool
) -> None:
    store = tmp_path / "uv"
    executable = store / f"cpython-{install_version}-linux-x86_64-gnu" / "bin" / "python"
    executable.parent.mkdir(parents=True)
    executable.touch()
    info = deepcopy(PythonInfo.current_system())
    info.executable = str(executable)
    info.system_executable = str(executable)
    info.version_info = info.version_info._replace(
        major=3, minor=99, micro=2 if releaselevel == "final" else 0, releaselevel=releaselevel, serial=2
    )
    mocker.patch("python_discovery._discovery.PathPythonInfo.from_exe", return_value=info)

    found = get_interpreter(spec, [], env={"PATH": "", "UV_PYTHON_INSTALL_DIR": str(store)})

    assert (found is info) is expected


def test_discovery_uv_invalid_hand_built_spec_skips_install(tmp_path: Path, mocker: MockerFixture) -> None:
    store = tmp_path / "uv"
    executable = store / "cpython-3.99.2-linux-x86_64-gnu" / "bin" / "python"
    executable.parent.mkdir(parents=True)
    executable.touch()
    spec = PythonSpec.from_string_spec("==3.99")
    spec.version_specifier = SimpleSpecifierSet.from_string("==invalid")
    info = deepcopy(PythonInfo.current_system())
    info.executable = str(executable)
    mocker.patch("python_discovery._discovery.PathPythonInfo.from_exe", return_value=info)

    candidates = list(propose_interpreters(spec, [], env={"PATH": "", "UV_PYTHON_INSTALL_DIR": str(store)}))

    assert all(candidate is not info for candidate, _ in candidates)
