import json
from datetime import datetime
from time import time
from typing import Any, Dict
from uuid import UUID

from sqlalchemy.orm import mapper

from app.api.shared_data import SharedData
from app.messaging.message_broker import SendingService
from app.report import history_logger, send_logger
from settings import RABBIT_DSN, TO_HERMES_QUEUE

message_sender = SendingService(
    dsn=RABBIT_DSN,
    log_to=send_logger,
)


def sql_history(target_model: object, event_type: str, pk: int, change: str):
    try:
        sh = SharedData()
        if sh is not None:
            manager = getattr(target_model, "_sa_class_manager")
            if manager.is_mapped:
                table = manager.mapper.local_table.fullname
            else:
                table = str(target_model)
            auth_data = sh.request.context.auth_instance.auth_data
            dt = datetime.utcnow()  # current date and time
            date_time = dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            history_data = {
                "user": auth_data.get("sub"),
                "channel": auth_data.get("channel"),
                "event": event_type,
                "event_date": date_time,
                "table": str(table),
                "change": change,
                "id": pk,
            }
            send_message_to_hermes("sql_history", history_data)
    except Exception as e:
        # Best allow an exception as it would prevent the data being written
        history_logger.error(f"Trapped Exception Lost sql history report due to {e}")


def mapper_history(target: object, event_type: str, mapped: mapper):
    try:
        sh = SharedData()
        if sh is not None:
            auth_data = sh.request.context.auth_instance.auth_data
            dt = datetime.utcnow()  # current date and time
            date_time = dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            table = mapped.mapped_table

            payload = {}
            for attr in dir(target):
                if attr[0] != "_":
                    value = getattr(target, attr)
                    if isinstance(value, (str, float, int, str, bool, type(None))):
                        payload[attr] = value
                    elif isinstance(value, (UUID,)):
                        payload[attr] = str(value)
                    elif isinstance(value, (datetime,)):
                        payload[attr] = value.strftime("%Y-%m-%dT%H:%M:%S.%f%z")

            hermes_history_data = {
                "user": auth_data.get("sub"),
                "channel": auth_data.get("channel"),
                "event": event_type,
                "event_date": date_time,
                "table": str(table),
                "change": None,
                "payload": payload,
            }
            send_message_to_hermes("mapped_history", hermes_history_data)
    except Exception as e:
        # Best allow an exception as it would prevent the data being written
        history_logger.error(f"Trapped Exception Lost mapper history report due to {e}")


def send_message_to_hermes(path: str, payload: Dict, add_headers=None) -> None:
    msg_data = create_message_data(payload, path, add_headers)
    _send_message(**msg_data)
    send_logger.info(f"SENT: {path}: " + str(payload))


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
