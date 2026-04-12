class HumanMessage:
    def __init__(self, content: str = ""):
        self.content = content


class RemoveMessage:
    def __init__(self, id=None):
        self.id = id
