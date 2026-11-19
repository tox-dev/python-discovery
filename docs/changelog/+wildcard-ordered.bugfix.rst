:class:`~python_discovery.PythonSpec` now raises :exc:`ValueError` for a ``.*`` wildcard that PEP 440 does not allow,
on an operator other than ``==`` and ``!=`` (``>=3.12.*``) or after a pre-release (``==3.13rc1.*``), instead of
accepting a specifier that matches no interpreter or every 3.13 one.
