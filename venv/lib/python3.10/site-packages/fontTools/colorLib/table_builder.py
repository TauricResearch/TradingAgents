"""
colorLib.table_builder: Generic helper for filling in BaseTable derivatives from tuples and maps and such.

"""

import collections
import enum
from fontTools.ttLib.tables.otBase import (
    BaseTable,
    FormatSwitchingBaseTable,
    UInt8FormatSwitchingBaseTable,
)
from fontTools.ttLib.tables.otConverters import (
    ComputedInt,
    SimpleValue,
    Struct,
    Short,
    UInt8,
    UShort,
    IntValue,
    FloatValue,
    OptionalValue,
)
from fontTools.misc.roundTools import otRound


class BuildCallback(enum.Enum):
    """Keyed on (BEFORE_BUILD, class[, Format if available]).
    Receives (dest, source).
    Should return (dest, source), which can be new objects.
    """

    BEFORE_BUILD = enum.auto()

    """Keyed on (AFTER_BUILD, class[, Format if available]).
    Receives (dest).
    Should return dest, which can be a new object.
    """
    AFTER_BUILD = enum.auto()

    """Keyed on (CREATE_DEFAULT, class[, Format if available]).
    Receives no arguments.
    Should return a new instance of class.
    """
    CREATE_DEFAULT = enum.auto()


def _assignable(convertersByName):
    return {k: v for k, v in convertersByName.items() if not isinstance(v, ComputedInt)}


def _isNonStrSequence(value):
    return isinstance(value, collections.abc.Sequence) and not isinstance(value, str)


def _split_format(cls, source):
    if _isNonStrSequence(source):
        assert len(source) > 0, f"{cls} needs at least format from {source}"
        fmt, remainder = source[0], source[1:]
    elif isinstance(source, collections.abc.Mapping):
        assert "Format" in source, f"{cls} needs at least Format from {source}"
        remainder = source.copy()
        fmt = remainder.pop("Format")
    else:
        raise ValueError(f"Not sure how to populate {cls} from {source}")

    assert isinstance(
        fmt, collections.abc.Hashable
    ), f"{cls} Format is not hashable: {fmt!r}"
    assert fmt in cls.convertersByName, f"{cls} invalid Format: {fmt!r}"

    return fmt, remainder


class TableBuilder:
    """
    Helps to populate things derived from BaseTable from maps, tuples, etc.

    A table of lifecycle callbacks may be provided to add logic beyond what is possible
    based on otData info for the target class. See BuildCallbacks.
    """

    def __init__(self, callbackTable=None):
        if callbackTable is None:
            callbackTable = {}
        self._callbackTable = callbackTable

    def _convert(self, dest, field, converter, value):
        enumClass = getattr(converter, "enumClass", None)

        if enumClass:
            if isinstance(value, enumClass):
                pass
            elif isinstance(value, str):
                try:
                    value = getattr(enumClass, value.upper())
                except AttributeError:
                    raise ValueError(f"{value} is not a valid {enumClass}")
            else:
                value = enumClass(value)

        elif isinstance(converter, IntValue):
            value = otRound(value)
        elif isinstance(converter, FloatValue):
            value = float(value)

        elif isinstance(converter, Struct):
            if converter.repeat:
                if _isNonStrSequence(value):
                    value = [self.build(converter.tableClass, v) for v in value]
                else:
                    value = [self.build(converter.tableClass, value)]
                setattr(dest, converter.repeat, len(value))
            else:
                value = self.build(converter.tableClass, value)
        elif callable(converter):
            value = converter(value)

        setattr(dest, field, value)

    def build(self, cls, source):
        assert issubclass(cls, BaseTable)

        if isinstance(source, cls):
            return source

        callbackKey = (cls,)
        fmt = None
        if issubclass(cls, FormatSwitchingBaseTable):
            fmt, source = _split_format(cls, source)
            callbackKey = (cls, fmt)

        dest = self._callbackTable.get(
            (BuildCallback.CREATE_DEFAULT,) + callbackKey, lambda: cls()
        )()
        assert isinstance(dest, cls)

        convByName = _assignable(cls.convertersByName)
        skippedFields = set()

        # For format switchers we need to resolve converters based on format
        if issubclass(cls, FormatSwitchingBaseTable):
            dest.Format = fmt
            convByName = _assignable(convByName[dest.Format])
            skippedFields.add("Format")

        # Convert sequence => mapping so before thunk only has to handle one format
        if _isNonStrSequence(source):
            # Sequence (typically list or tuple) assumed to match fields in declaration order
            assert len(source) <= len(
                convByName
            ), f"Sequence of {len(source)} too long for {cls}; expected <= {len(convByName)} values"
            source = dict(zip(convByName.keys(), source))

        dest, source = self._callbackTable.get(
            (BuildCallback.BEFORE_BUILD,) + callbackKey, lambda d, s: (d, s)
        )(dest, source)

        if isinstance(source, collections.abc.Mapping):
            for field, value in source.items():
                if field in skippedFields:
                    continue
                converter = convByName.get(field, None)
                if not converter:
                    raise ValueError(
                        f"Unrecognized field {field} for {cls}; expected one of {sorted(convByName.keys())}"
                    )
                self._convert(dest, field, converter, value)
        else:
            # let's try as a 1-tuple
            dest = self.build(cls, (source,))

        for field, conv in convByName.items():
            if not hasattr(dest, field) and isinstance(conv, OptionalValue):
                setattr(dest, field, conv.DEFAULT)

        dest = self._callbackTable.get(
            (BuildCallback.AFTER_BUILD,) + callbackKey, lambda d: d
        )(dest)

        return dest


class TableUnbuilder:
    def __init__(self, callbackTable=None):
        if callbackTable is None:
            callbackTable = {}
        self._callbackTable = callbackTable

    def unbuild(self, table):
        assert isinstance(table, BaseTable)

        source = {}

        callbackKey = (type(table),)
        if isinstance(table, FormatSwitchingBaseTable):
            source["Format"] = int(table.Format)
            callbackKey += (table.Format,)

        for converter in table.getConverters():
            if isinstance(converter, ComputedInt):
                continue
            value = getattr(table, converter.name)

            enumClass = getattr(converter, "enumClass", None)
            if enumClass:
                source[converter.name] = value.name.lower()
            elif isinstance(converter, Struct):
                if converter.repeat:
                    source[converter.name] = [self.unbuild(v) for v in value]
                else:
                    source[converter.name] = self.unbuild(value)
            elif isinstance(converter, SimpleValue):
                # "simple" values (e.g. int, float, str) need no further un-building
                source[converter.name] = value
            else:
                raise NotImplementedError(
                    "Don't know how unbuild {value!r} with {converter!r}"
                )

        source = self._callbackTable.get(callbackKey, lambda s: s)(source)

        return source
