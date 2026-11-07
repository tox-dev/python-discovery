from __future__ import annotations

from typing import TYPE_CHECKING

from python_discovery._py_info import PythonInfo
from python_discovery._py_spec import PythonSpec

from ._pep514 import discover_pythons

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping

    from python_discovery._cache import PyInfoCache


def propose_interpreters(
    spec: PythonSpec,
    cache: PyInfoCache | None,
    env: Mapping[str, str],
) -> Generator[PythonInfo, None, None]:
    existing = list(discover_pythons())
    existing.sort(
        key=lambda item: (
            *tuple(-1 if j is None else j for j in item[1:4]),
            1 if item[0] == "PythonCore" else 0,
        ),
        reverse=True,
    )

    implementation_by_org: dict[str, str] = {
        "ContinuumAnalytics": "CPython",
        "PythonCore": "CPython",
    }
    for name, major, minor, arch, threaded, exe, executable_args in existing:
        implementation = implementation_by_org.get(name, name)

        skip_pre_filter = implementation.lower() != "cpython"
        registry_spec = PythonSpec("", implementation, major, minor, None, arch, exe, free_threaded=threaded)
        if skip_pre_filter or registry_spec.satisfies(spec):
            interpreter = Pep514PythonInfo._from_exe_with_args(  # ruff:ignore[private-member-access] same package; the Windows proposer builds the same info object
                exe,
                cache,
                env=env,
                executable_args=executable_args,
                raise_on_error=False,
            )
            if interpreter is not None and interpreter.satisfies(spec, impl_must_match=True):
                yield interpreter


class Pep514PythonInfo(PythonInfo):
    # A Python information acquired from PEP-514.
    ...


__all__ = [
    "Pep514PythonInfo",
    "propose_interpreters",
]
