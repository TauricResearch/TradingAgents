# Copied from: https://github.com/encode/httpx/blob/master/httpx/_models.py,
# which is licensed under the BSD License.
# See https://github.com/encode/httpx/blob/master/LICENSE.md


from collections.abc import (
    ItemsView,
    Iterable,
    Iterator,
    KeysView,
    Mapping,
    MutableMapping,
    Sequence,
    ValuesView,
)
from typing import Any, AnyStr, Optional, Union, cast

HeaderTypes = Union[
    "Headers",
    Mapping[str, Optional[str]],
    Mapping[bytes, Optional[bytes]],
    Sequence[tuple[str, str]],
    Sequence[tuple[bytes, bytes]],
    Sequence[Union[str, bytes]],
]


def to_str(value: Union[str, bytes], encoding: str = "utf-8") -> str:
    return value if isinstance(value, str) else value.decode(encoding)


SENSITIVE_HEADERS = {"authorization", "proxy-authorization"}


def obfuscate_sensitive_headers(
    items: Iterable[tuple[AnyStr, Optional[AnyStr]]],
) -> Iterator[tuple[AnyStr, Optional[AnyStr]]]:
    for k, v in items:
        if to_str(k.lower()) in SENSITIVE_HEADERS:
            v = b"[secure]" if isinstance(v, bytes) else "[secure]"  # type: ignore
        yield k, v


def normalize_header_key(
    value: Union[str, bytes],
    lower: bool,
    encoding: Optional[str] = None,
) -> bytes:
    """
    Coerce str/bytes into a strictly byte-wise HTTP header key.
    """
    bytes_value = (
        value if isinstance(value, bytes) else value.encode(encoding or "ascii")
    )

    return bytes_value.lower() if lower else bytes_value


def normalize_header_value(
    value: Union[str, bytes, int, None], encoding: Optional[str] = None
) -> Union[bytes, None]:
    """
    Coerce str/bytes into a strictly byte-wise HTTP header value.
    """
    if value is None:
        return None

    if isinstance(value, bytes):
        return value

    # The default encoding for header value should be latin-1
    # See: RFC and https://github.com/python/cpython/blob/bc264eac3ad14dab748e33b3d714c2674872791f/Lib/http/client.py#L1309
    if isinstance(value, int):
        return str(value).encode()

    return cast(str, value).encode(encoding or "latin-1")


