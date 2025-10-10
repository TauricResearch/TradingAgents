import numpy as np

import pandas._config.config as cf

from pandas import (
    DataFrame,
    MultiIndex,
)


class TestTableSchemaRepr:
    def test_publishes(self, ip):
        ipython = ip.instance(config=ip.config)
        df = DataFrame({"A": [1, 2]})
        objects = [df["A"], df]  # dataframe / series
        expected_keys = [
            {"text/plain", "application/vnd.dataresource+json"},
            {"text/plain", "text/html", "application/vnd.dataresource+json"},
        ]

        opt = cf.option_context("display.html.table_schema", True)
        last_obj = None
        for obj, expected in zip(objects, expected_keys):
            last_obj = obj
            with opt:
                formatted = ipython.display_formatter.format(obj)
            assert set(formatted[0].keys()) == expected

        with_latex = cf.option_context("styler.render.repr", "latex")

        with opt, with_latex:
            formatted = ipython.display_formatter.format(last_obj)

        expected = {
            "text/plain",
            "text/html",
            "text/latex",
            "application/vnd.dataresource+json",
        }
        assert set(formatted[0].keys()) == expected

    def test_publishes_not_implemented(self, ip):
        # column MultiIndex
        # GH#15996
        midx = MultiIndex.from_product([["A", "B"], ["a", "b", "c"]])
        df = DataFrame(
            np.random.default_rng(2).standard_normal((5, len(midx))), columns=midx
        )

        opt = cf.option_context("display.html.table_schema", True)

        with opt:
            formatted = ip.instance(config=ip.config).display_formatter.format(df)

        expected = {"text/plain", "text/html"}
        assert set(formatted[0].keys()) == expected

    def test_config_on(self):
        df = DataFrame({"A": [1, 2]})
        with cf.option_context("display.html.table_schema", True):
            result = df._repr_data_resource_()

        assert result is not None

    def test_config_default_off(self):
        df = DataFrame({"A": [1, 2]})
        with cf.option_context("display.html.table_schema", False):
            result = df._repr_data_resource_()

        assert result is None

    def test_enable_data_resource_formatter(self, ip):
        # GH#10491
        formatters = ip.instance(config=ip.config).display_formatter.formatters
        mimetype = "application/vnd.dataresource+json"

        with cf.option_context("display.html.table_schema", True):
            assert "application/vnd.dataresource+json" in formatters
            assert formatters[mimetype].enabled

        # still there, just disabled
        assert "application/vnd.dataresource+json" in formatters
        assert not formatters[mimetype].enabled

        # able to re-set
        with cf.option_context("display.html.table_schema", True):
            assert "application/vnd.dataresource+json" in formatters
            assert formatters[mimetype].enabled
            # smoke test that it works
            ip.instance(config=ip.config).display_formatter.format(cf)
