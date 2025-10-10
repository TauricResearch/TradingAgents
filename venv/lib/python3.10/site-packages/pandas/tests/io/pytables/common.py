from collections.abc import Generator
from contextlib import contextmanager
import pathlib
import tempfile

import pytest

from pandas.io.pytables import HDFStore

tables = pytest.importorskip("tables")
# set these parameters so we don't have file sharing
tables.parameters.MAX_NUMEXPR_THREADS = 1
tables.parameters.MAX_BLOSC_THREADS = 1
tables.parameters.MAX_THREADS = 1


def safe_close(store):
    try:
        if store is not None:
            store.close()
    except OSError:
        pass


# contextmanager to ensure the file cleanup
@contextmanager
def ensure_clean_store(
    path, mode="a", complevel=None, complib=None, fletcher32=False
) -> Generator[HDFStore, None, None]:
    with tempfile.TemporaryDirectory() as tmpdirname:
        tmp_path = pathlib.Path(tmpdirname, path)
        with HDFStore(
            tmp_path,
            mode=mode,
            complevel=complevel,
            complib=complib,
            fletcher32=fletcher32,
        ) as store:
            yield store


def _maybe_remove(store, key):
    """
    For tests using tables, try removing the table to be sure there is
    no content from previous tests using the same table name.
    """
    try:
        store.remove(key)
    except (ValueError, KeyError):
        pass