class Headers(MutableMapping[str, Optional[str]]):
    """
    HTTP headers, as a case-insensitive multi-dict.
    """

    def __init__(
        self, headers: Optional[HeaderTypes] = None, encoding: Optional[str] = None
    ):
        self._list: list[tuple[bytes, bytes, Optional[bytes]]]

        if isinstance(headers, Headers):
            self._list = list(headers._list)
            encoding = encoding or headers.encoding
        elif not headers:
            self._list = []
        elif isinstance(headers, Mapping):
            self._list = [
                (
                    normalize_header_key(k, lower=False, encoding=encoding),
                    normalize_header_key(k, lower=True, encoding=encoding),
                    normalize_header_value(v, encoding),
                )
                for k, v in headers.items()
            ]
        elif isinstance(headers, list):
            # list of "Name: Value" pairs
            if isinstance(headers[0], (str, bytes)):
                sep = ":" if isinstance(headers[0], str) else b":"
                h = []
                for line in headers:
                    k, v = line.split(sep, maxsplit=1)  # pyright: ignore
                    h.append((k, v.strip()))
            # list of (Name, Value) pairs
            elif isinstance(headers[0], tuple):
                h = headers
            self._list = [
                (
                    normalize_header_key(k, lower=False, encoding=encoding),
                    normalize_header_key(k, lower=True, encoding=encoding),
                    normalize_header_value(v, encoding),
                )
                for k, v in h  # pyright: ignore
            ]

        self._encoding = encoding

    @property
    def encoding(self) -> str:
        """
        Header encoding is mandated as ascii, but we allow fallbacks to utf-8
        or iso-8859-1.
        """
        if self._encoding is None:
            for encoding in ["ascii", "utf-8"]:
                for key, value in self.raw:
                    try:
                        key.decode(encoding)
                        value.decode(encoding) if value is not None else value
                    except UnicodeDecodeError:
                        break
                else:
                    # The else block runs if 'break' did not occur, meaning
                    # all values fitted the encoding.
                    self._encoding = encoding
                    break
            else:
                # The ISO-8859-1 encoding covers all 256 code points in a byte,
                # so will never raise decode errors.
                self._encoding = "iso-8859-1"
        return self._encoding

    @encoding.setter
    def encoding(self, value: str) -> None:
        self._encoding = value

    @property
    def raw(self) -> list[tuple[bytes, Optional[bytes]]]:
        """
        Returns a list of the raw header items, as byte pairs.
        """
        return [(raw_key, value) for raw_key, _, value in self._list]

    def keys(self) -> KeysView[str]:
        return {key.decode(self.encoding): None for _, key, _ in self._list}.keys()

    def values(self) -> ValuesView[Optional[str]]:
        values_dict: dict[str, str] = {}
        for _, key, value in self._list:
            str_key = key.decode(self.encoding)
            str_value = value.decode(self.encoding) if value is not None else "None"
            if str_key in values_dict:
                values_dict[str_key] += f", {str_value}"
            else:
                values_dict[str_key] = str_value
        return values_dict.values()

    def items(self) -> ItemsView[str, Optional[str]]:
        """
        Return `(key, value)` items of headers. Concatenate headers
        into a single comma separated value when a key occurs multiple times.
        """
        values_dict: dict[str, str] = {}
        for _, key, value in self._list:
            str_key = key.decode(self.encoding)
            str_value = value.decode(self.encoding) if value is not None else "None"
            if str_key in values_dict:
                values_dict[str_key] += f", {str_value}"
            else:
                values_dict[str_key] = str_value
        return values_dict.items()

    def multi_items(self) -> list[tuple[str, Optional[str]]]:
        """
        Return a list of `(key, value)` pairs of headers. Allow multiple
        occurrences of the same key without concatenating into a single
        comma separated value.
        """
        return [
            (
                key.decode(self.encoding),
                value.decode(self.encoding) if value is not None else value,
            )
            for key, _, value in self._list
        ]

    def get(self, key: str, default: Any = None) -> Any:
        """
        Return a header value. If multiple occurrences of the header occur
        then concatenate them together with commas.
        """
        try:
            return self[key]
        except KeyError:
            return default

    def get_list(self, key: str, split_commas: bool = False) -> list[Optional[str]]:
        """
        Return a list of all header values for a given key.
        If `split_commas=True` is passed, then any comma separated header
        values are split into multiple return strings.
        """
        get_header_key = key.lower().encode(self.encoding)

        values = [
            item_value.decode(self.encoding) if item_value is not None else item_value
            for _, item_key, item_value in self._list
            if item_key.lower() == get_header_key
        ]

        if not split_commas:
            return values

        split_values = []
        for value in values:
            split_values.extend([item.strip() for item in value.split(",")])  # type: ignore
        return split_values

    def update(self, headers: Optional[HeaderTypes] = None) -> None:  # type: ignore
        headers = Headers(headers)
        for key in headers:
            if key in self:
                self.pop(key)
        self._list.extend(headers._list)

    def copy(self) -> "Headers":
        return Headers(self, encoding=self.encoding)

    def __getitem__(self, key: str) -> Optional[str]:
        """
        Return a single header value.
        If there are multiple headers with the same key, then we concatenate
        them with commas. See: https://tools.ietf.org/html/rfc7230#section-3.2.2
        """
        normalized_key = key.lower().encode(self.encoding)

        items = [
            header_value.decode(self.encoding)
            if header_value is not None
            else header_value
            for _, header_key, header_value in self._list
            if header_key == normalized_key
        ]

        if items == [None]:
            return None

        if items:
            return ", ".join([str(item) for item in items])

        raise KeyError(key)

    def __setitem__(self, key: str, value: Optional[str]) -> None:
        """
        Set the header `key` to `value`, removing any duplicate entries.
        Retains insertion order.
        """
        set_key = key.encode(self._encoding or "utf-8")
        set_value = (
            value.encode(self._encoding or "utf-8") if value is not None else value
        )
        lookup_key = set_key.lower()

        found_indexes = [
            idx
            for idx, (_, item_key, _) in enumerate(self._list)
            if item_key == lookup_key
        ]

        for idx in reversed(found_indexes[1:]):
            del self._list[idx]

        if found_indexes:
            idx = found_indexes[0]
            self._list[idx] = (set_key, lookup_key, set_value)
        else:
            self._list.append((set_key, lookup_key, set_value))

    def __delitem__(self, key: str) -> None:
        """
        Remove the header `key`.
        """
        del_key = key.lower().encode(self.encoding)

        pop_indexes = [
            idx
            for idx, (_, item_key, _) in enumerate(self._list)
            if item_key.lower() == del_key
        ]

        if not pop_indexes:
            raise KeyError(key)

        for idx in reversed(pop_indexes):
            del self._list[idx]

    def __contains__(self, key: Any) -> bool:
        header_key = key.lower().encode(self.encoding)
        return header_key in [key for _, key, _ in self._list]

    def __iter__(self) -> Iterator[Any]:
        return iter(self.keys())

    def __len__(self) -> int:
        return len(self._list)

    def __eq__(self, other: Any) -> bool:
        try:
            other_headers = Headers(other)
        except ValueError:
            return False

        self_list = [(key, value) for _, key, value in self._list]
        other_list = [(key, value) for _, key, value in other_headers._list]
        return sorted(self_list) == sorted(other_list)

    def __repr__(self) -> str:
        class_name = self.__class__.__name__

        encoding_str = ""
        if self.encoding != "ascii":
            encoding_str = f", encoding={self.encoding!r}"

        as_list = list(obfuscate_sensitive_headers(self.multi_items()))
        as_dict = dict(as_list)

        no_duplicate_keys = len(as_dict) == len(as_list)
        if no_duplicate_keys:
            return f"{class_name}({as_dict!r}{encoding_str})"
        return f"{class_name}({as_list!r}{encoding_str})"
