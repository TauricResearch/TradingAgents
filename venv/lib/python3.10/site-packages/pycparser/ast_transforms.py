#------------------------------------------------------------------------------
# pycparser: ast_transforms.py
#
# Some utilities used by the parser to create a friendlier AST.
#
# Eli Bendersky [https://eli.thegreenplace.net/]
# License: BSD
#------------------------------------------------------------------------------

from . import c_ast


def fix_switch_cases(switch_node):
    """ The 'case' statements in a 'switch' come out of parsing with one
        child node, so subsequent statements are just tucked to the parent
        Compound. Additionally, consecutive (fall-through) case statements
        come out messy. This is a peculiarity of the C grammar. The following:

            switch (myvar) {
                case 10:
                    k = 10;
                    p = k + 1;
                    return 10;
                case 20:
                case 30:
                    return 20;
                default:
                    break;
            }

        Creates this tree (pseudo-dump):

            Switch
                ID: myvar
                Compound:
                    Case 10:
                        k = 10
                    p = k + 1
                    return 10
                    Case 20:
                        Case 30:
                            return 20
                    Default:
                        break

        The goal of this transform is to fix this mess, turning it into the
        following:

            Switch
                ID: myvar
                Compound:
                    Case 10:
                        k = 10
                        p = k + 1
                        return 10
                    Case 20:
                    Case 30:
                        return 20
                    Default:
                        break

        A fixed AST node is returned. The argument may be modified.
    """
    assert isinstance(switch_node, c_ast.Switch)
    if not isinstance(switch_node.stmt, c_ast.Compound):
        return switch_node

    # The new Compound child for the Switch, which will collect children in the
    # correct order
    new_compound = c_ast.Compound([], switch_node.stmt.coord)

    # The last Case/Default node
    last_case = None

    # Goes over the children of the Compound below the Switch, adding them
    # either directly below new_compound or below the last Case as appropriate
    # (for `switch(cond) {}`, block_items would have been None)
    for child in (switch_node.stmt.block_items or []):
        if isinstance(child, (c_ast.Case, c_ast.Default)):
            # If it's a Case/Default:
            # 1. Add it to the Compound and mark as "last case"
            # 2. If its immediate child is also a Case or Default, promote it
            #    to a sibling.
            new_compound.block_items.append(child)
            _extract_nested_case(child, new_compound.block_items)
            last_case = new_compound.block_items[-1]
        else:
            # Other statements are added as children to the last case, if it
            # exists.
            if last_case is None:
                new_compound.block_items.append(child)
            else:
                last_case.stmts.append(child)

    switch_node.stmt = new_compound
    return switch_node


def _extract_nested_case(case_node, stmts_list):
    """ Recursively extract consecutive Case statements that are made nested
        by the parser and add them to the stmts_list.
    """
    if isinstance(case_node.stmts[0], (c_ast.Case, c_ast.Default)):
        stmts_list.append(case_node.stmts.pop())
        _extract_nested_case(stmts_list[-1], stmts_list)


def fix_atomic_specifiers(decl):
    """ Atomic specifiers like _Atomic(type) are unusually structured,
        conferring a qualifier upon the contained type.

        This function fixes a decl with atomic specifiers to have a sane AST
        structure, by removing spurious Typename->TypeDecl pairs and attaching
        the _Atomic qualifier in the right place.
    """
    # There can be multiple levels of _Atomic in a decl; fix them until a
    # fixed point is reached.
    while True:
        decl, found = _fix_atomic_specifiers_once(decl)
        if not found:
            break

    # Make sure to add an _Atomic qual on the topmost decl if needed. Also
    # restore the declname on the innermost TypeDecl (it gets placed in the
    # wrong place during construction).
    typ = decl
    while not isinstance(typ, c_ast.TypeDecl):
        try:
            typ = typ.type
        except AttributeError:
            return decl
    if '_Atomic' in typ.quals and '_Atomic' not in decl.quals:
        decl.quals.append('_Atomic')
    if typ.declname is None:
        typ.declname = decl.name

    return decl


def _fix_atomic_specifiers_once(decl):
    """ Performs one 'fix' round of atomic specifiers.
        Returns (modified_decl, found) where found is True iff a fix was made.
    """
    parent = decl
    grandparent = None
    node = decl.type
    while node is not None:
        if isinstance(node, c_ast.Typename) and '_Atomic' in node.quals:
            break
        try:
            grandparent = parent
            parent = node
            node = node.type
        except AttributeError:
            # If we've reached a node without a `type` field, it means we won't
            # find what we're looking for at this point; give up the search
            # and return the original decl unmodified.
            return decl, False

    assert isinstance(parent, c_ast.TypeDecl)
    grandparent.type = node.type
    if '_Atomic' not in node.type.quals:
        node.type.quals.append('_Atomic')
    return decl, True
