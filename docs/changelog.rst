#################
 Release History
#################

.. towncrier-draft-entries::

.. towncrier release notes start

.. _release-1-9-3:

*********************
 v1.9.3 (2026-11-03)
*********************

.. _release-1-9-3-fixed:

Fixed
-----

- Reject generic Python executables when a requested implementation is unavailable (:pr:`239`) by :user:`gaborbernat`.
  (:issue:`238`)

.. _release-1-9-2:

*********************
 v1.9.2 (2026-11-03)
*********************

.. _release-1-9-2-fixed:

Fixed
-----

- Match literal interpreter names against the executable found on ``PATH``, including symlink names (:pr:`220`) by
  :user:`gaborbernat`. (:issue:`188`)
- Preserve a virtual environment selected through ``try_first_with`` instead of returning its base interpreter
  (:pr:`218`) by :user:`gaborbernat`. (:issue:`191`)
- Skip interpreter candidates that return JSON without usable interpreter metadata and continue searching (:pr:`231`) by
  :user:`gaborbernat`. (:issue:`197`)
- Reject format widths in interpreter sysconfig paths before they allocate oversized strings (:pr:`229`) by
  :user:`gaborbernat`. (:issue:`199`)
- Check the interpreter's reported implementation when a spec names a known implementation, regardless of its filename
  on ``PATH`` (:pr:`233`) by :user:`gaborbernat`. (:issue:`201`)
- Write interpreter cache entries as compact JSON to keep their size proportional to the interpreter response
  (:pr:`237`) by :user:`gaborbernat`. (:issue:`204`)
- Prevent an earlier virtual-environment lookup from reporting an executable under the wrong Python version (:pr:`215`)
  by :user:`gaborbernat`.
- Retry interpreter discovery without the cache when cache access fails (:pr:`216`) by :user:`gaborbernat`.
- Exclude prereleases of the final version named by an exclusive upper bound, such as ``<3.12.0`` rejecting
  ``3.12.0rc1`` (:pr:`217`) by :user:`gaborbernat`.
- Stop repeated interpreter queries when a virtual environment reports the same base prefix with different path
  spellings (:pr:`219`) by :user:`gaborbernat`.
- Limit candidate stdout and stderr during interpreter queries so a noisy candidate cannot exhaust the caller's memory
  (:pr:`223`) by :user:`gaborbernat`.
- Find uv-managed patch releases when a version specifier names only their major and minor version (:pr:`227`) by
  :user:`gaborbernat`.
- Handle interpreter paths containing non-UTF-8 filesystem bytes when using DiskCache (:pr:`230`) by
  :user:`gaborbernat`.
- Preserve interpreter-provided values when answer keys match computed properties during cache serialization (:pr:`234`)
  by :user:`gaborbernat`.
- Return after an interpreter query times out without leaving pipe readers blocked by a child process (:pr:`228`) by
  :user:`gaborbernat`.
- Use the supplied environment for base-interpreter probes when resolving a virtual environment (:pr:`225`) by
  :user:`gaborbernat`.

.. _release-1-9-2-security:

Security
--------

- When an explicit ``env`` mapping omits ``HOME`` or ``USERPROFILE``, uv-managed interpreter discovery no longer
  searches the process home directory (:pr:`236`) by :user:`gaborbernat`. (:issue:`200`)
- Skip relative ``PATH`` entries, including the working-directory entry in the Windows default search path, when
  discovering interpreters (:pr:`235`) by :user:`gaborbernat`. (:issue:`202`)
- Validate pyenv, mise and asdf version names before using them as directory names. A version file can no longer direct
  python-discovery's resolver to a binary outside the version manager's installation directory (:pr:`205`) by
  :user:`gaborbernat`.
- When imported from an archive, python-discovery now extracts its interpreter probe into a private temporary directory.
  This prevents the probe from importing modules supplied in the shared temp directory (:pr:`206`) by
  :user:`gaborbernat`.
- Bare interpreter names now search ``PATH`` without probing a matching file in the working directory. Use ``./name``
  when the working directory contains the intended interpreter (:pr:`207`) by :user:`gaborbernat`.
- Tcl/Tk library detection no longer executes Tk startup profile files from the home or working directory (:pr:`208`) by
  :user:`gaborbernat`.
