class FeatureLibError(Exception):
    def __init__(self, message, location=None):
        Exception.__init__(self, message)
        self.location = location

    def __str__(self):
        message = Exception.__str__(self)
        if self.location:
            return f"{self.location}: {message}"
        else:
            return message


class IncludedFeaNotFound(FeatureLibError):
    def __str__(self):
        assert self.location is not None

        message = (
            "The following feature file should be included but cannot be found: "
            f"{Exception.__str__(self)}"
        )
        return f"{self.location}: {message}"
