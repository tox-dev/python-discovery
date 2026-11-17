from __future__ import annotations

import contextlib
import copy
import itertools
import json
import logging
import os
import sys
import sysconfig
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING, Final, NamedTuple

import pytest
from packaging.markers import default_environment
from setuptools.dist import Distribution

from python_discovery import DiskCache, MarkerEnvironment, PyInfoCache, PythonInfo, PythonSpec, SimpleSpecifierSet
from python_discovery._py_info import EXTENSIONS, VersionInfo

if TYPE_CHECKING:
    from packaging.markers import Environment
    from pytest_mock import MockerFixture


_IS_PYPY: Final[bool] = PythonInfo.current_system().implementation == "PyPy"

_CURRENT: Final[PythonInfo] = PythonInfo.current_system()
_EXECUTABLE_SUFFIX: Final[str] = Path(_CURRENT.executable).suffix if sys.platform == "win32" else ""
_ORIGINAL_SUFFIX: Final[str] = Path(_CURRENT.original_executable).suffix if sys.platform == "win32" else ""
_THREADED: Final[str] = "t" if _CURRENT.free_threaded else ""
_UNTHREADED: Final[str] = "" if _CURRENT.free_threaded else "t"
_OTHER_ARCHITECTURE: Final[int] = {32: 64, 64: 32}[_CURRENT.architecture]


@pytest.mark.graalpy
def test_current_as_json() -> None:
    parsed = json.loads(_CURRENT.to_json())
    major, minor, micro, releaselevel, serial = sys.version_info
    free_threaded = sysconfig.get_config_var("Py_GIL_DISABLED") == 1
    assert parsed["version_info"] == {
        "major": major,
        "minor": minor,
        "micro": micro,
        "releaselevel": releaselevel,
        "serial": serial,
    }
    assert parsed["free_threaded"] is free_threaded
    assert parsed["debug_build"] is bool(sysconfig.get_config_var("Py_DEBUG"))


def test_bad_exe_py_info_raise(tmp_path: Path, session_cache: DiskCache) -> None:
    exe = str(tmp_path)
    with pytest.raises(RuntimeError) as context:
        PythonInfo.from_exe(exe, session_cache)
    msg = str(context.value)
    assert "code" in msg
    assert exe in msg


def test_bad_exe_py_info_no_raise(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
    session_cache: DiskCache,
) -> None:
    caplog.set_level(logging.NOTSET)
    exe = str(tmp_path)
    result = PythonInfo.from_exe(exe, session_cache, raise_on_error=False)
    assert result is None
    out, _ = capsys.readouterr()
    assert not out
    messages = [r.message for r in caplog.records if r.name != "filelock"]
    assert len(messages) == 4
    assert "get interpreter info via cmd: " in messages[0]
    assert "retrying" in messages[1]
    assert "get interpreter info via cmd: " in messages[2]
    assert str(exe) in messages[3]
    assert "code" in messages[3]


@pytest.mark.parametrize(
    "spec",
    [sys.executable]
    + [
        f"{impl}{'.'.join(str(i) for i in ver)}{'t' if _CURRENT.free_threaded else ''}{arch}"
        for impl, ver, arch in itertools.product(
            (
                [_CURRENT.implementation]
                + (["python"] if _CURRENT.implementation == "CPython" else [])
                + (
                    [_CURRENT.implementation.lower()]
                    if _CURRENT.implementation != _CURRENT.implementation.lower()
                    else []
                )
            ),
            [sys.version_info[0 : i + 1] for i in range(3)],
            ["", f"-{_CURRENT.architecture}"],
        )
    ],
)
def test_satisfy_py_info(spec: str) -> None:
    matches = _CURRENT.satisfies(PythonSpec.from_string_spec(spec), impl_must_match=True)
    assert matches is True


def test_satisfy_not_arch() -> None:
    parsed_spec = PythonSpec.from_string_spec(
        f"{_CURRENT.implementation}-{_OTHER_ARCHITECTURE}",
    )
    matches = _CURRENT.satisfies(parsed_spec, impl_must_match=True)
    assert matches is False


def test_satisfy_not_threaded() -> None:
    parsed_spec = PythonSpec.from_string_spec(
        f"{_CURRENT.implementation}{_CURRENT.version_info.major}{_UNTHREADED}",
    )
    matches = _CURRENT.satisfies(parsed_spec, impl_must_match=True)
    assert matches is False


def _generate_not_match_current_interpreter_version() -> list[str]:
    result: list[str] = []
    for depth in range(3):
        ver: list[int] = [int(part) for part in sys.version_info[0 : depth + 1]]
        for idx in range(len(ver)):
            for offset in [-1, 1]:
                temp = ver.copy()
                temp[idx] += offset
                result.append(".".join(str(part) for part in temp))
    return result


_NON_MATCH_VER: Final[list[str]] = _generate_not_match_current_interpreter_version()


@pytest.mark.parametrize("spec", _NON_MATCH_VER)
def test_satisfy_not_version(spec: str) -> None:
    matches = _CURRENT.satisfies(PythonSpec.from_string_spec(f"{_CURRENT.implementation}{spec}"), impl_must_match=True)
    assert matches is False


def test_py_info_cached_error(caplog: pytest.LogCaptureFixture, tmp_path: Path, session_cache: DiskCache) -> None:
    caplog.set_level(logging.DEBUG)
    with pytest.raises(RuntimeError):
        PythonInfo.from_exe(str(tmp_path), session_cache)
    with pytest.raises(RuntimeError):
        PythonInfo.from_exe(str(tmp_path), session_cache)
    assert sum("get interpreter info via cmd:" in message for message in caplog.messages) == 4


def test_py_info_cache_clear(caplog: pytest.LogCaptureFixture, session_cache: DiskCache) -> None:
    result = PythonInfo.from_exe(sys.executable, session_cache)
    assert result is not None

    PythonInfo.clear_cache(session_cache)
    caplog.set_level(logging.DEBUG)
    info = PythonInfo.from_exe(sys.executable, session_cache)
    assert info is not None
    assert any("get interpreter info via cmd:" in message for message in caplog.messages)


class PyInfoMock(NamedTuple):
    implementation: str
    architecture: int
    version_info: VersionInfo