- Discovery skips ``.python-version`` files over 4096 characters during shim resolution, limiting memory use and
  allowing a parent or global version to apply (:pr:`209`) by :user:`gaborbernat`.
- Discovery uses the profile default for empty or relative ``APPDATA`` and skips relative profile paths when finding
  uv-managed Pythons (:pr:`210`) by :user:`gaborbernat`.
- Tcl/Tk library detection no longer opens an X display, so an unresponsive display cannot block interpreter discovery.
  It can also find the Tk library on headless systems (:pr:`211`) by :user:`gaborbernat`.
- Skip PEP 514 registry entries with relative or non-string executable paths and continue interpreter discovery
  (:pr:`212`) by :user:`gaborbernat`.
- Skip untrusted disk cache directories and entries on POSIX, and replace cache files without following links
  (:pr:`213`) by :user:`gaborbernat`.
- Place POSIX cache locks in a restricted directory and preserve group sharing under a group-permissive umask
  (:pr:`214`) by :user:`gaborbernat`.
- Interpreter discovery no longer reuses pyenv shim results across projects. A version choice in one checkout cannot
  leave an unsupported-version verdict that blocks discovery in another project (:pr:`232`) by :user:`gaborbernat`.

.. _release-1-9-1:

*********************
 v1.9.1 (2026-11-02)
*********************

.. _release-1-9-1-fixed:

Fixed
-----

- List free-threaded and debug builds on ``PATH``, such as ``python3.13t``, ``python3.13d`` and ``python3.13-dbg``, when
  ``iter_interpreters()`` runs with no spec, as it already did for uv's ``+freethreaded`` and ``+debug`` installs
  (:pr:`181`) by :user:`darrenhuai` and :user:`gaborbernat`.
- Reuse preferred interpreter paths supplied as an iterator when trying multiple interpreter specifications (:pr:`180`)
  by :user:`subotac` and :user:`gaborbernat`.
- Stop ``PythonInfo.system_include`` reporting the interpreter's prefix as the include directory when the C headers are
  not installed, which happened on Python 3.11 and later and on Debian's 3.10; the missing sysconfig include path is
  returned instead (:pr:`182`) by :user:`darrenhuai` and :user:`gaborbernat`.

.. _release-1-9-0:

*********************
 v1.9.0 (2026-10-30)
*********************

.. _release-1-9-0-added:

Added
-----

- Expose the 11 marker keys through ``MarkerEnvironment`` for callers that type-check ``PythonInfo.marker_environment``
  (:pr:`179`) by :user:`gaborbernat`.

.. _release-1-8-0:

*********************
 v1.8.0 (2026-10-30)
*********************

.. _release-1-8-0-added:

Added
-----

- Expose the selected interpreter's dependency marker values as ``PythonInfo.marker_environment`` (:pr:`178`) by
  :user:`gaborbernat`.

.. _release-1-7-0:

*********************
 v1.7.0 (2026-10-30)
*********************

.. _release-1-7-0-added:

Added
-----

- Accept the free-threaded, debug, architecture and machine suffixes after a version specifier, as in ``>=3.13t`` or
  ``cpython>=3.11,<3.14-64``, and raise ``ValueError`` for a spec that starts with a comparison operator but does not
  parse, such as ``>=3.13.``, instead of looking it up as an executable name (:pr:`176`) by :user:`gaborbernat`.
  (:issue:`175`)

.. _release-1-7-0-fixed:

Fixed
-----

- Stop a ``.python-version`` file that is not valid UTF-8, or that cannot be read, from aborting discovery through a
  pyenv, mise or asdf shim; a stray byte no longer hides the versions it names, and an unreadable file is skipped like a
  missing one (:pr:`173`) by :user:`darrenhuai` and :user:`gaborbernat`.

.. _release-1-7-0-documentation:

Documentation
-------------

- Link every documentation page to its source and edit view on GitHub, and add a GitHub icon to the footer (:pr:`177`)
  by :user:`gaborbernat`. (:issue:`174`)

.. _release-1-6-7:

*********************
 v1.6.7 (2026-10-28)
*********************

.. _release-1-6-7-fixed:

Fixed
-----

- Rank uv's minor version links behind the concrete install on Windows too, where uv creates them as directory junctions
  that ``Path.is_symlink()`` does not report (:pr:`170`) by :user:`darrenhuai` and :user:`gaborbernat`.
