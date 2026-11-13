:func:`~python_discovery.get_interpreter` no longer raises while resolving a ``pyenv`` shim when the working
directory was removed, or on illumos sits below an unreadable directory; it reads ``$PWD`` instead, as ``pyenv`` does.
