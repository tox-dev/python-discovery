Stop ``PythonInfo.system_include`` reporting the interpreter's prefix as the include directory when the C headers are
not installed, which happened on Python 3.11 and later and on Debian's 3.10; the missing sysconfig include path is
returned instead.
