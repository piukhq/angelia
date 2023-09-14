from dataclasses import asdict, dataclass
from enum import Enum


class EventType(str, Enum):
    CREATE = "create"
    DELETE = "delete"
    UPDATE = "update"


@dataclass
class HistoryData:
    event_name: str
    user_id: int | str  # Can be integer id field or external_id
    channel_slug: str
    event_type: EventType
    table: str
    change: str
    payload: dict
    related: dict

    def to_dict(self) -> dict:
        dict_repr = asdict(self)

        # "event_type" is a clearer description of the attribute but the payload expects it as "event" so
        # we swap them when returning the dict representation.
        event_type = dict_repr.pop("event_type").value
        dict_repr.update(event=event_type)
        return dict_repr
