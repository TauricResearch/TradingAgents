"""
Code of the config system; not related to fontTools or fonts in particular.

The options that are specific to fontTools are in :mod:`fontTools.config`.

To create your own config system, you need to create an instance of
:class:`Options`, and a subclass of :class:`AbstractConfig` with its
``options`` class variable set to your instance of Options.

"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    Iterable,
    Mapping,
    MutableMapping,
    Optional,
    Set,
    Union,
)


log = logging.getLogger(__name__)

__all__ = [
    "AbstractConfig",
    "ConfigAlreadyRegisteredError",
    "ConfigError",
    "ConfigUnknownOptionError",
    "ConfigValueParsingError",
    "ConfigValueValidationError",
    "Option",
    "Options",
]


class ConfigError(Exception):
    """Base exception for the config module."""


class ConfigAlreadyRegisteredError(ConfigError):
    """Raised when a module tries to register a configuration option that
    already exists.

    Should not be raised too much really, only when developing new fontTools
    modules.
    """

    def __init__(self, name):
        super().__init__(f"Config option {name} is already registered.")


class ConfigValueParsingError(ConfigError):
    """Raised when a configuration value cannot be parsed."""

    def __init__(self, name, value):
        super().__init__(
            f"Config option {name}: value cannot be parsed (given {repr(value)})"
        )


class ConfigValueValidationError(ConfigError):
    """Raised when a configuration value cannot be validated."""

    def __init__(self, name, value):
        super().__init__(
            f"Config option {name}: value is invalid (given {repr(value)})"
        )


class ConfigUnknownOptionError(ConfigError):
    """Raised when a configuration option is unknown."""

    def __init__(self, option_or_name):
        name = (
            f"'{option_or_name.name}' (id={id(option_or_name)})>"
            if isinstance(option_or_name, Option)
            else f"'{option_or_name}'"
        )
        super().__init__(f"Config option {name} is unknown")


# eq=False because Options are unique, not fungible objects
@dataclass(frozen=True, eq=False)
class Option:
    name: str
    """Unique name identifying the option (e.g. package.module:MY_OPTION)."""
    help: str
    """Help text for this option."""
    default: Any
    """Default value for this option."""
    parse: Callable[[str], Any]
    """Turn input (e.g. string) into proper type. Only when reading from file."""
    validate: Optional[Callable[[Any], bool]] = None
    """Return true if the given value is an acceptable value."""

    @staticmethod
    def parse_optional_bool(v: str) -> Optional[bool]:
        s = str(v).lower()
        if s in {"0", "no", "false"}:
            return False
        if s in {"1", "yes", "true"}:
            return True
        if s in {"auto", "none"}:
            return None
        raise ValueError("invalid optional bool: {v!r}")

    @staticmethod
    def validate_optional_bool(v: Any) -> bool:
        return v is None or isinstance(v, bool)


class Options(Mapping):
    """Registry of available options for a given config system.

    Define new options using the :meth:`register()` method.

    Access existing options using the Mapping interface.
    """

    __options: Dict[str, Option]

    def __init__(self, other: "Options" = None) -> None:
        self.__options = {}
        if other is not None:
            for option in other.values():
                self.register_option(option)

    def register(
        self,
        name: str,
        help: str,
        default: Any,
        parse: Callable[[str], Any],
        validate: Optional[Callable[[Any], bool]] = None,
    ) -> Option:
        """Create and register a new option."""
        return self.register_option(Option(name, help, default, parse, validate))

    def register_option(self, option: Option) -> Option:
        """Register a new option."""
        name = option.name
        if name in self.__options:
            raise ConfigAlreadyRegisteredError(name)
        self.__options[name] = option
        return option

    def is_registered(self, option: Option) -> bool:
        """Return True if the same option object is already registered."""
        return self.__options.get(option.name) is option

    def __getitem__(self, key: str) -> Option:
        return self.__options.__getitem__(key)

    def __iter__(self) -> Iterator[str]:
        return self.__options.__iter__()

    def __len__(self) -> int:
        return self.__options.__len__()

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}({{\n"
            + "".join(
                f"    {k!r}: Option(default={v.default!r}, ...),\n"
                for k, v in self.__options.items()
            )
            + "})"
        )


_USE_GLOBAL_DEFAULT = object()


class AbstractConfig(MutableMapping):
    """
    Create a set of config values, optionally pre-filled with values from
    the given dictionary or pre-existing config object.

    The class implements the MutableMapping protocol keyed by option name (`str`).
    For convenience its methods accept either Option or str as the key parameter.

    .. seealso:: :meth:`set()`

    This config class is abstract because it needs its ``options`` class
    var to be set to an instance of :class:`Options` before it can be
    instanciated and used.

    .. code:: python

        class MyConfig(AbstractConfig):
            options = Options()

        MyConfig.register_option( "test:option_name", "This is an option", 0, int, lambda v: isinstance(v, int))

        cfg = MyConfig({"test:option_name": 10})

    """

    options: ClassVar[Options]

    @classmethod
    def register_option(
        cls,
        name: str,
        help: str,
        default: Any,
        parse: Callable[[str], Any],
        validate: Optional[Callable[[Any], bool]] = None,
    ) -> Option:
        """Register an available option in this config system."""
        return cls.options.register(
            name, help=help, default=default, parse=parse, validate=validate
        )

    _values: Dict[str, Any]

    def __init__(
        self,
        values: Union[AbstractConfig, Dict[Union[Option, str], Any]] = {},
        parse_values: bool = False,
        skip_unknown: bool = False,
    ):
        self._values = {}
        values_dict = values._values if isinstance(values, AbstractConfig) else values
        for name, value in values_dict.items():
            self.set(name, value, parse_values, skip_unknown)

    def _resolve_option(self, option_or_name: Union[Option, str]) -> Option:
        if isinstance(option_or_name, Option):
            option = option_or_name
            if not self.options.is_registered(option):
                raise ConfigUnknownOptionError(option)
            return option
        elif isinstance(option_or_name, str):
            name = option_or_name
            try:
                return self.options[name]
            except KeyError:
                raise ConfigUnknownOptionError(name)
        else:
            raise TypeError(
                "expected Option or str, found "
                f"{type(option_or_name).__name__}: {option_or_name!r}"
            )

    def set(
        self,
        option_or_name: Union[Option, str],
        value: Any,
        parse_values: bool = False,
        skip_unknown: bool = False,
    ):
        """Set the value of an option.

        Args:
            * `option_or_name`: an `Option` object or its name (`str`).
            * `value`: the value to be assigned to given option.
            * `parse_values`: parse the configuration value from a string into
                its proper type, as per its `Option` object. The default
                behavior is to raise `ConfigValueValidationError` when the value
                is not of the right type. Useful when reading options from a
                file type that doesn't support as many types as Python.
            * `skip_unknown`: skip unknown configuration options. The default
                behaviour is to raise `ConfigUnknownOptionError`. Useful when
                reading options from a configuration file that has extra entries
                (e.g. for a later version of fontTools)
        """
        try:
            option = self._resolve_option(option_or_name)
        except ConfigUnknownOptionError as e:
            if skip_unknown:
                log.debug(str(e))
                return
            raise

        # Can be useful if the values come from a source that doesn't have
        # strict typing (.ini file? Terminal input?)
        if parse_values:
            try:
                value = option.parse(value)
            except Exception as e:
                raise ConfigValueParsingError(option.name, value) from e

        if option.validate is not None and not option.validate(value):
            raise ConfigValueValidationError(option.name, value)

        self._values[option.name] = value

    def get(
        self, option_or_name: Union[Option, str], default: Any = _USE_GLOBAL_DEFAULT
    ) -> Any:
        """
        Get the value of an option. The value which is returned is the first
        provided among:

        1. a user-provided value in the options's ``self._values`` dict
        2. a caller-provided default value to this method call
        3. the global default for the option provided in ``fontTools.config``

        This is to provide the ability to migrate progressively from config
        options passed as arguments to fontTools APIs to config options read
        from the current TTFont, e.g.

        .. code:: python

            def fontToolsAPI(font, some_option):
                value = font.cfg.get("someLib.module:SOME_OPTION", some_option)
                # use value

        That way, the function will work the same for users of the API that
        still pass the option to the function call, but will favour the new
        config mechanism if the given font specifies a value for that option.
        """
        option = self._resolve_option(option_or_name)
        if option.name in self._values:
            return self._values[option.name]
        if default is not _USE_GLOBAL_DEFAULT:
            return default
        return option.default

    def copy(self):
        return self.__class__(self._values)

    def __getitem__(self, option_or_name: Union[Option, str]) -> Any:
        return self.get(option_or_name)

    def __setitem__(self, option_or_name: Union[Option, str], value: Any) -> None:
        return self.set(option_or_name, value)

    def __delitem__(self, option_or_name: Union[Option, str]) -> None:
        option = self._resolve_option(option_or_name)
        del self._values[option.name]

    def __iter__(self) -> Iterable[str]:
        return self._values.__iter__()

    def __len__(self) -> int:
        return len(self._values)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({repr(self._values)})"
