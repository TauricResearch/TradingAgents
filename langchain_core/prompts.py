class ChatPromptTemplate:
    def __init__(self, *args, **kwargs):
        self.args = args

    def format_messages(self, **kwargs):
        return []


class MessagesPlaceholder:
    def __init__(self, variable_name: str):
        self.variable_name = variable_name
