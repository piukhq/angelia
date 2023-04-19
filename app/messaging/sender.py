import json
from datetime import datetime
from time import time
from typing import Any, Dict, Optional
from uuid import UUID

import arrow
from sqlalchemy.orm import ColumnProperty, RelationshipProperty, mapper

from app.api.shared_data import SharedData
from app.hermes.utils import EventType, HistoryData
from app.messaging.message_broker import SendingService
from app.report import history_logger, send_logger
from settings import RABBIT_DSN, TO_HERMES_QUEUE

message_sender = SendingService(
    dsn=RABBIT_DSN,
    log_to=send_logger,
)


def sql_history(target_model: object, event_type: str, pk: int, change: str):
    """
    We now do not send the event_time.  Hermes adds this using
    send message added utc_adjusted payload parameter to account for server time variations
    """
    try:
        sh = SharedData()
        if sh is not None:
            manager = getattr(target_model, "_sa_class_manager")
            if manager.is_mapped:
                table = manager.mapper.local_table.fullname
            else:
                table = str(target_model)
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


def process_mapper_attributes(target: object, attr: str, payload: dict, related: dict) -> None:
    if isinstance(attr, ColumnProperty):
        name = attr.key
        value = getattr(target, name)
        if isinstance(value, (str, float, int, str, bool, type(None))):
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


def mapper_history(target: object, event_type: EventType, mapped: mapper) -> Optional[HistoryData]:
    """
    We now do not send the event_time.  Hermes adds this using
    send message added utc_adjusted payload parameter to account for server time variations

    """
    try:
        sh = SharedData()
        if sh is not None:
            auth_data = sh.request.context.auth_instance.auth_data
            table = mapped.mapped_table
            payload = {}
            related = {}
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


def send_message_to_hermes(path: str, payload: Dict, add_headers=None) -> None:
    payload["utc_adjusted"] = arrow.utcnow().shift(microseconds=-100000).isoformat()
    msg_data = create_message_data(payload, path, add_headers)
    _send_message(**msg_data)
    send_logger.info(f"SENT: {path}")


def create_message_data(payload: Any, path: str = None, base_headers=None) -> Dict[str, Any]:
    if base_headers is None:
        base_headers = {}

    headers = {
        "X-http-path": path,
        "X-epoch-timestamp": time(),
        "X-version": "1.0",
        "X-content-type": "application/json",
        **base_headers,
    }

    return {
        "payload": json.dumps(payload),
        "headers": headers,
        "queue_name": TO_HERMES_QUEUE,
    }


def _send_message(**kwargs) -> None:
    """
    :param kwargs:
    :key payload: Any
    :key headers: Dict[str,Any]
    :key queue_name: str
    """
    payload = kwargs.get("payload")
    headers = kwargs.get("headers")
    queue_name = kwargs.get("queue_name")
    message_sender.send(payload, headers, queue_name)
