import pytest

from pandas import Series

pytest.importorskip("matplotlib")
from pandas.plotting._matplotlib.style import get_standard_colors


class TestGetStandardColors:
    @pytest.mark.parametrize(
        "num_colors, expected",
        [
            (3, ["red", "green", "blue"]),
            (5, ["red", "green", "blue", "red", "green"]),
            (7, ["red", "green", "blue", "red", "green", "blue", "red"]),
            (2, ["red", "green"]),
            (1, ["red"]),
        ],
    )
    def test_default_colors_named_from_prop_cycle(self, num_colors, expected):
        import matplotlib as mpl
        from matplotlib.pyplot import cycler

        mpl_params = {
            "axes.prop_cycle": cycler(color=["red", "green", "blue"]),
        }
        with mpl.rc_context(rc=mpl_params):
            result = get_standard_colors(num_colors=num_colors)
            assert result == expected

    @pytest.mark.parametrize(
        "num_colors, expected",
        [
            (1, ["b"]),
            (3, ["b", "g", "r"]),
            (4, ["b", "g", "r", "y"]),
            (5, ["b", "g", "r", "y", "b"]),
            (7, ["b", "g", "r", "y", "b", "g", "r"]),
        ],
    )
    def test_default_colors_named_from_prop_cycle_string(self, num_colors, expected):
        import matplotlib as mpl
        from matplotlib.pyplot import cycler

        mpl_params = {
            "axes.prop_cycle": cycler(color="bgry"),
        }
        with mpl.rc_context(rc=mpl_params):
            result = get_standard_colors(num_colors=num_colors)
            assert result == expected

    @pytest.mark.parametrize(
        "num_colors, expected_name",
        [
            (1, ["C0"]),
            (3, ["C0", "C1", "C2"]),
            (
                12,
                [
                    "C0",
                    "C1",
                    "C2",
                    "C3",
                    "C4",
                    "C5",
                    "C6",
                    "C7",
                    "C8",
                    "C9",
                    "C0",
                    "C1",
                ],
            ),
        ],
    )
    def test_default_colors_named_undefined_prop_cycle(self, num_colors, expected_name):
        import matplotlib as mpl
        import matplotlib.colors as mcolors

        with mpl.rc_context(rc={}):
            expected = [mcolors.to_hex(x) for x in expected_name]
            result = get_standard_colors(num_colors=num_colors)
            assert result == expected

    @pytest.mark.parametrize(
        "num_colors, expected",
        [
            (1, ["red", "green", (0.1, 0.2, 0.3)]),
            (2, ["red", "green", (0.1, 0.2, 0.3)]),
            (3, ["red", "green", (0.1, 0.2, 0.3)]),
            (4, ["red", "green", (0.1, 0.2, 0.3), "red"]),
        ],
    )
    def test_user_input_color_sequence(self, num_colors, expected):
        color = ["red", "green", (0.1, 0.2, 0.3)]
        result = get_standard_colors(color=color, num_colors=num_colors)
        assert result == expected

    @pytest.mark.parametrize(
        "num_colors, expected",
        [
            (1, ["r", "g", "b", "k"]),
            (2, ["r", "g", "b", "k"]),
            (3, ["r", "g", "b", "k"]),
            (4, ["r", "g", "b", "k"]),
            (5, ["r", "g", "b", "k", "r"]),
            (6, ["r", "g", "b", "k", "r", "g"]),
        ],
    )
    def test_user_input_color_string(self, num_colors, expected):
        color = "rgbk"
        result = get_standard_colors(color=color, num_colors=num_colors)
        assert result == expected

    @pytest.mark.parametrize(
        "num_colors, expected",
        [
            (1, [(0.1, 0.2, 0.3)]),
            (2, [(0.1, 0.2, 0.3), (0.1, 0.2, 0.3)]),
            (3, [(0.1, 0.2, 0.3), (0.1, 0.2, 0.3), (0.1, 0.2, 0.3)]),
        ],
    )
    def test_user_input_color_floats(self, num_colors, expected):
        color = (0.1, 0.2, 0.3)
        result = get_standard_colors(color=color, num_colors=num_colors)
        assert result == expected

    @pytest.mark.parametrize(
        "color, num_colors, expected",
        [
            ("Crimson", 1, ["Crimson"]),
            ("DodgerBlue", 2, ["DodgerBlue", "DodgerBlue"]),
            ("firebrick", 3, ["firebrick", "firebrick", "firebrick"]),
        ],
    )
    def test_user_input_named_color_string(self, color, num_colors, expected):
        result = get_standard_colors(color=color, num_colors=num_colors)
        assert result == expected

    @pytest.mark.parametrize("color", ["", [], (), Series([], dtype="object")])
    def test_empty_color_raises(self, color):
        with pytest.raises(ValueError, match="Invalid color argument"):
            get_standard_colors(color=color, num_colors=1)

    @pytest.mark.parametrize(
        "color",
        [
            "bad_color",
            ("red", "green", "bad_color"),
            (0.1,),
            (0.1, 0.2),
            (0.1, 0.2, 0.3, 0.4, 0.5),  # must be either 3 or 4 floats
        ],
    )
    def test_bad_color_raises(self, color):
        with pytest.raises(ValueError, match="Invalid color"):
            get_standard_colors(color=color, num_colors=5)
