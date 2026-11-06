:func:`~python_discovery.iter_interpreters` with no key no longer probes each ``PATH`` directory as if it were an
interpreter. The empty spec made the literal name check point at the directory itself, so every entry cost a failed
subprocess and a retry.
