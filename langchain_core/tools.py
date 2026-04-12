from functools import wraps
from typing import Callable, Optional


def tool(*args: str, **kwargs: str):
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*f_args, **f_kwargs):
            return func(*f_args, **f_kwargs)

        return wrapper

    if args and callable(args[0]):
        return decorator(args[0])
    return decorator