@pytest.mark.parametrize(
    ("target", "position", "discovered"),
    [
        pytest.param(
            PyInfoMock("CPython", 64, VersionInfo(3, 6, 8, "final", 0)),
            0,
            [
                PyInfoMock("CPython", 64, VersionInfo(3, 6, 9, "final", 0)),
                PyInfoMock("PyPy", 64, VersionInfo(3, 6, 8, "final", 0)),
            ],
            id="pypy-candidate-3.6.8",
        ),
        pytest.param(
            PyInfoMock("CPython", 64, VersionInfo(3, 6, 8, "final", 0)),
            0,
            [
                PyInfoMock("CPython", 64, VersionInfo(3, 6, 9, "final", 0)),
                PyInfoMock("CPython", 32, VersionInfo(3, 6, 9, "final", 0)),
            ],
            id="cpython-32bit-candidate-3.6.9",
        ),
        pytest.param(
            PyInfoMock("CPython", 64, VersionInfo(3, 8, 1, "final", 0)),
            0,
            [
                PyInfoMock("CPython", 32, VersionInfo(2, 7, 12, "rc", 2)),
                PyInfoMock("PyPy", 64, VersionInfo(3, 8, 1, "final", 0)),
            ],
            id="pypy-candidate-3.8.1",
        ),
    ],
)
def test_system_executable_no_exact_match(
    target: PyInfoMock,
    discovered: list[PyInfoMock],
    position: int,
    *,
    tmp_path: Path,
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
    session_cache: DiskCache,
) -> None:
    caplog.set_level(logging.DEBUG)

    def _make_py_info(of: PyInfoMock) -> PythonInfo:
        base = copy.deepcopy(_CURRENT)
        base.implementation = of.implementation
        base.version_info = of.version_info
        base.architecture = of.architecture
        return base

    discovered_with_path: dict[str, PythonInfo] = {}
    names: list[str] = []
    for pos, info in enumerate(discovered):
        path = tmp_path / str(pos)
        path.write_text("", encoding="utf-8")
        py_info = _make_py_info(info)
        system_executable = _CURRENT.system_executable
        assert system_executable is not None
        py_info.system_executable = system_executable
        py_info.executable = system_executable
        discovered_with_path[str(path)] = py_info
        names.append(path.name)

    target_py_info = _make_py_info(target)
    mocker.patch.object(target_py_info, "_find_possible_exe_names", return_value=names, autospec=True)
    mocker.patch.object(target_py_info, "_find_possible_folders", return_value=[str(tmp_path)], autospec=True)

    def func(exe_path: str, _cache: PyInfoCache | None = None, **_kwargs: object) -> PythonInfo:
        return discovered_with_path[exe_path]

    mocker.patch.object(target_py_info, "from_exe", side_effect=func, autospec=True)
    target_py_info.real_prefix = str(tmp_path)

    target_py_info.system_executable = None
    target_py_info.executable = str(tmp_path)
    mapped = target_py_info.resolve_to_system(session_cache, target_py_info)
    assert mapped.system_executable == _CURRENT.system_executable
    expected = discovered_with_path[str(tmp_path / str(position))]
    assert (mapped.implementation, mapped.architecture, mapped.version_info) == (
        expected.implementation,
        expected.architecture,
        expected.version_info,
    )

    assert caplog.records[0].msg == "discover exe for %s in %s"
    for record in caplog.records[1:-1]:
        assert record.message.startswith("refused interpreter ")
        assert record.levelno == logging.DEBUG

    warn_similar = caplog.records[-1]
    assert warn_similar.levelno == logging.DEBUG
    assert warn_similar.msg.startswith("no exact match found, chosen most similar")


@pytest.mark.parametrize("attr", ["free_threaded", "debug_build"])
def test_discover_exe_validates_abi_flag(
    attr: str, tmp_path: Path, mocker: MockerFixture, session_cache: DiskCache
) -> None:
    def candidate(*, flag: bool, name: str) -> PythonInfo:
        info = copy.deepcopy(_CURRENT)
        setattr(info, attr, flag)
        exe = tmp_path / name
        exe.write_text("", encoding="utf-8")
        info.executable = str(exe)
        return info

    target = candidate(flag=True, name="target")
    mismatch = candidate(flag=False, name="release")
    match = candidate(flag=True, name="debug")
    by_path = {info.executable: info for info in (mismatch, match)}

    mocker.patch.object(target, "_find_possible_exe_names", return_value=["release", "debug"], autospec=True)
    mocker.patch.object(target, "_find_possible_folders", return_value=[str(tmp_path)], autospec=True)
    mocker.patch.object(target, "from_exe", side_effect=lambda exe, *_a, **_k: by_path[exe], autospec=True)

    found = target.discover_exe(session_cache, prefix=str(tmp_path), exact=True)
    assert found is match  # the release build is refused even though version, impl and arch match


