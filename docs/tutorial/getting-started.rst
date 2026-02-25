Getting started
===============

Installation
------------

.. code-block:: console

   pip install python-discovery

Core concepts
-------------

Before diving into code, here are the key ideas:

- **Interpreter** -- a Python executable on your system (e.g., ``/usr/bin/python3.12``).
- **Spec** -- a short string describing what you are looking for (e.g., ``python3.12``, ``pypy3.9``, ``>=3.11``).
- **Discovery** -- the process of searching your system for an interpreter that matches a spec.
- **Cache** -- a disk store that remembers previously discovered interpreters so the next lookup is instant.

Inspecting the current interpreter
------------------------------------

The simplest use case: get information about the Python that is running right now.

.. mermaid::

    flowchart TD
        Call["PythonInfo.current_system(cache)"] --> Info["PythonInfo"]
        Info --> Exe["executable: /usr/bin/python3.12"]
        Info --> Ver["version_info: (3, 12, 1)"]
        Info --> Impl["implementation: CPython"]
        Info --> Arch["architecture: 64"]

        style Call fill:#4a90d9,stroke:#2a5f8f,color:#fff
        style Info fill:#4a9f4a,stroke:#2a6f2a,color:#fff

.. code-block:: python

   from pathlib import Path

   from python_discovery import DiskCache, PythonInfo

   cache = DiskCache(root=Path("~/.cache/python-discovery").expanduser())
   info = PythonInfo.current_system(cache)

   print(info.executable)        # /usr/bin/python3.12
   print(info.version_info[:3])  # (3, 12, 1)
   print(info.implementation)    # CPython  (or PyPy, GraalPy, etc.)
   print(info.architecture)      # 64       (or 32)

The returned :class:`~python_discovery.PythonInfo` object contains everything the library knows about that interpreter:
paths, version numbers, sysconfig variables, platform details, and more.

Finding a different interpreter
--------------------------------

Usually you need a *specific* Python version, not the one currently running. Pass a **spec** string
to :func:`~python_discovery.get_interpreter` to search your system.

.. mermaid::

    flowchart TD
        Spec["Spec: python3.12"] --> Call["get_interpreter(spec, cache)"]
        Call --> Found{"Match found?"}
        Found -->|Yes| Info["PythonInfo with full metadata"]
        Found -->|No| Nil["None"]

        style Spec fill:#4a90d9,stroke:#2a5f8f,color:#fff
        style Info fill:#4a9f4a,stroke:#2a6f2a,color:#fff
        style Nil fill:#d94a4a,stroke:#8f2a2a,color:#fff

.. code-block:: python

   from pathlib import Path

   from python_discovery import DiskCache, get_interpreter

   cache = DiskCache(root=Path("~/.cache/python-discovery").expanduser())
   result = get_interpreter("python3.12", cache=cache)
   if result is not None:
       print(result.executable)

You can pass multiple specs as a list -- the library tries each one in order and returns the first match.

.. code-block:: python

   result = get_interpreter(["python3.12", "python3.11"], cache=cache)

Writing specs
-------------

A spec tells python-discovery what to look for. The simplest form is just a version number like ``3.12``.
You can add more constraints to narrow the search.

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

Common examples:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Spec
     - What it matches
   * - ``3.12``
     - Any Python 3.12 (CPython, PyPy, etc.)
   * - ``python3.12``
     - CPython 3.12 (``python`` means CPython)
   * - ``pypy3.9``
     - PyPy 3.9
   * - ``python3.13t``
     - Free-threaded (no-GIL) CPython 3.13
   * - ``python3.12-64``
     - 64-bit CPython 3.12
   * - ``python3.12-64-arm64``
     - 64-bit CPython 3.12 on ARM64 hardware
   * - ``/usr/bin/python3``
     - An absolute path, used directly without searching
   * - ``>=3.11,<3.13``
     - Any Python in the 3.11--3.12 range (:pep:`440` syntax)

See the :doc:`full spec reference </explanation>` for all options.

Parsing a spec
--------------

You can parse a spec string into its components without searching the system. This is useful for
inspecting what a spec means or for building tools on top of python-discovery.

.. mermaid::

    flowchart TD
        Input["cpython3.12t-64-arm64"] --> Parse["PythonSpec.from_string_spec()"]
        Parse --> Spec["PythonSpec"]
        Spec --> impl["implementation: cpython"]
        Spec --> ver["major: 3, minor: 12"]
        Spec --> ft["free_threaded: True"]
        Spec --> arch["architecture: 64"]
        Spec --> mach["machine: arm64"]

        style Input fill:#4a90d9,stroke:#2a5f8f,color:#fff
        style Spec fill:#4a9f4a,stroke:#2a6f2a,color:#fff

.. code-block:: python

   from python_discovery import PythonSpec

   spec = PythonSpec.from_string_spec("cpython3.12t-64-arm64")
   spec.implementation   # "cpython"
   spec.major            # 3
   spec.minor            # 12
   spec.free_threaded    # True
   spec.architecture     # 64
   spec.machine          # "arm64"

Skipping the cache
------------------

If you only need to discover once and do not want to write anything to disk, pass ``cache=None``.
Every call will run a subprocess to query the interpreter, so this is slower for repeated lookups.

.. code-block:: python

   from python_discovery import get_interpreter

   result = get_interpreter("python3.12")
