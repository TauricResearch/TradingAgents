# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Level-1 disk cache decorator for DataFrame-returning data-vendor functions.

Cache file layout:
    {data_cache_dir}/{kind}/{func_name}/{key16}.parquet

Key is sha256(func_name, args, kwargs)[:16]. TTL is read from
config["cache_ttl"][kind] (seconds; 0 disables caching for that kind).

Behavior:
- cache hit (fresh): read parquet and return
- cache miss / stale / corrupt: call function, store result on success
- empty DataFrame is NOT cached (so transient failures retry next call)
- fail-open: any cache exception logs and falls through to the wrapped function
"""

import functools
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from threading import Lock
from typing import Callable

import pandas as pd

logger = logging.getLogger(__name__)

_path_locks: dict[str, Lock] = {}
_path_locks_master = Lock()


def _get_path_lock(path: str) -> Lock:
    """Per-path in-process lock so concurrent calls don't collide on disk."""
    with _path_locks_master:
        lock = _path_locks.get(path)
        if lock is None:
            lock = Lock()
            _path_locks[path] = lock
        return lock


def _make_key(func_name: str, args: tuple, kwargs: dict) -> str:
    payload = json.dumps(
        {"fn": func_name, "args": list(args), "kwargs": kwargs},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _is_fresh(path: Path, ttl_seconds: int) -> bool:
    if ttl_seconds <= 0:
        return False
    age = time.time() - path.stat().st_mtime
    return age < ttl_seconds


def simple_parquet_cache(kind: str) -> Callable:
    """Disk cache decorator. See module docstring for details."""

    def decorator(func: Callable[..., pd.DataFrame]) -> Callable[..., pd.DataFrame]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> pd.DataFrame:
            from .config import get_config

            path: Path | None = None
            lock: Lock | None = None

            # Phase 1: try to serve from cache (fail-open on any cache infra error)
            try:
                config = get_config()
                ttl = int(config.get("cache_ttl", {}).get(kind, 0))
                if ttl <= 0:
                    return func(*args, **kwargs)

                base = Path(config["data_cache_dir"]) / kind / func.__name__
                base.mkdir(parents=True, exist_ok=True)
                key = _make_key(func.__name__, args, kwargs)
                path = base / f"{key}.parquet"
                lock = _get_path_lock(str(path))

                with lock:
                    if path.exists() and _is_fresh(path, ttl):
                        try:
                            return pd.read_parquet(path)
                        except Exception as e:
                            logger.warning("cache read failed for %s: %s", path, e)
            except Exception as e:
                logger.warning("simple_parquet_cache read bypass: %s", e)
                path = None  # disable write-back if read path itself failed

            # Phase 2: call the wrapped function — exceptions propagate naturally
            result = func(*args, **kwargs)

            # Phase 3: try to persist non-empty DataFrame results (fail-open)
            if (
                path is not None
                and lock is not None
                and isinstance(result, pd.DataFrame)
                and not result.empty
            ):
                tmp = path.with_suffix(".parquet.tmp")
                try:
                    with lock:
                        result.to_parquet(tmp, compression="snappy")
                        os.replace(tmp, path)
                except Exception as e:
                    logger.warning("cache write failed for %s: %s", path, e)
                    try:
                        tmp.unlink(missing_ok=True)
                    except Exception:
                        pass
            return result

        return wrapper

    return decorator
