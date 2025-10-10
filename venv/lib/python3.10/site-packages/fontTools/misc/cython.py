""" Exports a no-op 'cython' namespace similar to
https://github.com/cython/cython/blob/master/Cython/Shadow.py

This allows to optionally compile @cython decorated functions
(when cython is available at built time), or run the same code
as pure-python, without runtime dependency on cython module.

We only define the symbols that we use. E.g. see fontTools.cu2qu
"""

from types import SimpleNamespace


def _empty_decorator(x):
    return x


compiled = False

for name in ("double", "complex", "int"):
    globals()[name] = None

for name in ("cfunc", "inline"):
    globals()[name] = _empty_decorator

locals = lambda **_: _empty_decorator
returns = lambda _: _empty_decorator
