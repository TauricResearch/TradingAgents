import pkgutil
import sys
import fontTools
import importlib
import os
from pathlib import Path


def main():
    """Show this help"""
    path = fontTools.__path__
    descriptions = {}
    for pkg in sorted(
        mod.name
        for mod in pkgutil.walk_packages([fontTools.__path__[0]], prefix="fontTools.")
    ):
        try:
            imports = __import__(pkg, globals(), locals(), ["main"])
        except ImportError as e:
            continue
        try:
            description = imports.main.__doc__
            # Cython modules seem to return "main()" as the docstring
            if description and description != "main()":
                pkg = pkg.replace("fontTools.", "").replace(".__main__", "")
                # show the docstring's first line only
                descriptions[pkg] = description.splitlines()[0]
        except AttributeError as e:
            pass
    for pkg, description in descriptions.items():
        print("fonttools %-25s %s" % (pkg, description), file=sys.stderr)


if __name__ == "__main__":
    print("fonttools v%s\n" % fontTools.__version__, file=sys.stderr)
    main()
