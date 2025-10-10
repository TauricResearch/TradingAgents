#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# multitasking: Non-blocking Python methods using decorators
# https://github.com/ranaroussi/multitasking
#
# Copyright 2016-2025 Ran Aroussi
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

__version__ = "0.0.12"

# Core imports for multitasking functionality
import time as _time
from functools import wraps
from sys import exit as sysexit
from os import _exit as osexit
from typing import Any, Callable, Dict, List, Optional, TypedDict, Union

# Threading and multiprocessing imports
from threading import Thread, Semaphore
from multiprocessing import Process, cpu_count


class PoolConfig(TypedDict):
    """Type definition for execution pool configuration.

    This defines the structure of each pool in the POOLS dictionary,
    containing the semaphore for limiting concurrent tasks, the engine
    type (Thread or Process), pool name, and thread count.
    """
    pool: Optional[Semaphore]  # Controls concurrent task execution
    engine: Union[type[Thread], type[Process]]  # Execution engine
    name: str  # Human-readable pool identifier
    threads: int  # Maximum concurrent tasks (0 = unlimited)


class Config(TypedDict):
    """Type definition for global multitasking configuration.

    This structure holds all global state including CPU info, engine
    preferences, task tracking, and pool management. It serves as the
    central configuration store for the entire library.
    """
    CPU_CORES: int  # Number of CPU cores detected
    ENGINE: str  # Default engine type ("thread" or "process")
    MAX_THREADS: int  # Global maximum thread/process count
    KILL_RECEIVED: bool  # Signal to stop accepting new tasks
    TASKS: List[Union[Thread, Process]]  # All created tasks
    POOLS: Dict[str, PoolConfig]  # Named execution pools
    POOL_NAME: str  # Currently active pool name


# Global configuration dictionary - this is the central state store
# for all multitasking operations. It tracks pools, tasks, and settings.
config: Config = {
    "CPU_CORES": cpu_count(),  # Auto-detect available CPU cores
    "ENGINE": "thread",  # Default to threading (safer than processes)
    "MAX_THREADS": cpu_count(),  # Start with one thread per CPU core
    "KILL_RECEIVED": False,  # Not in shutdown mode initially
    "TASKS": [],  # No tasks created yet
    "POOLS": {},  # No pools created yet
    "POOL_NAME": "Main"  # Default pool name
}


def set_max_threads(threads: Optional[int] = None) -> None:
    """Configure the maximum number of concurrent threads/processes.

    This function allows users to override the default CPU-based thread
    count. Setting this affects new pools but not existing ones.

    Args:
        threads: Maximum concurrent tasks. If None, uses CPU count.
                 Must be positive integer or None.

    Example:
        set_max_threads(4)  # Limit to 4 concurrent tasks
        set_max_threads()   # Reset to CPU count
    """
    if threads is not None:
        # User provided explicit thread count
        config["MAX_THREADS"] = threads
    else:
        # Reset to system default (one per CPU core)
        config["MAX_THREADS"] = cpu_count()


def set_engine(kind: str = "") -> None:
    """Configure the execution engine for new pools.

    This determines whether new tasks run in threads or separate
    processes. Threads share memory but processes are more isolated.
    Only affects pools created after this call.

    Args:
        kind: Engine type. Contains "process" for multiprocessing,
              anything else defaults to threading.

    Note:
        Threading: Faster startup, shared memory, GIL limitations
        Processing: Slower startup, isolated memory, true parallelism
    """
    if "process" in kind.lower():
        # Use multiprocessing for CPU-bound tasks
        config["ENGINE"] = "process"
    else:
        # Use threading for I/O-bound tasks (default)
        config["ENGINE"] = "thread"


def getPool(name: Optional[str] = None) -> Dict[str, Union[str, int]]:
    """Retrieve information about an execution pool.

    Returns a dictionary with pool metadata including engine type,
    name, and thread count. Useful for debugging and monitoring.

    Args:
        name: Pool name to query. If None, uses current active pool.

    Returns:
        Dictionary with keys: 'engine', 'name', 'threads'

    Raises:
        KeyError: If the specified pool doesn't exist
    """
    # Default to currently active pool if no name specified
    if name is None:
        name = config["POOL_NAME"]

    # Determine engine type from the pool configuration
    engine = "thread"  # Default assumption
    if config["POOLS"][config["POOL_NAME"]]["engine"] == Process:
        engine = "process"

    # Return pool information as a dictionary
    return {
        "engine": engine,
        "name": name,
        "threads": config["POOLS"][config["POOL_NAME"]]["threads"]
    }


