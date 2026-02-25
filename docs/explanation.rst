How it works
============

Where does python-discovery look?
-------------------------------

When you call :func:`~python_discovery.get_interpreter`, the library checks several locations in
order. It stops as soon as it finds an interpreter that matches your spec.

.. mermaid::

    flowchart TD
        Start["get_interpreter()"] --> AbsPath{"Is spec an<br>absolute path?"}
        AbsPath -->|Yes| TryAbs["Use path directly"]
        AbsPath -->|No| TryFirst["try_first_with paths"]
        TryFirst --> RelPath{"Is spec a<br>relative path?"}
        RelPath -->|Yes| TryRel["Resolve relative to cwd"]
        RelPath -->|No| Current["Current interpreter"]
        Current --> Win{"Windows?"}
        Win -->|Yes| PEP514["PEP 514 registry"]
        Win -->|No| PATH
        PEP514 --> PATH["PATH search"]
        PATH --> Shims["Version-manager shims<br>(pyenv / mise / asdf)"]
        Shims --> UV["uv-managed Pythons"]

        TryAbs --> Verify
        TryRel --> Verify
        UV --> Verify

        Verify{{"Verify candidate<br>(subprocess call)"}}
        Verify -->|Matches spec| Cache["Cache and return"]
        Verify -->|No match| Next["Try next candidate"]

        style Start fill:#4a90d9,stroke:#2a5f8f,color:#fff
        style Verify fill:#d9904a,stroke:#8f5f2a,color:#fff
        style Cache fill:#4a9f4a,stroke:#2a6f2a,color:#fff
        style Next fill:#d94a4a,stroke:#8f2a2a,color:#fff

Each candidate is verified by running it as a subprocess and collecting its metadata (version,
architecture, platform, sysconfig values, etc.). This subprocess call is the expensive part, which
is why results are cached.

How version-manager shims are handled
-----------------------------------------

Version managers like `pyenv <https://github.com/pyenv/pyenv>`_ install thin wrapper scripts called
**shims** (e.g., ``~/.pyenv/shims/python3.12``) that redirect to the real interpreter. python-discovery
detects these shims and resolves them to the actual binary.

.. mermaid::

    flowchart TD
        Shim["Shim detected"] --> EnvVar{"PYENV_VERSION<br>set?"}
        EnvVar -->|Yes| Use["Use that version"]
        EnvVar -->|No| File{".python-version<br>file exists?"}
        File -->|Yes| Use
        File -->|No| Global{"pyenv global<br>version exists?"}
        Global -->|Yes| Use
        Global -->|No| Skip["Skip shim"]

        style Shim fill:#4a90d9,stroke:#2a5f8f,color:#fff
        style Use fill:#4a9f4a,stroke:#2a6f2a,color:#fff
        style Skip fill:#d94a4a,stroke:#8f2a2a,color:#fff

`mise <https://mise.jdx.dev/>`_ and `asdf <https://asdf-vm.com/>`_ work similarly, using the
``MISE_DATA_DIR`` and ``ASDF_DATA_DIR`` environment variables to locate their installations.

How caching works
-------------------

Querying an interpreter requires a subprocess call, which is slow. The cache avoids repeating this
work by storing the result as a JSON file keyed by the interpreter's path.

.. mermaid::

    flowchart TD
        Lookup["py_info(path)"] --> Exists{"Cache hit?"}
        Exists -->|Yes| Read["Read JSON"]
        Exists -->|No| Run["Run subprocess"]
        Run --> Write["Write JSON<br>(with filelock)"]
        Write --> Return["Return PythonInfo"]
        Read --> Return

        style Lookup fill:#4a90d9,stroke:#2a5f8f,color:#fff
        style Return fill:#4a9f4a,stroke:#2a6f2a,color:#fff
        style Run fill:#d9904a,stroke:#8f5f2a,color:#fff

The built-in :class:`~python_discovery.DiskCache` stores files under ``<root>/py_info/4/<sha256>.json``
with `filelock <https://py-filelock.readthedocs.io/>`_-based locking for safe concurrent access. You
can also pass ``cache=None`` to disable caching, or implement your own backend (see
:doc:`/how-to/standalone-usage`).

Spec format reference
-----------------------

A spec string follows the pattern ``[impl][version][t][-arch][-machine]``. Every part is optional.

.. mermaid::

    flowchart TD
        Spec["Spec string"] --> Impl["impl<br>(optional)"]
        Impl --> Version["version<br>(optional)"]
        Version --> T["t<br>(optional)"]
        T --> Arch["-arch<br>(optional)"]
        Arch --> Machine["-machine<br>(optional)"]

        style Impl fill:#4a90d9,stroke:#2a5f8f,color:#fff
        style Version fill:#4a9f4a,stroke:#2a6f2a,color:#fff
        style T fill:#d9904a,stroke:#8f5f2a,color:#fff
        style Arch fill:#d94a4a,stroke:#8f2a2a,color:#fff
        style Machine fill:#904ad9,stroke:#5f2a8f,color:#fff

**Parts explained:**

- **impl** -- the Python implementation name. ``python`` and ``py`` both mean "any implementation"
  (usually CPython). Use ``cpython``, ``pypy``, or ``graalpy`` to be explicit.
- **version** -- dotted version number (``3``, ``3.12``, or ``3.12.1``). You can also write
  ``312`` as shorthand for ``3.12``.
- **t** -- appended directly after the version. Matches free-threaded (no-GIL) builds only.
- **-arch** -- ``-32`` or ``-64`` for 32-bit or 64-bit interpreters.
- **-machine** -- the CPU instruction set: ``-arm64``, ``-x86_64``, ``-aarch64``, ``-riscv64``, etc.

**Full examples:**

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Spec
     - Meaning
   * - ``3.12``
     - Any Python 3.12
   * - ``python3.12``
     - CPython 3.12
   * - ``cpython3.12``
     - Explicitly CPython 3.12
   * - ``pypy3.9``
     - PyPy 3.9
   * - ``python3.13t``
     - Free-threaded (no-GIL) CPython 3.13
   * - ``python3.12-64``
     - 64-bit CPython 3.12
   * - ``python3.12-64-arm64``
     - 64-bit CPython 3.12 on ARM64
   * - ``/usr/bin/python3``
     - Absolute path, used directly (no search)
   * - ``>=3.11,<3.13``
     - :pep:`440` version specifier (any Python in range)
   * - ``cpython>=3.11``
     - :pep:`440` specifier restricted to CPython

:pep:`440` specifiers (``>=``, ``<=``, ``~=``, ``!=``, ``==``, ``===``) are supported. Multiple
specifiers can be comma-separated, for example ``>=3.11,<3.13``.
