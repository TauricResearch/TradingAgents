"""Methods for traversing trees of otData-driven OpenType tables."""

from collections import deque
from typing import Callable, Deque, Iterable, List, Optional, Tuple
from .otBase import BaseTable


__all__ = [
    "bfs_base_table",
    "dfs_base_table",
    "SubTablePath",
]


class SubTablePath(Tuple[BaseTable.SubTableEntry, ...]):
    def __str__(self) -> str:
        path_parts = []
        for entry in self:
            path_part = entry.name
            if entry.index is not None:
                path_part += f"[{entry.index}]"
            path_parts.append(path_part)
        return ".".join(path_parts)


# Given f(current frontier, new entries) add new entries to frontier
AddToFrontierFn = Callable[[Deque[SubTablePath], List[SubTablePath]], None]


def dfs_base_table(
    root: BaseTable,
    root_accessor: Optional[str] = None,
    skip_root: bool = False,
    predicate: Optional[Callable[[SubTablePath], bool]] = None,
    iter_subtables_fn: Optional[
        Callable[[BaseTable], Iterable[BaseTable.SubTableEntry]]
    ] = None,
) -> Iterable[SubTablePath]:
    """Depth-first search tree of BaseTables.

    Args:
        root (BaseTable): the root of the tree.
        root_accessor (Optional[str]): attribute name for the root table, if any (mostly
            useful for debugging).
        skip_root (Optional[bool]): if True, the root itself is not visited, only its
            children.
        predicate (Optional[Callable[[SubTablePath], bool]]): function to filter out
            paths. If True, the path is yielded and its subtables are added to the
            queue. If False, the path is skipped and its subtables are not traversed.
        iter_subtables_fn (Optional[Callable[[BaseTable], Iterable[BaseTable.SubTableEntry]]]):
            function to iterate over subtables of a table. If None, the default
            BaseTable.iterSubTables() is used.

    Yields:
        SubTablePath: tuples of BaseTable.SubTableEntry(name, table, index) namedtuples
        for each of the nodes in the tree. The last entry in a path is the current
        subtable, whereas preceding ones refer to its parent tables all the way up to
        the root.
    """
    yield from _traverse_ot_data(
        root,
        root_accessor,
        skip_root,
        predicate,
        lambda frontier, new: frontier.extendleft(reversed(new)),
        iter_subtables_fn,
    )


def bfs_base_table(
    root: BaseTable,
    root_accessor: Optional[str] = None,
    skip_root: bool = False,
    predicate: Optional[Callable[[SubTablePath], bool]] = None,
    iter_subtables_fn: Optional[
        Callable[[BaseTable], Iterable[BaseTable.SubTableEntry]]
    ] = None,
) -> Iterable[SubTablePath]:
    """Breadth-first search tree of BaseTables.

    Args:
        root
            the root of the tree.
        root_accessor (Optional[str]): attribute name for the root table, if any (mostly
            useful for debugging).
        skip_root (Optional[bool]): if True, the root itself is not visited, only its
            children.
        predicate (Optional[Callable[[SubTablePath], bool]]): function to filter out
            paths. If True, the path is yielded and its subtables are added to the
            queue. If False, the path is skipped and its subtables are not traversed.
        iter_subtables_fn (Optional[Callable[[BaseTable], Iterable[BaseTable.SubTableEntry]]]):
            function to iterate over subtables of a table. If None, the default
            BaseTable.iterSubTables() is used.

    Yields:
        SubTablePath: tuples of BaseTable.SubTableEntry(name, table, index) namedtuples
        for each of the nodes in the tree. The last entry in a path is the current
        subtable, whereas preceding ones refer to its parent tables all the way up to
        the root.
    """
    yield from _traverse_ot_data(
        root,
        root_accessor,
        skip_root,
        predicate,
        lambda frontier, new: frontier.extend(new),
        iter_subtables_fn,
    )


def _traverse_ot_data(
    root: BaseTable,
    root_accessor: Optional[str],
    skip_root: bool,
    predicate: Optional[Callable[[SubTablePath], bool]],
    add_to_frontier_fn: AddToFrontierFn,
    iter_subtables_fn: Optional[
        Callable[[BaseTable], Iterable[BaseTable.SubTableEntry]]
    ] = None,
) -> Iterable[SubTablePath]:
    # no visited because general otData cannot cycle (forward-offset only)
    if root_accessor is None:
        root_accessor = type(root).__name__

    if predicate is None:

        def predicate(path):
            return True

    if iter_subtables_fn is None:

        def iter_subtables_fn(table):
            return table.iterSubTables()

    frontier: Deque[SubTablePath] = deque()

    root_entry = BaseTable.SubTableEntry(root_accessor, root)
    if not skip_root:
        frontier.append((root_entry,))
    else:
        add_to_frontier_fn(
            frontier,
            [
                (root_entry, subtable_entry)
                for subtable_entry in iter_subtables_fn(root)
            ],
        )

    while frontier:
        # path is (value, attr_name) tuples. attr_name is attr of parent to get value
        path = frontier.popleft()
        current = path[-1].value

        if not predicate(path):
            continue

        yield SubTablePath(path)

        new_entries = [
            path + (subtable_entry,) for subtable_entry in iter_subtables_fn(current)
        ]

        add_to_frontier_fn(frontier, new_entries)
