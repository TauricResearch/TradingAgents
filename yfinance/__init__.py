from datetime import datetime


class Ticker:
    def __init__(self, symbol: str):
        self.symbol = symbol

    def history(self, start=None, end=None, **kwargs):
        class DummyData:
            def __init__(self):
                self.index = type("Idx", (), {"tz": None})()
                self.columns = []
                self._data = []

            @property
            def empty(self):
                return True

            def to_csv(self):
                return ""

            def __len__(self):
                return 0

        return DummyData()