- Stop a venv lookup from rewriting the ``executable`` of earlier results, ``PythonInfo.current()`` and
  ``PythonInfo.current_system()`` when they share its base interpreter (:pr:`171`) by :user:`darrenhuai` and
  :user:`gaborbernat`.

.. _release-1-6-6:

*********************
 v1.6.6 (2026-10-27)
*********************

.. _release-1-6-6-fixed:

Fixed
-----

- Treat version specifiers with an item that cannot be parsed, such as ``>=3.x``, ``>=3.12 <4`` or ``>=3.12,foo``, as
  literal executable paths instead of raising a bare ``AssertionError`` or ignoring the item during discovery
  (:pr:`157`) by :user:`darrenhuai` and :user:`gaborbernat`.
- Accept relative interpreter paths that step up a directory, such as ``../venv/bin/python``, which were found and
  queried but never matched the spec (:pr:`158`) by :user:`darrenhuai` and :user:`gaborbernat`.
- Match ``~=X.Y`` compatible-release specifiers against later minor versions, as PEP 440 defines, instead of only the
  same minor; ``~=3.10`` now accepts 3.11 and newer 3.x (:pr:`159`) by :user:`darrenhuai` and :user:`gaborbernat`.

.. _release-1-6-5:

*********************
 v1.6.5 (2026-10-27)
*********************

.. _release-1-6-5-packaging:

Packaging
---------

- Releases now run on the shared tox-dev/github-workflows pipeline, with a locked release toolchain and generated GitHub
  Release notes (:pr:`164`) by :user:`gaborbernat`.

.. _release-1-6-4:

*********************
 v1.6.4 (2026-10-19)
*********************

.. _release-1-6-4-documentation:

Documentation
-------------

- Clarify the executable paths accepted by ``try_first_with`` in the standalone usage example. (:pr:`150`) - by
  :user:`travisfortney`.

.. _release-1-6-3:

*********************
 v1.6.3 (2026-10-16)
*********************

.. _release-1-6-3-fixed:

Fixed
-----

- Treat specs with dot-only version components, such as ``python.``, as literal executable paths instead of raising
  ``IndexError`` - by :user:`harbinresearcher` and :user:`gaborbernat`. (:pr:`147`)
- Pass PEP 514 ``ExecutableArguments`` to registered Windows interpreters when querying them, so a registration that
  points at a launcher such as ``py.exe -3.11`` reports the interpreter it selects - by :user:`blouirts123` and
  :user:`gaborbernat`. (:pr:`148`)

.. _release-1-6-2:

*********************
 v1.6.2 (2026-10-10)
*********************

.. _release-1-6-2-added:

Added
-----

- Require Python 3.9 or newer for installation while still discovering Python 3.6 and 3.7 interpreters (:pr:`142`) - by
  :user:`gaborbernat`.

.. _release-1-6-2-fixed:

Fixed
-----

- Discard malformed interpreter cache entries and query the interpreter again, including entries with missing,
  non-string or unusable ``system_executable`` paths - by :user:`darrenhuai` and :user:`gaborbernat`. (:pr:`141`)
- Use the default interpreter query timeout and warn for invalid ``PY_DISCOVERY_TIMEOUT`` values. Accept ``inf`` or
  values above the subprocess wait limit to disable the timeout - by :user:`darrenhuai` and :user:`gaborbernat`.
  (:pr:`143`)

.. _release-1-6-1:

*********************
 v1.6.1 (2026-09-18)
*********************

.. _release-1-6-1-fixed:

Fixed
-----

- Skip empty ``PATH`` entries during interpreter discovery - by :user:`gaborbernat`. (:pr:`132`)

.. _release-1-6-1-documentation:

Documentation
-------------

- Document :attr:`~python_discovery.PythonInfo.system_exe` across the tutorial, the how-to guide and the explanation of
  how resolution reaches a base interpreter. The class diagram in the how-to guide had
  :attr:`~python_discovery.PythonInfo.system_executable` typed ``str`` rather than ``str | None`` - by
  :user:`gaborbernat`. (:pr:`128`)

.. _release-1-6-0:

*********************
 v1.6.0 (2026-08-28)
*********************

.. _release-1-6-0-added:

Added
-----

