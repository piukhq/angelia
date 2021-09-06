from enum import Enum


class JourneyTypes(str, Enum):
    JOIN = 0
    LINK = 1
    ADD = 2
    UPDATE = 3
