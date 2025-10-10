# Copyright 2013 Google, Inc. All Rights Reserved.
#
# Google Author(s): Behdad Esfahbod, Roozbeh Pournader

from fontTools.ttLib.tables.DefaultTable import DefaultTable
import logging


log = logging.getLogger("fontTools.merge")


def add_method(*clazzes, **kwargs):
    """Returns a decorator function that adds a new method to one or
    more classes."""
    allowDefault = kwargs.get("allowDefaultTable", False)

    def wrapper(method):
        done = []
        for clazz in clazzes:
            if clazz in done:
                continue  # Support multiple names of a clazz
            done.append(clazz)
            assert allowDefault or clazz != DefaultTable, "Oops, table class not found."
            assert (
                method.__name__ not in clazz.__dict__
            ), "Oops, class '%s' has method '%s'." % (clazz.__name__, method.__name__)
            setattr(clazz, method.__name__, method)
        return None

    return wrapper


def mergeObjects(lst):
    lst = [item for item in lst if item is not NotImplemented]
    if not lst:
        return NotImplemented
    lst = [item for item in lst if item is not None]
    if not lst:
        return None

    clazz = lst[0].__class__
    assert all(type(item) == clazz for item in lst), lst

    logic = clazz.mergeMap
    returnTable = clazz()
    returnDict = {}

    allKeys = set.union(set(), *(vars(table).keys() for table in lst))
    for key in allKeys:
        try:
            mergeLogic = logic[key]
        except KeyError:
            try:
                mergeLogic = logic["*"]
            except KeyError:
                raise Exception(
                    "Don't know how to merge key %s of class %s" % (key, clazz.__name__)
                )
        if mergeLogic is NotImplemented:
            continue
        value = mergeLogic(getattr(table, key, NotImplemented) for table in lst)
        if value is not NotImplemented:
            returnDict[key] = value

    returnTable.__dict__ = returnDict

    return returnTable


@add_method(DefaultTable, allowDefaultTable=True)
def merge(self, m, tables):
    if not hasattr(self, "mergeMap"):
        log.info("Don't know how to merge '%s'.", self.tableTag)
        return NotImplemented

    logic = self.mergeMap

    if isinstance(logic, dict):
        return m.mergeObjects(self, self.mergeMap, tables)
    else:
        return logic(tables)