- :attr:`~python_discovery.PythonInfo.system_exe` returns the executable of the system Python an interpreter is based
  on, falling back to :attr:`~python_discovery.PythonInfo.executable` the way
  :meth:`~python_discovery.PythonInfo.resolve_to_system` does. :attr:`~python_discovery.PythonInfo.system_executable` is
  ``None`` until resolution runs, so every consumer had to narrow a value discovery has already settled - by
  :user:`gaborbernat`. (:pr:`127`)

.. _release-1-5-3:

*********************
 v1.5.3 (2026-08-24)
*********************

.. _release-1-5-3-fixed:

Fixed
-----

- Prefer the version-matched system executable when CPython reports an existing generic executable for a copied POSIX
  virtual environment. (:issue:`124`) - by :user:`gaborbernat`.

.. _release-1-5-2:

*********************
 v1.5.2 (2026-08-12)
*********************

.. _release-1-5-2-fixed:

Fixed
-----

- Restore discovery of Python 3.6 and 3.7 interpreters. Earlier interrogation used Python 3.8 syntax and silently
  skipped these candidates. Interpreters below 3.6 now produce one warning; an absolute-path spec raises
  ``RuntimeError`` with that message. (:pr:`117`, :issue:`116`) - by :user:`gaborbernat`.

.. _release-1-5-2-documentation:

Documentation
-------------

- Document that the library runs on Python 3.8+ and discovers interpreters down to 3.6. (:pr:`117`, :issue:`116`) - by
  :user:`gaborbernat`.

.. _release-1-5-1:

*********************
 v1.5.1 (2026-07-31)
*********************

.. _release-1-5-1-fixed:

Fixed
-----

- Locate uv's interpreter store the way uv does, using XDG on macOS (``~/.local/share/uv/python``) and roaming
  ``%APPDATA%\uv\python`` on Windows, neither of which ``platformdirs`` reported. The uv variables now come from the
  ``env`` mapping rather than ``os.environ`` - by :user:`gaborbernat`. (:pr:`111`, :issue:`109`)
- Pick uv-managed interpreters by install directory name instead of globbing the store. A bare ``3.8`` now means
  CPython, the way uv resolves it, rather than whichever implementation the filesystem happened to list first, and
  probing runs newest version first - by :user:`gaborbernat`. (:pr:`112`, :issue:`110`)

.. _release-1-5-1-packaging:

Packaging
---------

- Drop the ``platformdirs`` runtime dependency; locating uv's store was the only thing it did - by :user:`gaborbernat`.
  (:pr:`111`, :issue:`109`)

.. _release-1-5-0:

*********************
 v1.5.0 (2026-07-21)
*********************

.. _release-1-5-0-added:

Added
-----

- Add Python 3.15 support. (:pr:`104`) - by :user:`gaborbernat`.

.. _release-1-4-4:

*********************
 v1.4.4 (2026-07-08)
*********************

.. _release-1-4-4-fixed:

Fixed
-----

- Parse the debug build flag in interpreter specs - ``python3.13d`` and Debian's ``python3.13-dbg`` /
  ``python3.13-debug`` now select a ``Py_DEBUG`` interpreter instead of being misread as an ISA named ``dbg``. Resolving
  a virtualenv to its base interpreter also checks the free-threaded and debug ABI flags, so a debug or free-threaded
  environment no longer resolves to a release build of the same version - by :user:`ychampion` and :user:`gaborbernat`.
  (:pr:`96`)

.. _release-1-4-3:

*********************
 v1.4.3 (2026-07-03)
*********************

.. _release-1-4-3-packaging:

Packaging
---------

- Constrain the ``hatchling`` build requirement per Python version so sdist builds resolve a compatible backend on the
  declared ``>=3.8`` floor - ``hatchling>=1.28`` dropped Python 3.9, leaving 3.8/3.9 unbuildable from source - by
  :user:`gaborbernat`. (:pr:`94`, :issue:`92`)

.. _release-1-4-2:

*********************
 v1.4.2 (2026-06-11)
*********************

.. _release-1-4-2-fixed:

Fixed
-----

- Stop executable symlink resolution once the stdlib landmark is reachable and keep macOS framework builds untouched,
  matching ``getpath`` - Homebrew interpreters no longer get version-pinned ``Cellar`` paths recorded and stable aliases
  such as Debian's ``/usr/bin/python3`` are preserved - by :user:`gaborbernat`. (:pr:`87`, :issue:`86`)

.. _release-1-4-1:

