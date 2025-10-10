from __future__ import annotations

import math


def calc_chunk_sizes(
    chunk_size: int | tuple[int, int] | None,
    chunk_count: int | tuple[int, int] | None,
    total_chunk_count: int | None,
    ny: int,
    nx: int,
) -> tuple[int, int]:
    """Calculate chunk sizes.

    Args:
        chunk_size (int or tuple(int, int), optional): Chunk size in (y, x) directions, or the same
            size in both directions if only one is specified. Cannot be negative.
        chunk_count (int or tuple(int, int), optional): Chunk count in (y, x) directions, or the
            same count in both directions if only one is specified. If less than 1, set to 1.
        total_chunk_count (int, optional): Total number of chunks. If less than 1, set to 1.
        ny (int): Number of grid points in y-direction.
        nx (int): Number of grid points in x-direction.

    Return:
        tuple(int, int): Chunk sizes (y_chunk_size, x_chunk_size).

    Note:
        Zero or one of ``chunk_size``, ``chunk_count`` and ``total_chunk_count`` should be
        specified.
    """
    if sum([chunk_size is not None, chunk_count is not None, total_chunk_count is not None]) > 1:
        raise ValueError("Only one of chunk_size, chunk_count and total_chunk_count should be set")

    if nx < 2 or ny < 2:
        raise ValueError(f"(ny, nx) must be at least (2, 2), not ({ny}, {nx})")

    if total_chunk_count is not None:
        max_chunk_count = (nx-1)*(ny-1)
        total_chunk_count = min(max(total_chunk_count, 1), max_chunk_count)
        if total_chunk_count == 1:
            chunk_size = 0
        elif total_chunk_count == max_chunk_count:
            chunk_size = (1, 1)
        else:
            factors = two_factors(total_chunk_count)
            if ny > nx:
                chunk_count = factors
            else:
                chunk_count = (factors[1], factors[0])

    if chunk_count is not None:
        if isinstance(chunk_count, tuple):
            y_chunk_count, x_chunk_count = chunk_count
        else:
            y_chunk_count = x_chunk_count = chunk_count
        x_chunk_count = min(max(x_chunk_count, 1), nx-1)
        y_chunk_count = min(max(y_chunk_count, 1), ny-1)
        chunk_size = (math.ceil((ny-1) / y_chunk_count), math.ceil((nx-1) / x_chunk_count))

    if chunk_size is None:
        y_chunk_size = x_chunk_size = 0
    elif isinstance(chunk_size, tuple):
        y_chunk_size, x_chunk_size = chunk_size
    else:
        y_chunk_size = x_chunk_size = chunk_size

    if x_chunk_size < 0 or y_chunk_size < 0:
        raise ValueError("chunk_size cannot be negative")

    return y_chunk_size, x_chunk_size


def two_factors(n: int) -> tuple[int, int]:
    """Split an integer into two integer factors.

    The two factors will be as close as possible to the sqrt of n, and are returned in decreasing
    order.  Worst case returns (n, 1).

    Args:
        n (int): The integer to factorize, must be positive.

    Return:
        tuple(int, int): The two factors of n, in decreasing order.
    """
    if n < 0:
        raise ValueError(f"two_factors expects positive integer not {n}")

    i = math.ceil(math.sqrt(n))
    while n % i != 0:
        i -= 1
    j = n // i
    if i > j:
        return i, j
    else:
        return j, i
