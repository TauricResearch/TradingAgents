class ChatGoogleGenerativeAI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def invoke(self, input, config=None, **kwargs):
        return {"content": "mocked"}
