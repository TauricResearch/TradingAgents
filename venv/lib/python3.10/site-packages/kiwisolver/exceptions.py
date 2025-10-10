# --------------------------------------------------------------------------------------
# Copyright (c) 2023-2024, Nucleic Development Team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file LICENSE, distributed with this software.
# --------------------------------------------------------------------------------------
"""Kiwi exceptions.

Imported by the kiwisolver C extension.

"""


class BadRequiredStrength(Exception):
    pass


class DuplicateConstraint(Exception):
    __slots__ = ("constraint",)

    def __init__(self, constraint):
        self.constraint = constraint


class DuplicateEditVariable(Exception):
    __slots__ = ("edit_variable",)

    def __init__(self, edit_variable):
        self.edit_variable = edit_variable


class UnknownConstraint(Exception):
    __slots__ = ("constraint",)

    def __init__(self, constraint):
        self.constraint = constraint


class UnknownEditVariable(Exception):
    __slots__ = ("edit_variable",)

    def __init__(self, edit_variable):
        self.edit_variable = edit_variable


class UnsatisfiableConstraint(Exception):
    __slots__ = ("constraint",)

    def __init__(self, constraint):
        self.constraint = constraint
