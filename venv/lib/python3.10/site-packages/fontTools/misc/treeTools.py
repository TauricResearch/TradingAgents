"""Generic tools for working with trees."""

from math import ceil, log


def build_n_ary_tree(leaves, n):
    """Build N-ary tree from sequence of leaf nodes.

    Return a list of lists where each non-leaf node is a list containing
    max n nodes.
    """
    if not leaves:
        return []

    assert n > 1

    depth = ceil(log(len(leaves), n))

    if depth <= 1:
        return list(leaves)

    # Fully populate complete subtrees of root until we have enough leaves left
    root = []
    unassigned = None
    full_step = n ** (depth - 1)
    for i in range(0, len(leaves), full_step):
        subtree = leaves[i : i + full_step]
        if len(subtree) < full_step:
            unassigned = subtree
            break
        while len(subtree) > n:
            subtree = [subtree[k : k + n] for k in range(0, len(subtree), n)]
        root.append(subtree)

    if unassigned:
        # Recurse to fill the last subtree, which is the only partially populated one
        subtree = build_n_ary_tree(unassigned, n)
        if len(subtree) <= n - len(root):
            # replace last subtree with its children if they can still fit
            root.extend(subtree)
        else:
            root.append(subtree)
        assert len(root) <= n

    return root
