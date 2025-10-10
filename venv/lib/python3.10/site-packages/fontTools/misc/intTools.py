__all__ = ["popCount", "bit_count", "bit_indices"]


try:
    bit_count = int.bit_count
except AttributeError:

    def bit_count(v):
        return bin(v).count("1")


"""Return number of 1 bits (population count) of the absolute value of an integer.

See https://docs.python.org/3.10/library/stdtypes.html#int.bit_count
"""
popCount = bit_count  # alias


def bit_indices(v):
    """Return list of indices where bits are set, 0 being the index of the least significant bit.

    >>> bit_indices(0b101)
    [0, 2]
    """
    return [i for i, b in enumerate(bin(v)[::-1]) if b == "1"]
