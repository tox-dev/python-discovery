How-to guides
=============

Search specific directories first
-----------------------------------

If you know a likely location for the interpreter, pass it via ``try_first_with`` to check there
before the normal search. This is useful when you have a custom Python install outside the
standard locations.

.. code-block:: python

   from python_discovery import get_interpreter

   info = get_interpreter("python3.12", try_first_with=["/opt/python/bin"])
   if info is not None:
       print(info.executable)

Restrict the search environment
---------------------------------

By default, python-discovery reads environment variables like ``PATH`` and ``PYENV_ROOT`` from your
shell. You can override these to control exactly where the library looks.

.. mermaid::

    flowchart TD
        Env["Custom env dict"] --> Call["get_interpreter(spec, env=env)"]
        Call --> PATH["PATH"]
        Call --> Pyenv["PYENV_ROOT"]
        Call --> UV["UV_PYTHON_INSTALL_DIR"]
        Call --> Mise["MISE_DATA_DIR"]

        style Env fill:#4a90d9,stroke:#2a5f8f,color:#fff

.. code-block:: python

   import os

   from python_discovery import get_interpreter

   env = {**os.environ, "PATH": "/usr/local/bin:/usr/bin"}
   result = get_interpreter("python3.12", env=env)

Read interpreter metadata
---------------------------

Once you have a :class:`~python_discovery.PythonInfo`, you can inspect everything about the interpreter.

.. mermaid::

    classDiagram
        class PythonInfo {
            +executable: str
            +system_executable: str
            +implementation: str
            +version_info: VersionInfo
            +architecture: int
            +platform: str
            +sysconfig_vars: dict
            +sysconfig_paths: dict
            +machine: str
            +free_threaded: bool
        }

.. code-block:: python

   from pathlib import Path

   from python_discovery import DiskCache, get_interpreter

   cache = DiskCache(root=Path("~/.cache/python-discovery").expanduser())
   info = get_interpreter("python3.12", cache=cache)

   info.executable           # Resolved path to the binary.
   info.system_executable    # The underlying system interpreter (outside any venv).
   info.implementation       # "CPython", "PyPy", "GraalPy", etc.
   info.version_info         # VersionInfo(major, minor, micro, releaselevel, serial).
   info.architecture         # 64 or 32.
   info.platform             # sys.platform value ("linux", "darwin", "win32").
   info.machine              # ISA: "arm64", "x86_64", etc.
   info.free_threaded        # True if this is a no-GIL build.
   info.sysconfig_vars       # All sysconfig.get_config_vars() values.
   info.sysconfig_paths      # All sysconfig.get_paths() values.

Implement a custom cache backend
-----------------------------------

The built-in :class:`~python_discovery.DiskCache` stores results as JSON files with
`filelock <https://py-filelock.readthedocs.io/>`_-based locking. If you need a different storage
strategy (e.g., in-memory, database-backed), implement the :class:`~python_discovery.PyInfoCache`
protocol.

.. mermaid::

    classDiagram
        class PyInfoCache {
            <<Protocol>>
            +py_info(path) ContentStore
            +py_info_clear() None
        }
        class ContentStore {
            <<Protocol>>
            +exists() bool
            +read() dict | None
            +write(content) None
            +remove() None
            +locked() context
        }
        class DiskCache {
            +root: Path
        }
        PyInfoCache <|.. DiskCache
        PyInfoCache --> ContentStore

.. code-block:: python

   from pathlib import Path

   from python_discovery import ContentStore, PyInfoCache


   class MyContentStore:
       def __init__(self, path: Path) -> None:
           self._path = path

       def exists(self) -> bool: ...

       def read(self) -> dict | None: ...

       def write(self, content: dict) -> None: ...

       def remove(self) -> None: ...

       def locked(self): ...


   class MyCache:
       def py_info(self, path: Path) -> MyContentStore: ...

       def py_info_clear(self) -> None: ...

Any object that matches the protocol works -- no inheritance required.