def createPool(
    name: str = "main",
    threads: Optional[int] = None,
    engine: Optional[str] = None
) -> None:
    """Create a new execution pool with specified configuration.

    Pools manage concurrent task execution using semaphores. Each pool
    has its own thread/process limit and engine type. Creating a pool
    automatically makes it the active pool for new tasks.

    Args:
        name: Unique identifier for this pool
        threads: Max concurrent tasks. None uses global MAX_THREADS.
                 Values < 2 create unlimited pools (no semaphore).
        engine: "process" or "thread". None uses global ENGINE setting.

    Note:
        Setting threads=0 or threads=1 creates an unlimited pool where
        all tasks run immediately without queuing.
    """
    # Switch to this pool as the active one
    config["POOL_NAME"] = name

    # Parse and validate thread count
    try:
        threads = (
            int(threads) if threads is not None
            else config["MAX_THREADS"]
        )
    except (ValueError, TypeError):
        # Invalid input, fall back to global setting
        threads = config["MAX_THREADS"]

    # Thread counts less than 2 mean unlimited execution
    if threads < 2:
        threads = 0  # 0 is our internal code for "unlimited"

    # Determine engine type (default to global setting)
    engine = engine if engine is not None else config["ENGINE"]

    # Update global settings to match this pool
    config["MAX_THREADS"] = threads
    config["ENGINE"] = engine

    # Create the pool configuration
    config["POOLS"][config["POOL_NAME"]] = {
        # Semaphore controls concurrent execution (None = unlimited)
        "pool": Semaphore(threads) if threads > 0 else None,
        # Engine class determines Thread vs Process execution
        "engine": Process if "process" in engine.lower() else Thread,
        "name": name,
        "threads": threads
    }


def task(
    callee: Callable[..., Any]
) -> Callable[..., Optional[Union[Thread, Process]]]:
    """Decorator that converts a function into an asynchronous task.

    This is the main decorator of the library. It wraps any function
    to make it run asynchronously in the background using the current
    pool's configuration (threads or processes).

    Args:
        callee: The function to be made asynchronous

    Returns:
        Decorated function that returns Thread/Process object or None

    Example:
        @task
        def my_function(x, y):
            return x + y

        result = my_function(1, 2)  # Returns Thread/Process object
        wait_for_tasks()  # Wait for completion
    """
    # Ensure we have at least one pool available for task execution
    if not config["POOLS"]:
        createPool()  # Create default pool if none exists

    def _run_via_pool(*args: Any, **kwargs: Any) -> Any:
        """Internal wrapper that handles semaphore-controlled execution.

        This function is what actually runs in the background thread/process.
        It acquires the pool's semaphore (if any) before executing the
        original function, ensuring we don't exceed the concurrent limit.
        """
        pool = config["POOLS"][config["POOL_NAME"]]['pool']
        if pool is not None:
            # Limited pool: acquire semaphore before execution
            with pool:
                return callee(*args, **kwargs)
        else:
            # Unlimited pool: execute immediately
            return callee(*args, **kwargs)

    @wraps(callee)  # Preserve original function metadata
    def async_method(
        *args: Any, **kwargs: Any
    ) -> Optional[Union[Thread, Process]]:
        """The actual decorated function that users call.

        This decides whether to run synchronously (for 0-thread pools)
        or asynchronously (for normal pools). It handles the creation
        and startup of Thread/Process objects.
        """
        # Check if this pool runs synchronously (threads=0)
        if config["POOLS"][config["POOL_NAME"]]['threads'] == 0:
            # No threading: execute immediately and return None
            callee(*args, **kwargs)
            return None

        # Check if we're in shutdown mode
        if not config["KILL_RECEIVED"]:
            # Normal operation: create background task
            try:
                # Get the engine class (Thread or Process)
                engine_class = config["POOLS"][config["POOL_NAME"]]['engine']

                # Create the task with daemon=False for proper cleanup
                single = engine_class(
                    target=_run_via_pool,
                    args=args,
                    kwargs=kwargs,
                    daemon=False
                )
            except Exception:
                # Fallback for older Python versions without daemon param
                single = engine_class(
                    target=_run_via_pool,
                    args=args,
                    kwargs=kwargs
                )

            # Track this task for monitoring and cleanup
            config["TASKS"].append(single)

            # Start the task execution
            single.start()

            # Return the task object for user control
            return single

        # Shutdown mode: don't create new tasks
        return None

    return async_method


