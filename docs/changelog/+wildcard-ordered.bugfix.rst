:class:`~python_discovery.PythonSpec` now raises :exc:`ValueError` for wildcards on operators other than ``==`` or
``!=``, such as ``>=3.12.*``, and after pre-release suffixes, such as ``==3.13rc1.*``.
