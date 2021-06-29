import json
from time import time
from typing import Any, Dict

from app.messaging.message_broker import SendingService
from app.report import send_logger
from settings import RABBIT_USER, RABBIT_PASSWORD, RABBIT_HOST, RABBIT_PORT, TO_HERMES_QUEUE

message_sender = SendingService(
    user=RABBIT_USER,
    password=RABBIT_PASSWORD,
    host=RABBIT_HOST,
    port=RABBIT_PORT,
    log_to=send_logger
)


def send_message_to_hermes(path: str, payload: Dict, add_headers=None) -> None:
    msg_data = create_message_data(payload, path, add_headers)
    _send_message(**msg_data)


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