def get_list_of_tasks() -> List[Union[Thread, Process]]:
    """Retrieve all tasks ever created by this library.

    This includes both currently running tasks and completed ones.
    Useful for debugging and monitoring task history.

    Returns:
        List of all Thread/Process objects created by @task decorator

    Note:
        Completed tasks remain in this list until program termination.
        Use get_active_tasks() to see only currently running tasks.
    """
    return config["TASKS"]


def get_active_tasks() -> List[Union[Thread, Process]]:
    """Retrieve only the currently running tasks.

    Filters the complete task list to show only tasks that are still
    executing. This is more useful than get_list_of_tasks() for
    monitoring current system load.

    Returns:
        List of Thread/Process objects that are still running

    Example:
        active = get_active_tasks()
        print(f"Currently running {len(active)} tasks")
    """
    return [task for task in config["TASKS"] if task.is_alive()]


def wait_for_tasks(sleep: float = 0) -> bool:
    """Block until all background tasks complete execution.

    This is the primary synchronization mechanism. It prevents new
    tasks from being created and waits for existing ones to finish.
    Essential for ensuring all work is done before program exit.

    Args:
        sleep: Seconds to sleep between checks. 0 means busy-wait.
               Higher values reduce CPU usage but increase latency.

    Returns:
        Always returns True when all tasks are complete

    Note:
        Sets KILL_RECEIVED=True during execution to prevent new tasks,
        then resets it to False when done.
    """
    # Signal that we're in shutdown mode - no new tasks allowed
    config["KILL_RECEIVED"] = True

    # Handle synchronous pools (threads=0) - nothing to wait for
    if config["POOLS"][config["POOL_NAME"]]['threads'] == 0:
        return True

    try:
        # Main waiting loop
        while True:
            # Find all tasks that are still running
            running_tasks = [
                task for task in config["TASKS"]
                if task is not None and task.is_alive()
            ]

            # Attempt to join each running task with timeout
            # This gives each task a chance to complete cleanly
            for task in running_tasks:
                task.join(1)  # Wait up to 1 second per task

            # Recheck which tasks are still running after join attempts
            still_running = len([
                task for task in config["TASKS"]
                if task is not None and task.is_alive()
            ])

            # If no tasks are running, we're done
            if still_running == 0:
                break

            # Optional sleep to reduce CPU usage during waiting
            if sleep > 0:
                _time.sleep(sleep)

    except Exception:
        # Ignore any exceptions during cleanup (e.g., interrupted joins)
        pass

    # Re-enable task creation for future use
    config["KILL_RECEIVED"] = False
    return True


def killall(self: Any = None, cls: Any = None) -> None:
    """Emergency shutdown function that terminates the entire program.

    This is a last-resort function that immediately exits the program,
    potentially leaving tasks in an inconsistent state. It tries
    sys.exit() first, then os._exit() as a final measure.

    Args:
        self: Unused parameter kept for backward compatibility
        cls: Unused parameter kept for backward compatibility

    Warning:
        This function does NOT wait for tasks to complete cleanly.
        Use wait_for_tasks() for graceful shutdown instead.

    Note:
        The function attempts sys.exit(0) first (which allows cleanup
        handlers to run), falling back to os._exit(0) which terminates
        immediately without any cleanup.
    """
    # Signal shutdown mode to prevent new tasks
    config["KILL_RECEIVED"] = True

    try:
        # Attempt graceful exit (allows cleanup handlers)
        sysexit(0)
    except SystemExit:
        # Force immediate termination if graceful exit fails
        osexit(0)

    # This line should never be reached, but reset flag just in case
    config["KILL_RECEIVED"] = False
