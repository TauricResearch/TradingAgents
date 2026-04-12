class BM25Okapi:
    def __init__(self, corpus, *args, **kwargs):
        self.corpus = list(corpus)

    def get_scores(self, query):
        return [0.0 for _ in self.corpus]