*********************
 v1.4.1 (2026-06-11)
*********************

.. _release-1-4-1-fixed:

Fixed
-----

- Resolve executable-only symlinks when computing ``system_executable``, mirroring CPython's ``getpath.realpath``
  (python/cpython#115237): a symlink to the interpreter binary now resolves to the real interpreter, while a fully
  symlinked interpreter tree is kept as-is - by :user:`gaborbernat`. (:pr:`85`, :issue:`84`)

.. _release-1-4-0:

*********************
 v1.4.0 (2026-05-28)
*********************

.. _release-1-4-0-added:

Added
-----

- Add ``debug_build`` attribute to :class:`PythonInfo` exposing whether the interpreter is a debug build (``Py_DEBUG``)
  - by :user:`gaborbernat`. (:pr:`79`)

.. _release-1-3-2:

*********************
 v1.3.2 (2026-05-27)
*********************

.. _release-1-3-2-fixed:

Fixed
-----

- Accept dots in machine and ISA specifiers (:pr:`78`) - by :user:`gaborbernat`.

.. _release-1-3-1:

*********************
 v1.3.1 (2026-05-12)
*********************

.. _release-1-3-1-fixed:

Fixed
-----

- Canonicalize GraalVM as GraalPy in interpreter specs and results - by :user:`timfel`. (:pr:`73`)

.. _release-1-3-0:

*********************
 v1.3.0 (2026-05-05)
*********************

.. _release-1-3-0-added:

Added
-----

- Add :func:`~python_discovery.iter_interpreters` for enumerating every discovered interpreter, with PATH and UV-install
  support for non-CPython implementations listed in :data:`~python_discovery.KNOWN_IMPLEMENTATIONS` (:pull:`71`) - by
  :user:`gaborbernat`.

.. _release-1-2-2:

*********************
 v1.2.2 (2026-04-06)
*********************

.. _release-1-2-2-added:

Added
-----

- Export ``normalize_isa`` (:pull:`62`) - by :user:`rahuldevikar`.

.. _release-1-2-2-deprecated:

Deprecated
----------

- Deprecate ``KNOWN_ARCHITECTURES`` (:pull:`62`) - by :user:`rahuldevikar`.

.. _release-1-2-1:

*********************
 v1.2.1 (2026-03-26)
*********************

.. _release-1-2-1-added:

Added
-----

- Expose ``KNOWN_ARCHITECTURES`` as public API (:pull:`56`) - by :user:`rahuldevikar`.

.. _release-1-2-0:

*********************
 v1.2.0 (2026-03-18)
*********************

.. _release-1-2-0-added:

Added
-----

- Increase interpreter query timeout to 15s, with an override (:pull:`53`) - by :user:`gaborbernat`.

.. _release-1-1-3:

*********************
 v1.1.3 (2026-03-10)
*********************

.. _release-1-1-2:

*********************
 v1.1.2 (2026-03-09)
*********************

.. _release-1-1-2-fixed:

Fixed
-----

- Match prerelease versions against ``major.minor`` specs (:pull:`48`) - by :user:`gaborbernat`.
- Drain pipes after killing a timed-out interpreter probe (:pull:`49`) - by :user:`gaborbernat`.

.. _release-1-1-2-documentation:

Documentation
-------------

- Add package description and usage to the README (:pull:`46`) - by :user:`gaborbernat`.

.. _release-1-1-1:

*********************
 v1.1.1 (2026-03-06)
*********************

.. _release-1-1-1-fixed:

Fixed
-----

- Add a timeout to interpreter probing (:pull:`42`) - by :user:`gaborbernat`.

.. _release-1-1-0:

*********************
 v1.1.0 (2026-02-26)
*********************

.. _release-1-1-0-added:

Added
-----

- Add a ``predicate`` parameter to :func:`~python_discovery.get_interpreter` (:pull:`31`) - by :user:`gaborbernat`.

.. _release-1-1-0-documentation:

Documentation
-------------

- Add ``:param:`` descriptions to all public APIs (:pull:`32`) - by :user:`gaborbernat`.

.. _release-1-0-0:

*********************
 v1.0.0 (2026-02-25)
*********************

.. _release-1-0-0-added:

Added
-----

- Initial release as a standalone package, extracted from ``virtualenv`` (:pull:`28`) - by :user:`gaborbernat`.
