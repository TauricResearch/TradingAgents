"""
PostScript Type 1 fonts make use of two types of encryption: charstring
encryption and ``eexec`` encryption. Charstring encryption is used for
the charstrings themselves, while ``eexec`` is used to encrypt larger
sections of the font program, such as the ``Private`` and ``CharStrings``
dictionaries. Despite the different names, the algorithm is the same,
although ``eexec`` encryption uses a fixed initial key R=55665.

The algorithm uses cipher feedback, meaning that the ciphertext is used
to modify the key. Because of this, the routines in this module return
the new key at the end of the operation.

"""

from fontTools.misc.textTools import bytechr, bytesjoin, byteord


def _decryptChar(cipher, R):
    cipher = byteord(cipher)
    plain = ((cipher ^ (R >> 8))) & 0xFF
    R = ((cipher + R) * 52845 + 22719) & 0xFFFF
    return bytechr(plain), R


def _encryptChar(plain, R):
    plain = byteord(plain)
    cipher = ((plain ^ (R >> 8))) & 0xFF
    R = ((cipher + R) * 52845 + 22719) & 0xFFFF
    return bytechr(cipher), R


def decrypt(cipherstring, R):
    r"""
    Decrypts a string using the Type 1 encryption algorithm.

    Args:
            cipherstring: String of ciphertext.
            R: Initial key.

    Returns:
            decryptedStr: Plaintext string.
            R: Output key for subsequent decryptions.

    Examples::

            >>> testStr = b"\0\0asdadads asds\265"
            >>> decryptedStr, R = decrypt(testStr, 12321)
            >>> decryptedStr == b'0d\nh\x15\xe8\xc4\xb2\x15\x1d\x108\x1a<6\xa1'
            True
            >>> R == 36142
            True
    """
    plainList = []
    for cipher in cipherstring:
        plain, R = _decryptChar(cipher, R)
        plainList.append(plain)
    plainstring = bytesjoin(plainList)
    return plainstring, int(R)


def encrypt(plainstring, R):
    r"""
    Encrypts a string using the Type 1 encryption algorithm.

    Note that the algorithm as described in the Type 1 specification requires the
    plaintext to be prefixed with a number of random bytes. (For ``eexec`` the
    number of random bytes is set to 4.) This routine does *not* add the random
    prefix to its input.

    Args:
            plainstring: String of plaintext.
            R: Initial key.

    Returns:
            cipherstring: Ciphertext string.
            R: Output key for subsequent encryptions.

    Examples::

            >>> testStr = b"\0\0asdadads asds\265"
            >>> decryptedStr, R = decrypt(testStr, 12321)
            >>> decryptedStr == b'0d\nh\x15\xe8\xc4\xb2\x15\x1d\x108\x1a<6\xa1'
            True
            >>> R == 36142
            True

    >>> testStr = b'0d\nh\x15\xe8\xc4\xb2\x15\x1d\x108\x1a<6\xa1'
    >>> encryptedStr, R = encrypt(testStr, 12321)
    >>> encryptedStr == b"\0\0asdadads asds\265"
    True
    >>> R == 36142
    True
    """
    cipherList = []
    for plain in plainstring:
        cipher, R = _encryptChar(plain, R)
        cipherList.append(cipher)
    cipherstring = bytesjoin(cipherList)
    return cipherstring, int(R)


def hexString(s):
    import binascii

    return binascii.hexlify(s)


def deHexString(h):
    import binascii

    h = bytesjoin(h.split())
    return binascii.unhexlify(h)


if __name__ == "__main__":
    import sys
    import doctest

    sys.exit(doctest.testmod().failed)
