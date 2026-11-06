``PythonSpec.satisfies`` now checks a version specifier at the precision it was written with, so ``3.11`` no longer
satisfies ``>=3.13``. This also lets the Windows registry pre-filter skip interpreters that can't match.
