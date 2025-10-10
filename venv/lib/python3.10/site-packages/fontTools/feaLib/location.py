from typing import NamedTuple


class FeatureLibLocation(NamedTuple):
    """A location in a feature file"""

    file: str
    line: int
    column: int

    def __str__(self):
        return f"{self.file}:{self.line}:{self.column}"
