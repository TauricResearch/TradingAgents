class MessagesState:
    def __init__(self, messages=None):
        self.messages = list(messages) if messages else []
