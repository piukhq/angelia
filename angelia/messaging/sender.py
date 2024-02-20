from datetime import datetime
from time import time
from typing import TYPE_CHECKING, Any
from uuid import UUID

import arrow
from sqlalchemy.orm import ColumnProperty, RelationshipProperty, mapper

from angelia.api.shared_data import SharedData
from angelia.hermes.utils import EventType, HistoryData
from angelia.messaging.message_broker import ProducerQueues, sending_service
from angelia.report import ctx, history_logger, send_logger

if TYPE_CHECKING:
    from angelia.hermes.models import ModelBase

    TargetType = type[ModelBase]


def sql_history(target_model: "TargetType", event_type: str, pk: int, change: str) -> None:
    """
    We now do not send the event_time.  Hermes adds this using
    send message added utc_adjusted payload parameter to account for server time variations
    """
    try:
        sh = SharedData()  # type: ignore [call-arg]
        if sh is not None:
            manager = target_model._sa_class_manager
            table = manager.mapper.local_table.fullname if manager.is_mapped else str(target_model)
            auth_data = sh.request.context.auth_instance.auth_data

            history_data = {
                "user_id": auth_data.get("sub"),
                "channel_slug": auth_data.get("channel"),
                "event": event_type,
                "table": str(table),
                "change": change,
                "id": pk,
            }
            send_message_to_hermes("sql_history", history_data)
    except Exception as e:
        # Best allow an exception as it would prevent the data being written
        history_logger.error(f"Trapped Exception Lost sql history report due to {e}")


def process_mapper_attributes(target: "TargetType", attr: str, payload: dict, related: dict) -> None:
    if isinstance(attr, ColumnProperty):
        name = attr.key
        value = getattr(target, name)
        if value is None or isinstance(value, str | float | int | str | bool):
            payload[name] = value
        elif isinstance(value, UUID):
            payload[name] = str(value)
        elif isinstance(value, datetime):
            payload[name] = value.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
    elif isinstance(attr, RelationshipProperty):
        name = attr.key
        value = getattr(target, name)
        try:
            if not isinstance(value, list):
                # not a list if primary related
                if value is None:
                    related[name] = None
                else:
                    related[name] = value.id
        except Exception as e:
            # Best allow an exception as it would prevent the data being written
            history_logger.error(f"Trapped Exception mapper history relationship id for {name} not found due to {e}")


def mapper_history(target: "TargetType", event_type: EventType, mapped: mapper) -> HistoryData | None:
    """
    We now do not send the event_time.  Hermes adds this using
    send message added utc_adjusted payload parameter to account for server time variations

    """
    try:
        sh = SharedData()  # type: ignore [call-arg]
        if sh is not None:
            auth_data = sh.request.context.auth_instance.auth_data
            table = mapped.mapped_table
            payload: dict = {}
            related: dict = {}
            change = ""
            if event_type.value == "update":
                change = "updated"
            for attr in mapped.base_mapper.attrs:
                process_mapper_attributes(target, attr, payload, related)

            hermes_history_data = HistoryData(
                event_name="mapped_history",
                user_id=auth_data.get("sub"),
                channel_slug=auth_data.get("channel"),
                event_type=event_type,
                table=str(table),
                change=change,
                payload=payload,
                related=related,
            )

            return hermes_history_data
    except Exception as e:
        # Best allow an exception as it would prevent the data being written
        history_logger.error(f"Trapped Exception Lost mapper history report due to {e}")

    return None


def send_message_to_hermes(path: str, payload: dict, add_headers: dict | None = None) -> None:
    payload["utc_adjusted"] = arrow.utcnow().shift(microseconds=-100000).isoformat()
    msg_data = create_message_data(payload, path, add_headers)
    sending_service.queues[ProducerQueues.HERMES.name].send_message(**msg_data)
    send_logger.info(f"SENT: {path}")


def create_message_data(payload: Any, path: str | None = None, base_headers: dict | None = None) -> dict[str, Any]:
    if base_headers is None:
        base_headers = {}

    headers = base_headers | {
        "X-http-path": path,
        "X-epoch-timestamp": time(),
        "X-version": "1.0",
        "X-content-type": "application/json",
        "X-azure-ref": ctx.x_azure_ref,
    }

    return {"payload": payload, "headers": headers}
