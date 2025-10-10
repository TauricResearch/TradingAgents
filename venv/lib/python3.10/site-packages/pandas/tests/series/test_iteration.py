class TestIteration:
    def test_keys(self, datetime_series):
        assert datetime_series.keys() is datetime_series.index

    def test_iter_datetimes(self, datetime_series):
        for i, val in enumerate(datetime_series):
            # pylint: disable-next=unnecessary-list-index-lookup
            assert val == datetime_series.iloc[i]

    def test_iter_strings(self, string_series):
        for i, val in enumerate(string_series):
            # pylint: disable-next=unnecessary-list-index-lookup
            assert val == string_series.iloc[i]

    def test_iteritems_datetimes(self, datetime_series):
        for idx, val in datetime_series.items():
            assert val == datetime_series[idx]

    def test_iteritems_strings(self, string_series):
        for idx, val in string_series.items():
            assert val == string_series[idx]

        # assert is lazy (generators don't define reverse, lists do)
        assert not hasattr(string_series.items(), "reverse")

    def test_items_datetimes(self, datetime_series):
        for idx, val in datetime_series.items():
            assert val == datetime_series[idx]

    def test_items_strings(self, string_series):
        for idx, val in string_series.items():
            assert val == string_series[idx]

        # assert is lazy (generators don't define reverse, lists do)
        assert not hasattr(string_series.items(), "reverse")
