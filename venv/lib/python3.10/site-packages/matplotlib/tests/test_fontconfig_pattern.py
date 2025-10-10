import pytest

from matplotlib.font_manager import FontProperties


# Attributes on FontProperties object to check for consistency
keys = [
    "get_family",
    "get_style",
    "get_variant",
    "get_weight",
    "get_size",
    ]


def test_fontconfig_pattern():
    """Test converting a FontProperties to string then back."""

    # Defaults
    test = "defaults "
    f1 = FontProperties()
    s = str(f1)

    f2 = FontProperties(s)
    for k in keys:
        assert getattr(f1, k)() == getattr(f2, k)(), test + k

    # Basic inputs
    test = "basic "
    f1 = FontProperties(family="serif", size=20, style="italic")
    s = str(f1)

    f2 = FontProperties(s)
    for k in keys:
        assert getattr(f1, k)() == getattr(f2, k)(), test + k

    # Full set of inputs.
    test = "full "
    f1 = FontProperties(family="sans-serif", size=24, weight="bold",
                        style="oblique", variant="small-caps",
                        stretch="expanded")
    s = str(f1)

    f2 = FontProperties(s)
    for k in keys:
        assert getattr(f1, k)() == getattr(f2, k)(), test + k


def test_fontconfig_str():
    """Test FontProperties string conversions for correctness."""

    # Known good strings taken from actual font config specs on a linux box
    # and modified for MPL defaults.

    # Default values found by inspection.
    test = "defaults "
    s = ("sans\\-serif:style=normal:variant=normal:weight=normal"
         ":stretch=normal:size=12.0")
    font = FontProperties(s)
    right = FontProperties()
    for k in keys:
        assert getattr(font, k)() == getattr(right, k)(), test + k

    test = "full "
    s = ("serif-24:style=oblique:variant=small-caps:weight=bold"
         ":stretch=expanded")
    font = FontProperties(s)
    right = FontProperties(family="serif", size=24, weight="bold",
                           style="oblique", variant="small-caps",
                           stretch="expanded")
    for k in keys:
        assert getattr(font, k)() == getattr(right, k)(), test + k


def test_fontconfig_unknown_constant():
    with pytest.raises(ValueError, match="ParseException"):
        FontProperties(":unknown")
