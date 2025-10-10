"""Private utility methods used by the subset modules"""


def _add_method(*clazzes):
    """Returns a decorator function that adds a new method to one or
    more classes."""

    def wrapper(method):
        done = []
        for clazz in clazzes:
            if clazz in done:
                continue  # Support multiple names of a clazz
            done.append(clazz)
            assert clazz.__name__ != "DefaultTable", "Oops, table class not found."
            assert not hasattr(
                clazz, method.__name__
            ), "Oops, class '%s' has method '%s'." % (clazz.__name__, method.__name__)
            setattr(clazz, method.__name__, method)
        return None

    return wrapper


def _uniq_sort(l):
    return sorted(set(l))
