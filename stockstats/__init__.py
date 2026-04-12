def wrap(data):
    class Stub:
        def __init__(self, df):
            self.df = df

    return Stub(data)
