``PythonSpec.satisfies`` now checks a version specifier at the precision it was written with, so ``3.11`` no longer
satisfies ``>=3.13``. The Windows registry pre-filter skips mismatched releases and interrogates candidates whose
prerelease status is unknown.