def test_py_info_ignores_distutils_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    raw = f"""
    [install]
    prefix={tmp_path}{os.sep}prefix
    install_purelib={tmp_path}{os.sep}purelib
    install_platlib={tmp_path}{os.sep}platlib
    install_headers={tmp_path}{os.sep}headers
    install_scripts={tmp_path}{os.sep}scripts
    install_data={tmp_path}{os.sep}data
    """
    (tmp_path / "setup.cfg").write_text(dedent(raw), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    py_info = PythonInfo.from_exe(sys.executable)
    assert py_info is not None
    distutils = py_info.distutils_install
    for key, value in distutils.items():  # pragma: no cover # distutils_install is empty with "venv" scheme
        assert not value.startswith(str(tmp_path)), f"{key}={value}"


def test_discover_exe_on_path_non_spec_name_match(mocker: MockerFixture) -> None:
    suffixed_name = f"python{_CURRENT.version_info.major}.{_CURRENT.version_info.minor}m{_EXECUTABLE_SUFFIX}"
    spec = PythonSpec.from_string_spec(suffixed_name)
    mocker.patch.object(_CURRENT, "executable", str(Path(_CURRENT.executable).parent / suffixed_name))
    assert _CURRENT.satisfies(spec, impl_must_match=True) is True


def test_satisfies_debug_spec_requires_debug_build(mocker: MockerFixture) -> None:
    spec = PythonSpec.from_string_spec(f"python{_CURRENT.version_info.major}.{_CURRENT.version_info.minor}-dbg")
    assert spec.debug is True
    mocker.patch.object(_CURRENT, "free_threaded", spec.free_threaded)

    mocker.patch.object(_CURRENT, "debug_build", False)
    assert _CURRENT.satisfies(spec, impl_must_match=True) is False

    mocker.patch.object(_CURRENT, "debug_build", True)
    assert _CURRENT.satisfies(spec, impl_must_match=True) is True


def test_discover_exe_on_path_non_spec_name_not_match(mocker: MockerFixture) -> None:
    suffixed_name = f"python{_CURRENT.version_info.major}.{_CURRENT.version_info.minor}m{_ORIGINAL_SUFFIX}"
    spec = PythonSpec.from_string_spec(suffixed_name)
    mocker.patch.object(
        _CURRENT,
        "original_executable",
        str(Path(_CURRENT.executable).parent / f"e{suffixed_name}"),
    )
    assert _CURRENT.satisfies(spec, impl_must_match=True) is False


@pytest.mark.skipif(_IS_PYPY, reason="setuptools distutils patching does not work")
def test_py_info_setuptools() -> None:
    assert Distribution
    PythonInfo()


@pytest.mark.usefixtures("_skip_if_test_in_system")
def test_py_info_to_system_raises(  # pragma: no cover # skipped in venv environments
    session_cache: DiskCache,
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    mocker.patch.object(PythonInfo, "_find_possible_folders", return_value=[], autospec=True)
    result = PythonInfo.from_exe(sys.executable, cache=session_cache, raise_on_error=False)
    assert result is None
    log = caplog.records[-1]
    assert log.levelno == logging.INFO
    expected = f"ignore {sys.executable} due cannot resolve system due to RuntimeError('failed to detect "
    assert expected in log.message


def test_sysconfig_vars_include_shared_lib_keys() -> None:
    for key in ("Py_ENABLE_SHARED", "INSTSONAME", "LIBDIR"):
        assert key in _CURRENT.sysconfig_vars


def test_py_info_has_sysconfig_platform() -> None:
    assert hasattr(_CURRENT, "sysconfig_platform")
    assert _CURRENT.sysconfig_platform is not None
    assert isinstance(_CURRENT.sysconfig_platform, str)
    assert len(_CURRENT.sysconfig_platform) > 0


def test_py_info_machine_property() -> None:
    machine = _CURRENT.machine
    assert machine is not None
    assert isinstance(machine, str)
    assert len(machine) > 0
    assert machine == machine.lower(), f"machine value should be lowercase: {machine}"


def test_py_info_machine_in_spec() -> None:
    spec = _CURRENT.spec
    assert _CURRENT.machine in spec
    assert f"-{_CURRENT.architecture}-{_CURRENT.machine}" in spec


def test_py_info_sysconfig_platform_matches_sysconfig() -> None:
    assert _CURRENT.sysconfig_platform == sysconfig.get_platform()


@pytest.mark.parametrize(
    ("platform", "expected"),
    [
        pytest.param("win32", "x86", id="win32"),
        pytest.param("win-amd64", "x86_64", id="win-amd64"),
        pytest.param("win-arm64", "arm64", id="win-arm64"),
        pytest.param("linux-x86_64", "x86_64", id="linux-x86_64"),
        pytest.param("linux-aarch64", "arm64", id="linux-aarch64"),
        pytest.param("linux-riscv64", "riscv64", id="linux-riscv64"),
        pytest.param("linux-ppc64le", "ppc64le", id="linux-ppc64le"),
        pytest.param("linux-s390x", "s390x", id="linux-s390x"),
        pytest.param("macosx-14.0-arm64", "arm64", id="macos-arm64"),
        pytest.param("macosx-14.0-x86_64", "x86_64", id="macos-x86_64"),
    ],
)
def test_py_info_machine_derivation(platform: str, expected: str) -> None:
    info = copy.deepcopy(_CURRENT)
    info.sysconfig_platform = platform
    assert info.machine == expected


@pytest.mark.parametrize("runtime_isa", ["arm64", "x86_64"])
def test_py_info_machine_derivation_universal2(mocker: MockerFixture, runtime_isa: str) -> None:
    info = copy.deepcopy(_CURRENT)
    info.sysconfig_platform = "macosx-11.0-universal2"
    mocker.patch("python_discovery._py_info.platform.machine", return_value=runtime_isa, autospec=True)
    assert info.machine == runtime_isa


def test_py_info_satisfies_with_machine() -> None:
    threaded = _THREADED
    spec_str = (
        f"{_CURRENT.implementation}{_CURRENT.version_info.major}{threaded}-{_CURRENT.architecture}-{_CURRENT.machine}"
    )
    parsed_spec = PythonSpec.from_string_spec(spec_str)
    assert _CURRENT.satisfies(parsed_spec, impl_must_match=True) is True


def test_py_info_satisfies_not_machine() -> None:
    other_machine = {"arm64": "x86_64"}.get(_CURRENT.machine, "arm64")
    parsed_spec = PythonSpec.from_string_spec(f"{_CURRENT.implementation}-{_CURRENT.architecture}-{other_machine}")
    assert _CURRENT.satisfies(parsed_spec, impl_must_match=True) is False


def test_py_info_satisfies_no_machine_in_spec() -> None:
    spec_str = f"{_CURRENT.implementation}{_CURRENT.version_info.major}{_THREADED}-{_CURRENT.architecture}"
    parsed_spec = PythonSpec.from_string_spec(spec_str)
    assert parsed_spec.machine is None
    assert _CURRENT.satisfies(parsed_spec, impl_must_match=True) is True


@pytest.mark.parametrize(
    ("platform", "spec_machine"),
    [
        pytest.param("linux-x86_64", "amd64", id="amd64-matches-x86_64"),
        pytest.param("macosx-14.0-arm64", "aarch64", id="aarch64-matches-arm64"),
    ],
)
def test_py_info_satisfies_machine_cross_os_normalization(platform: str, spec_machine: str) -> None:
    info = copy.deepcopy(_CURRENT)
    info.sysconfig_platform = platform
    spec = PythonSpec.from_string_spec(f"{info.implementation}-{info.architecture}-{spec_machine}")
    assert info.satisfies(spec, impl_must_match=True) is True


@pytest.mark.parametrize("debug", [pytest.param(True, id="debug"), pytest.param(False, id="release")])
def test_py_info_debug_build_in_spec(*, debug: bool) -> None:
    info = copy.deepcopy(_CURRENT)
    info.debug_build = debug
    assert ("d-" in info.spec) is debug


@pytest.mark.parametrize("debug", [pytest.param(True, id="debug"), pytest.param(False, id="release")])
def test_py_info_debug_build_exe_names(*, debug: bool) -> None:
    info = copy.deepcopy(_CURRENT)
    info.debug_build = debug
    names = info._find_possible_exe_names()
    abiflag_name = f"python{info.version_info.major}.{info.version_info.minor}d"
    assert any("_d" in n for n in names) is debug
    assert any(n.endswith("-dbg") for n in names) is debug
    assert (abiflag_name in names) is debug


def test_py_info_debug_build_json_round_trip() -> None:
    info = copy.deepcopy(_CURRENT)
    info.debug_build = True
    restored = PythonInfo.from_json(info.to_json())
    assert restored.debug_build is True


def test_py_info_to_dict_includes_sysconfig_platform() -> None:
    data = _CURRENT.to_dict()
    assert "sysconfig_platform" in data
    assert data["sysconfig_platform"] == sysconfig.get_platform()


def test_py_info_to_dict_preserves_property_named_answer_key() -> None:
    data = _CURRENT.to_dict()
    data["system_include"] = "supplied path"
    assert PythonInfo.from_dict(data).to_dict()["system_include"] == "supplied path"


def test_py_info_json_round_trip() -> None:
    json_str = _CURRENT.to_json()
    parsed = json.loads(json_str)
    assert "sysconfig_platform" in parsed
    restored = PythonInfo.from_json(json_str)
    assert (restored.sysconfig_platform, restored.machine) == (_CURRENT.sysconfig_platform, _CURRENT.machine)


def test_marker_environment_matches_target_interpreter() -> None:
    info: Final[PythonInfo | None] = PythonInfo.from_exe(sys.executable, ignore_cache=True, resolve_to_host=False)
    assert info is not None
    assert info.marker_environment == default_environment()


def test_marker_environment_type_has_standard_keys() -> None:
    assert MarkerEnvironment.__required_keys__ == default_environment().keys()


def test_marker_environment_uses_target_platform(tmp_path: Path) -> None:
    (tmp_path / "sitecustomize.py").write_text(
        'import platform\nplatform.machine = lambda: "target-machine"\nplatform.release = lambda: "target-release"\n',
        encoding="utf-8",
    )
    expected: Final[Environment] = default_environment()
    assert expected["platform_machine"] != "target-machine"
    assert expected["platform_release"] != "target-release"
    info: Final[PythonInfo | None] = PythonInfo.from_exe(
        sys.executable,
        ignore_cache=True,
        resolve_to_host=False,
        env={**os.environ, "PYTHONPATH": str(tmp_path)},
    )
    assert info is not None
    assert info.marker_environment == {
        **expected,
        "platform_machine": "target-machine",
        "platform_release": "target-release",
    }


def test_marker_environment_survives_json_round_trip() -> None:
    assert PythonInfo.from_json(_CURRENT.to_json()).marker_environment == _CURRENT.marker_environment


def test_marker_environment_formats_prerelease(mocker: MockerFixture) -> None:
    version: Final[VersionInfo] = VersionInfo(*sys.implementation.version)
    mocker.patch.object(sys.implementation, "version", version._replace(releaselevel="candidate", serial=1))

    assert PythonInfo().marker_environment["implementation_version"] == (
        f"{version.major}.{version.minor}.{version.micro}c1"
    )


@pytest.mark.parametrize(
    ("target_platform", "discovered_platforms", "expected_idx"),
    [
        pytest.param("linux-x86_64", ["linux-aarch64", "linux-x86_64"], 1, id="x86_64-over-aarch64"),
        pytest.param("macosx-14.0-arm64", ["macosx-14.0-x86_64", "macosx-14.0-arm64"], 1, id="arm64-over-x86_64"),
    ],
)
def test_select_most_likely_prefers_machine_match(
    target_platform: str,
    discovered_platforms: list[str],
    expected_idx: int,
) -> None:
    target = copy.deepcopy(_CURRENT)
    target.sysconfig_platform = target_platform
    discovered = [copy.deepcopy(_CURRENT) for _ in discovered_platforms]
    for info, plat in zip(discovered, discovered_platforms):
        info.sysconfig_platform = plat
    result = PythonInfo._select_most_likely(discovered, target)
    assert result.sysconfig_platform == discovered_platforms[expected_idx]


@pytest.mark.parametrize(
    ("system_executable", "expected"),
    [
        pytest.param("/usr/bin/python3", "/usr/bin/python3", id="resolved"),
        pytest.param(None, "/venv/bin/python", id="unresolved falls back to executable"),
    ],
)
def test_py_info_system_exe(system_executable: str | None, expected: str) -> None:
    info = copy.deepcopy(_CURRENT)
    info.executable = "/venv/bin/python"
    info.system_executable = system_executable
    assert info.system_exe == expected


def test_py_info_pypy_version(mocker: MockerFixture) -> None:
    mocker.patch("platform.python_implementation", return_value="PyPy", autospec=True)
    mocker.patch.object(sys, "pypy_version_info", (7, 3, 11, "final", 0), create=True)
    info = PythonInfo()
    assert (info.implementation, info.pypy_version_info) == ("PyPy", (7, 3, 11, "final", 0))


def test_py_info_canonicalizes_graalvm(mocker: MockerFixture) -> None:
    mocker.patch("platform.python_implementation", return_value="GraalVM", autospec=True)
    info = PythonInfo()
    assert info.implementation == "GraalPy"


def test_has_venv_attribute() -> None:
    info = PythonInfo()
    assert isinstance(info.has_venv, bool)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX only")
@pytest.mark.skipif(bool(_CURRENT.sysconfig_vars.get("PYTHONFRAMEWORK")), reason="framework builds keep recorded path")
def test_from_exe_resolves_executable_only_symlink(  # pragma: no cover # skipped on framework interpreter hosts
    tmp_path: Path,
    session_cache: DiskCache,
) -> None:
    system_exe = _CURRENT.system_executable
    assert system_exe is not None
    link = tmp_path / "python3"
    link.symlink_to(system_exe)
    info = PythonInfo.from_exe(str(link), session_cache, ignore_cache=True)
    assert info is not None
    assert info.system_executable is not None
    assert Path(info.system_executable).samefile(system_exe)
    assert Path(info.system_executable).parent != tmp_path


def test_version_str() -> None:
    assert _CURRENT.version_str == ".".join(str(i) for i in sys.version_info[:3])


def test_version_release_str() -> None:
    assert _CURRENT.version_release_str == ".".join(str(i) for i in sys.version_info[:2])


def test_python_name() -> None:
    assert _CURRENT.python_name == f"python{sys.version_info.major}.{sys.version_info.minor}"


def test_is_old_virtualenv() -> None:
    info = copy.deepcopy(_CURRENT)
    info.real_prefix = "/some/prefix"
    assert info.is_old_virtualenv is True
    info.real_prefix = None
    assert info.is_old_virtualenv is False


def test_is_venv() -> None:
    assert _CURRENT.is_venv == (_CURRENT.base_prefix is not None)


def test_system_prefix() -> None:
    info = copy.deepcopy(_CURRENT)
    info.real_prefix = "/real"
    assert info.system_prefix == "/real"
    info.real_prefix = None
    info.base_prefix = "/base"
    assert info.system_prefix == "/base"


def test_system_exec_prefix() -> None:
    info = copy.deepcopy(_CURRENT)
    info.real_prefix = "/real"
    assert info.system_exec_prefix == "/real"
    info.real_prefix = None
    assert info.system_exec_prefix == info.base_exec_prefix or info.exec_prefix


def test_repr() -> None:
    result = repr(_CURRENT)
    assert "PythonInfo" in result


def test_str() -> None:
    result = str(_CURRENT)
    assert "PythonInfo" in result
    assert "spec=" in result


def test_machine_none_platform() -> None:
    info = copy.deepcopy(_CURRENT)
    info.sysconfig_platform = None
    assert info.machine == "unknown"


def test_from_json_round_trip() -> None:
    restored = PythonInfo.from_json(_CURRENT.to_json())
    assert (restored.version_info, restored.implementation) == (_CURRENT.version_info, _CURRENT.implementation)


def test_from_dict() -> None:
    restored = PythonInfo.from_dict(_CURRENT.to_dict())
    assert restored.version_info == _CURRENT.version_info


def test_resolve_to_system_circle(mocker: MockerFixture, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    target = copy.deepcopy(_CURRENT)
    target.system_executable = None
    target.real_prefix = None
    target.base_prefix = "/prefix_a"

    second = copy.deepcopy(_CURRENT)
    second.system_executable = None
    second.real_prefix = None
    second.base_prefix = "/prefix_b"

    third = copy.deepcopy(_CURRENT)
    third.system_executable = None
    third.real_prefix = None
    third.base_prefix = "/prefix_a"

    mocker.patch.object(PythonInfo, "discover_exe", side_effect=[second, third], autospec=True)

    with pytest.raises(RuntimeError, match="prefixes are causing a circle"):
        PythonInfo.resolve_to_system(None, target)


def test_resolve_to_system_single_prefix_self_link(mocker: MockerFixture, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    target = copy.deepcopy(_CURRENT)
    target.system_executable = None
    target.real_prefix = None
    target.base_prefix = "/prefix_a"

    second = copy.deepcopy(_CURRENT)
    second.system_executable = None
    second.real_prefix = None
    second.base_prefix = "/prefix_a"

    mocker.patch.object(PythonInfo, "discover_exe", return_value=second, autospec=True)

    result = PythonInfo.resolve_to_system(None, target)
    assert result.system_executable is not None
    assert any("links back to itself" in r.message for r in caplog.records)


def test_resolve_to_system_repeated_prefix_with_parent_segments(tmp_path: Path, mocker: MockerFixture) -> None:
    (tmp_path / "child").mkdir()
    target = PythonInfo()
    target.system_executable = target.real_prefix = None
    target.base_prefix = str(tmp_path)
    repeated = PythonInfo()
    repeated.system_executable = repeated.real_prefix = None
    repeated.base_prefix = str(tmp_path / "child" / "..")
    mocker.patch.object(PythonInfo, "discover_exe", return_value=repeated, autospec=True)

    result = PythonInfo.resolve_to_system(None, target)

    assert result.system_executable == repeated.executable


def test_discover_exe_cache_hit(mocker: MockerFixture) -> None:
    info = copy.deepcopy(_CURRENT)
    cached = copy.deepcopy(_CURRENT)
    PythonInfo._cache_exe_discovery["/some/prefix", True, info.version_info] = cached
    try:
        result = info.discover_exe(
            mocker.create_autospec(PyInfoCache, instance=True), prefix="/some/prefix", exact=True
        )
        assert result is cached
    finally:
        del PythonInfo._cache_exe_discovery["/some/prefix", True, info.version_info]


def test_discover_exe_cache_keeps_requested_version(tmp_path: Path) -> None:
    prefix = _CURRENT.prefix
    assert prefix is not None
    cache = DiskCache(tmp_path)
    PythonInfo.clear_cache(cache)
    try:
        found = _CURRENT.discover_exe(cache, prefix)
        assert found.version_info == _CURRENT.version_info
        other = copy.deepcopy(_CURRENT)
        other.version_info = other.version_info._replace(major=0)
        with pytest.raises(RuntimeError):
            other.discover_exe(cache, prefix)
    finally:
        PythonInfo.clear_cache(cache)


def test_check_exe_none_path(tmp_path: Path, mocker: MockerFixture) -> None:
    info = copy.deepcopy(_CURRENT)
    result = info._check_exe(
        mocker.create_autospec(PyInfoCache, instance=True),
        str(tmp_path),
        "nonexistent",
        [],
        dict(os.environ),
        exact=True,
    )
    assert result is None


def test_satisfies_version_specifier() -> None:
    spec = PythonSpec.from_string_spec(f">={sys.version_info.major}.{sys.version_info.minor}")
    assert _CURRENT.satisfies(spec, impl_must_match=False) is True


def test_satisfies_version_specifier_fails() -> None:
    spec = PythonSpec.from_string_spec(f">{sys.version_info.major + 1}")
    assert _CURRENT.satisfies(spec, impl_must_match=False) is False


@pytest.mark.parametrize(
    ("suffix", "expected"),
    [
        pytest.param("t", _CURRENT.free_threaded, id="free-threaded"),
        pytest.param("", True, id="any-build"),
    ],
)
def test_satisfies_version_specifier_free_threaded(suffix: str, expected: bool) -> None:
    spec = PythonSpec.from_string_spec(f">={sys.version_info.major}.{sys.version_info.minor}{suffix}")
    assert _CURRENT.satisfies(spec, impl_must_match=False) is expected


def test_satisfies_version_specifier_unparsable_version() -> None:
    specifier = SimpleSpecifierSet.from_string(">=3.x")
    spec = PythonSpec(">=3.x", None, None, None, None, None, None, version_specifier=specifier)
    assert _CURRENT.satisfies(spec, impl_must_match=False) is False


@pytest.mark.parametrize(
    ("version_info", "spec_str", "expected"),
    [
        pytest.param(VersionInfo(3, 14, 0, "alpha", 1), ">=3.14.0a1", True, id="alpha_match_exact"),
        pytest.param(VersionInfo(3, 14, 0, "beta", 1), ">=3.14.0b1", True, id="beta_match_exact"),
        pytest.param(VersionInfo(3, 14, 0, "candidate", 1), ">=3.14.0rc1", True, id="rc_match_exact"),
        pytest.param(VersionInfo(3, 15, 0, "alpha", 6), ">=3.15", True, id="prerelease_match_major_minor"),
        pytest.param(VersionInfo(3, 15, 0, "alpha", 6), ">=3.15.0", False, id="prerelease_not_match_full_precision"),
        pytest.param(VersionInfo(3, 15, 0, "alpha", 5), "<3.15.0a6", True, id="earlier_prerelease_less_than"),
        pytest.param(VersionInfo(3, 15, 0, "alpha", 6), "<3.15.0a6", False, id="prerelease_not_less_than_itself"),
        pytest.param(VersionInfo(3, 12, 0, "candidate", 1), "<3.12.0", False, id="prerelease_not_below_final_bound"),
        pytest.param(VersionInfo(3, 15, 0, "alpha", 6), ">=3.15.0a6", True, id="prerelease_match_itself"),
        pytest.param(VersionInfo(3, 15, 0, "alpha", 6), ">=3.15.0a7", False, id="prerelease_not_match_later"),
        pytest.param(VersionInfo(3, 15, 0, "final", 0), ">=3.15.0a6", True, id="final_greater_than_prerelease"),
        pytest.param(VersionInfo(3, 15, 0, "final", 0), "<3.15.0a6", False, id="final_not_less_than_prerelease"),
        pytest.param(VersionInfo(3, 15, 0, "final", 0), ">=3.15", True, id="final_match_major_minor"),
        pytest.param(VersionInfo(3, 15, 1, "alpha", 1), ">=3.15.0", True, id="later_micro_prerelease_match"),
        pytest.param(VersionInfo(3, 13, 7, "final", 0), "~=3.10", True, id="compatible_release_later_minor"),
        pytest.param(VersionInfo(4, 0, 0, "final", 0), "~=3.10", False, id="compatible_release_next_major"),
        pytest.param(VersionInfo(3, 13, 0, "alpha", 1), "~=3.12.0", False, id="compatible_release_next_minor_alpha"),
    ],
)
def test_satisfies_version_specifier_prerelease(version_info: VersionInfo, spec_str: str, expected: bool) -> None:
    info = copy.deepcopy(_CURRENT)
    info.version_info = version_info
    spec = PythonSpec.from_string_spec(spec_str)
    assert info.satisfies(spec, impl_must_match=False) is expected


def test_satisfies_path_not_abs_basename_match() -> None:
    info = copy.deepcopy(_CURRENT)
    # stem drops everything from the first dot, so python3.15t arrives as python3 and stops naming a free-threaded
    # build; only the Windows .exe belongs off the end.
    spec = PythonSpec.from_string_spec(Path(info.original_executable).name.removesuffix(".exe"))
    assert info.satisfies(spec, impl_must_match=False) is True


def test_satisfies_path_not_abs_basename_no_match() -> None:
    info = copy.deepcopy(_CURRENT)
    spec = PythonSpec.from_string_spec("completely_different_name")
    assert info.satisfies(spec, impl_must_match=False) is False


@pytest.mark.skipif(sys.platform == "win32", reason="win32 tested separately")
def test_satisfies_path_win32(mocker: MockerFixture) -> None:
    info = copy.deepcopy(_CURRENT)
    mocker.patch.object(sys, "platform", "win32")
    info.executable = "/some/path/python.exe"
    spec = PythonSpec.from_string_spec("python")
    spec.path = "python"
    assert info.satisfies(spec, impl_must_match=False) is True


def test_install_path() -> None:
    assert isinstance(_CURRENT.install_path("purelib"), str)


def test_install_path_rejects_format_width() -> None:
    info = copy.deepcopy(_CURRENT)
    info.distutils_install = {}
    info.sysconfig_paths["purelib"] = "{base:>1000000}/lib"
    with pytest.raises(ValueError, match="format specifiers"):
        info.install_path("purelib")


def test_system_include() -> None:
    result = _CURRENT.system_include
    assert isinstance(result, str)


@pytest.mark.parametrize(
    ("distutils_install", "existing", "expected"),
    [
        pytest.param({}, [], "include", id="no-headers-path"),
        pytest.param({"headers": "headers/UNKNOWN"}, ["headers"], "headers", id="headers"),
        pytest.param({"headers": "headers/UNKNOWN"}, [], "include", id="headers-missing"),
        pytest.param({"headers": "headers/UNKNOWN"}, ["include", "headers"], "include", id="include-present"),
    ],
)
def test_system_include_fallback(
    tmp_path: Path, distutils_install: dict[str, str], existing: list[str], expected: str
) -> None:
    info = copy.deepcopy(_CURRENT)
    info.prefix, info.base_prefix, info.real_prefix = str(tmp_path), None, None
    info.sysconfig_vars = {"base": str(tmp_path)}
    info.sysconfig_paths = {"include": "{base}/include"}
    info.distutils_install = distutils_install
    for name in existing:
        (tmp_path / name).mkdir()
    assert info.system_include == str(tmp_path / expected)


def test_sysconfig_path_missing_key() -> None:
    assert not _CURRENT.sysconfig_path("nonexistent_key")


def test_sysconfig_path_with_config_var() -> None:
    result = _CURRENT.sysconfig_path("stdlib", {})
    assert isinstance(result, str)


def test_current_system_cached(session_cache: DiskCache) -> None:
    PythonInfo._current_system = None
    result1 = PythonInfo.current_system(session_cache)
    result2 = PythonInfo.current_system(session_cache)
    assert result1 is result2


def test_current_cached(session_cache: DiskCache) -> None:
    PythonInfo._current = None
    result1 = PythonInfo.current(session_cache)
    result2 = PythonInfo.current(session_cache)
    assert result1 is result2


def test_from_exe_resolve_error(mocker: MockerFixture, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    fake_info = PythonInfo()
    fake_info.original_executable = "/fake/python"
    mocker.patch(
        "python_discovery._cached_py_info.from_exe",
        return_value=fake_info,
        autospec=True,
    )
    mocker.patch.object(PythonInfo, "resolve_to_system", side_effect=RuntimeError("test error"), autospec=True)
    result = PythonInfo.from_exe(sys.executable, raise_on_error=False, resolve_to_host=True)
    assert result is None
    assert any("cannot resolve system" in r.message for r in caplog.records)


def test_sysconfig_path_no_config_var() -> None:
    result = _CURRENT.sysconfig_path("stdlib")
    assert isinstance(result, str)
    assert len(result) > 0


def test_satisfies_abs_spec_path_falls_through(tmp_path: Path) -> None:
    info = copy.deepcopy(_CURRENT)
    spec = PythonSpec("", None, None, None, None, None, str(tmp_path / "other" / "python"))
    assert spec.is_abs is True
    assert info.satisfies(spec, impl_must_match=False) is True


def test_satisfies_abs_spec_path_match() -> None:
    info = copy.deepcopy(_CURRENT)
    spec = PythonSpec("", None, None, None, None, None, info.executable)
    assert info.satisfies(spec, impl_must_match=False) is True


def test_current_returns_none_raises(mocker: MockerFixture) -> None:
    PythonInfo._current = None
    mocker.patch.object(PythonInfo, "from_exe", return_value=None, autospec=True)
    with pytest.raises(RuntimeError, match="failed to query current Python interpreter"):
        PythonInfo.current()
    PythonInfo._current = None


def test_current_system_returns_none_raises(mocker: MockerFixture) -> None:
    PythonInfo._current_system = None
    mocker.patch.object(PythonInfo, "from_exe", return_value=None, autospec=True)
    with pytest.raises(RuntimeError, match="failed to query current system Python interpreter"):
        PythonInfo.current_system()
    PythonInfo._current_system = None


def test_check_exe_from_exe_returns_none(tmp_path: Path, mocker: MockerFixture) -> None:
    info = copy.deepcopy(_CURRENT)
    (tmp_path / "python").touch()
    mocker.patch.object(PythonInfo, "from_exe", return_value=None, autospec=True)
    result = info._check_exe(
        mocker.create_autospec(PyInfoCache, instance=True), str(tmp_path), "python", [], dict(os.environ), exact=True
    )
    assert result is None


def test_check_exe_mismatch_not_exact(tmp_path: Path, mocker: MockerFixture) -> None:
    info = copy.deepcopy(_CURRENT)
    (tmp_path / "python").touch()
    other = copy.deepcopy(_CURRENT)
    other.architecture = {32: 64, 64: 32}[info.architecture]
    mocker.patch.object(PythonInfo, "from_exe", return_value=other, autospec=True)
    discovered: list[PythonInfo] = []
    result = info._check_exe(
        mocker.create_autospec(PyInfoCache, instance=True),
        str(tmp_path),
        "python",
        discovered,
        dict(os.environ),
        exact=False,
    )
    assert result is None
    assert len(discovered) == 1


def test_check_exe_mismatch_exact(tmp_path: Path, mocker: MockerFixture) -> None:
    info = copy.deepcopy(_CURRENT)
    (tmp_path / "python").touch()
    other = copy.deepcopy(_CURRENT)
    other.architecture = {32: 64, 64: 32}[info.architecture]
    mocker.patch.object(PythonInfo, "from_exe", return_value=other, autospec=True)
    discovered: list[PythonInfo] = []
    result = info._check_exe(
        mocker.create_autospec(PyInfoCache, instance=True),
        str(tmp_path),
        "python",
        discovered,
        dict(os.environ),
        exact=True,
    )
    assert result is None
    assert len(discovered) == 0


def test_find_possible_exe_names_free_threaded() -> None:
    info = copy.deepcopy(_CURRENT)
    info.free_threaded = True
    names = info._find_possible_exe_names()
    assert any("t" in n for n in names)


def test_possible_base_python_basename() -> None:
    info = copy.deepcopy(_CURRENT)
    info.executable = "/usr/bin/python"
    info.implementation = "CPython"
    names = list(info._possible_base())
    assert "python" in names
    assert "cpython" in names


def test_possible_base_case_sensitive(mocker: MockerFixture) -> None:
    info = copy.deepcopy(_CURRENT)
    info.executable = "/usr/bin/CPython3.12"
    info.implementation = "CPython"
    mocker.patch("python_discovery._compat.fs_is_case_sensitive", return_value=True, autospec=True)
    names = list(info._possible_base())
    lower_names = [n for n in names if n.islower()]
    upper_names = [n for n in names if n.isupper()]
    assert len(lower_names) >= 1
    assert len(upper_names) >= 1


def test_possible_base_case_sensitive_upper_equals_base(mocker: MockerFixture) -> None:
    info = copy.deepcopy(_CURRENT)
    info.executable = "/usr/bin/JYTHON"
    info.implementation = "JYTHON"
    mocker.patch("python_discovery._compat.fs_is_case_sensitive", return_value=True, autospec=True)
    names = list(info._possible_base())
    assert "jython" in names
    assert "JYTHON" in names


def test_resolve_to_system_resolved_from_exe(mocker: MockerFixture, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    target = copy.deepcopy(_CURRENT)
    target.system_executable = "/some/system/python"
    target.executable = "/some/venv/python"

    resolved = copy.deepcopy(_CURRENT)
    resolved.system_executable = "/some/system/python"
    resolved.executable = "/some/system/python"

    mocker.patch.object(PythonInfo, "from_exe", return_value=resolved, autospec=True)
    result = PythonInfo.resolve_to_system(None, target)
    assert result.executable == "/some/venv/python"


def test_from_exe_uses_supplied_environment_for_base_probe(
    mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PYTHONPATH", "process-only")
    target = copy.deepcopy(_CURRENT)
    target.executable = "venv"
    target.system_executable = "system"
    mapped = copy.deepcopy(_CURRENT)
    mapped.executable = mapped.system_executable = "system"
    mapped.path = ["mapped"]
    process_only = copy.deepcopy(mapped)
    process_only.path = ["process-only"]
    mocker.patch(
        "python_discovery._cached_py_info.from_exe",
        side_effect=lambda _cls, _cache, exe, **kwargs: {
            "venv": target,
            "system": mapped if kwargs["env"] == {"PYTHONPATH": "mapped"} else process_only,
        }[exe],
        autospec=True,
    )

    info = PythonInfo.from_exe("venv", env={"PYTHONPATH": "mapped"})

    assert info is not None
    assert info.path == ["mapped"]


def test_resolve_to_system_uses_supplied_environment_for_prefix_probe(mocker: MockerFixture) -> None:
    target = copy.deepcopy(_CURRENT)
    target.system_executable = None
    target.real_prefix = None
    target.base_prefix = "/prefix"

    mapped = copy.deepcopy(_CURRENT)
    mapped.path = ["mapped"]
    mapped.system_executable = mapped.executable
    fallback = copy.deepcopy(_CURRENT)
    fallback.path = ["process"]
    fallback.system_executable = fallback.executable
    mocker.patch.object(
        PythonInfo,
        "discover_exe",
        side_effect=lambda _cls, _cache, **kwargs: (
            mapped if kwargs.get("env") == {"PYTHONPATH": "mapped"} else fallback
        ),
        autospec=True,
    )

    resolved = PythonInfo.resolve_to_system(None, target, env={"PYTHONPATH": "mapped"})

    assert resolved.path == ["mapped"]


def test_resolve_to_system_from_exe_returns_none(mocker: MockerFixture) -> None:
    target = copy.deepcopy(_CURRENT)
    target.system_executable = "/some/system/python"
    target.executable = "/some/venv/python"

    mocker.patch.object(PythonInfo, "from_exe", return_value=None, autospec=True)
    result = PythonInfo.resolve_to_system(None, target)
    assert result.executable == "/some/venv/python"


@pytest.mark.parametrize(
    "system_executable",
    [
        pytest.param("/some/system/python", id="resolved"),
        pytest.param(None, id="discovered"),
    ],
)
def test_resolve_to_system_leaves_shared_info_untouched(mocker: MockerFixture, system_executable: str | None) -> None:
    shared = copy.deepcopy(_CURRENT)
    shared.system_executable = shared.executable = "/some/system/python"
    mocker.patch.object(PythonInfo, "from_exe", return_value=shared, autospec=True)
    mocker.patch.object(PythonInfo, "discover_exe", return_value=shared, autospec=True)

    results: list[PythonInfo] = []
    for venv in ("/some/venv-a", "/some/venv-b"):
        target = copy.deepcopy(_CURRENT)
        target.system_executable = system_executable
        target.real_prefix, target.base_prefix, target.executable = None, venv, f"{venv}/python"
        results.append(PythonInfo.resolve_to_system(None, target))

    assert [(info.executable, info.system_executable) for info in results] == [
        ("/some/venv-a/python", "/some/system/python"),
        ("/some/venv-b/python", "/some/system/python"),
    ]
    assert shared.executable == "/some/system/python"


def test_resolve_to_system_returns_target_when_executable_unchanged() -> None:
    target = copy.deepcopy(_CURRENT)
    target.system_executable = target.executable = "/some/system/python"
    assert PythonInfo.resolve_to_system(None, target) is target


_DISCOVERY_CURRENT: Final[PythonInfo] = PythonInfo.current()
_DISCOVERY_THREADED: Final[str] = "t" if _DISCOVERY_CURRENT.free_threaded else ""


def _fs_supports_symlink() -> bool:
    return sys.platform != "win32"


def test_discover_empty_folder(tmp_path: Path, session_cache: DiskCache) -> None:
    with pytest.raises(RuntimeError):
        _DISCOVERY_CURRENT.discover_exe(session_cache, prefix=str(tmp_path))


def _discover_base_folders() -> tuple[str, ...]:
    exe_dir = str(Path(_DISCOVERY_CURRENT.executable).parent)
    folders: dict[str, None] = {}
    if (
        exe_dir.startswith(_DISCOVERY_CURRENT.prefix)
        and (  # pragma: no branch, the branch depends on the host interpreter layout
            relative := exe_dir[len(_DISCOVERY_CURRENT.prefix) :].lstrip("/\\")
        )
    ):
        folders[relative] = None
    folders["."] = None
    return tuple(folders)


_BASE: Final[tuple[str, ...]] = _discover_base_folders()


@pytest.mark.skipif(not _fs_supports_symlink(), reason="symlink is not supported")
@pytest.mark.parametrize("suffix", sorted({".exe", ""} & set(EXTENSIONS) if sys.platform == "win32" else [""]))
@pytest.mark.parametrize("into", _BASE)
@pytest.mark.parametrize(
    "arch",
    [pytest.param(_DISCOVERY_CURRENT.architecture, id="current"), pytest.param("", id="empty")],
)
@pytest.mark.parametrize(
    "version", [".".join(str(i) for i in _DISCOVERY_CURRENT.version_info[0:i]) for i in range(3, 0, -1)]
)
@pytest.mark.parametrize(
    "impl",
    [pytest.param(_DISCOVERY_CURRENT.implementation, id="current"), pytest.param("python", id="python")],
)
def test_discover_ok(
    tmp_path: Path,
    suffix: str,
    impl: str,
    version: str,
    *,
    arch: int | str,
    into: str,
    caplog: pytest.LogCaptureFixture,
    session_cache: DiskCache,
) -> None:
    caplog.set_level(logging.DEBUG)
    folder = tmp_path / into
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"{impl}{version}{_DISCOVERY_THREADED}{f'-{arch}' * bool(arch)}{suffix}"
    Path(str(dest)).symlink_to(_DISCOVERY_CURRENT.executable)
    pyvenv = Path(_DISCOVERY_CURRENT.executable).parents[1] / "pyvenv.cfg"
    with contextlib.suppress(FileNotFoundError):
        (folder / pyvenv.name).write_text(pyvenv.read_text(encoding="utf-8"), encoding="utf-8")
    inside_folder = str(tmp_path)
    found = _DISCOVERY_CURRENT.discover_exe(session_cache, inside_folder).executable
    dest_str = str(dest)
    assert os.path.normcase(found) == os.path.normcase(dest_str)
    assert len(caplog.messages) >= 1, caplog.text
    assert "get interpreter info via cmd: " in caplog.text

    dest.rename(dest.parent / (f"{dest.name}-1"))
    PythonInfo.clear_cache(session_cache)
    with pytest.raises(RuntimeError):
        _DISCOVERY_CURRENT.discover_exe(session_cache, inside_folder)
