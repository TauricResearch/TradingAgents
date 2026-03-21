from enum import Enum


class AnalystType(str, Enum):
    ODDS = "odds"
    SOCIAL = "social"
    NEWS = "news"
    EVENT = "event"
