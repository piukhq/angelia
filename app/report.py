import logging
import sys
import threading
import uuid
from copy import deepcopy
from functools import wraps
from typing import TYPE_CHECKING, Any

import falcon
from gunicorn.glogging import Logger as GLogger
from pythonjsonlogger import jsonlogger

from app.api.filter import hide_fields
from settings import DEFAULT_LOG_FORMAT, JSON_LOGGING, LOG_FORMAT, LOG_LEVEL

if TYPE_CHECKING:
    from collections.abc import Callable
    from logging import LogRecord

    from falcon import Request, Response


class HealthzAndMetricsFilter(logging.Filter):
    def filter(self, record: "LogRecord") -> bool:
        message = record.getMessage()
        return not any(match in message for match in ("/livez", "/readyz", "/metrics"))


class CustomFormatter(logging.Formatter):
    @staticmethod
    def _format(record: "LogRecord") -> str:
        log_items = DEFAULT_LOG_FORMAT.split(" | ")

        for name, val, index in (("request_id", ctx.request_id, 3), ("user_id", ctx.user_id, 4)):
            if val:
                setattr(record, name, val)
                log_item = f"{name} - %({name})s"
                log_items.insert(index, log_item)

        return " | ".join(log_items)

    def format(self, record: "LogRecord") -> str:
        self._style._fmt = self._format(record)
        return super(CustomFormatter, self).format(record)


class CustomJsonFormatter(CustomFormatter, jsonlogger.JsonFormatter):
    pass


class CustomGunicornFormatter(GLogger, jsonlogger.JsonFormatter):
    pass


class _Context:
    """Used for storing context data for logging purposes"""

    def __init__(self) -> None:
        self._thread_local = threading.local()

    @property
    def request_id(self) -> str | None:
        return getattr(self._thread_local, "request_id", None)

    @request_id.setter
    def request_id(self, value: str) -> None:
        self._thread_local.request_id = value

    @property
    def user_id(self) -> int | None:
        return getattr(self._thread_local, "user_id", None)

    @user_id.setter
    def user_id(self, value: int) -> None:
        self._thread_local.user_id = value


def get_json_handler() -> logging.StreamHandler:
    json_handler = logging.StreamHandler(sys.stdout)
    json_handler.setFormatter(CustomJsonFormatter(LOG_FORMAT))
    return json_handler


def get_console_handler() -> logging.StreamHandler:
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(CustomFormatter(LOG_FORMAT))
    return console_handler


def get_logger(logger_name: str, *, log_level: int = LOG_LEVEL) -> logging.Logger:
    logger = logging.getLogger(logger_name)
    logger.setLevel(log_level)
    if JSON_LOGGING:
        logger.addHandler(get_json_handler())
    else:
        logger.addHandler(get_console_handler())
    logger.propagate = False
    return logger


def log_request_data(func: "Callable") -> "Callable":
    """
    Decorator function to log request and response information if logger is set to DEBUG.
    :param func: a falcon view to decorate
    :return: None
    """

    def _format_req_for_logging(req: "Request") -> dict:
        # Deep copies used so any manipulation of data used for logging e.g filtering of fields
        # does not affect the original objects.
        media = hide_fields(deepcopy(req.media), {"account.authorise_fields"})
        headers = hide_fields(deepcopy(req.headers), {"AUTHORIZATION"})
        context = hide_fields(
            deepcopy({key: val for key, val in dict(req.context).items() if key != "db_session"}),
            {"decrypted_media.account.authorise_fields"},
        )

        auth_instance = context.pop("auth_instance", None)
        if auth_instance:
            context.update({"auth": getattr(auth_instance, "auth_data", "No auth data")})

        return {
            "context": context,
            "media": media,
            "headers": headers,
        }

    def _format_resp_for_logging(resp: "Response") -> dict:
        return {
            "context": dict(resp.context),
            "media": resp.media,
            "status": resp.status,
        }

    @wraps(func)
    def _request_logger(*args: Any, **kwargs: Any) -> None:
        req = None
        resp = None
        for arg in args:
            if isinstance(arg, falcon.Request):
                req = arg
                continue
            elif isinstance(arg, falcon.Response):
                resp = arg

        if not (req and resp):
            raise ValueError("Decorated function must contain falcon.Request and falcon.Response arguments")

        request_id = str(uuid.uuid4())
        req.context.request_id = resp.context.request_id = ctx.request_id = request_id

        # Improve performance by bypassing request/response logging when not in debug mode
        if api_logger.getEffectiveLevel() != logging.DEBUG:
            func(*args, **kwargs)
            return

        api_logger.debug(f"Request to {func.__qualname__}")
        try:
            func(*args, **kwargs)
            resp_log = _format_resp_for_logging(resp)
            api_logger.debug(f"Response from {func.__qualname__} - {resp_log}")
        except Exception as e:
            api_logger.exception(f"Response from {func.__qualname__} - Error {repr(e)}")
            raise

    return _request_logger


ctx = _Context()


# Sets up the root logger with our custom handlers/formatters.
get_logger("")

# Sets libraries log level to WARN to avoid non releavant log spam
get_logger("azure", log_level=logging.WARNING)
get_logger("urllib3", log_level=logging.WARNING)

# Filters out /metrics /livez and /readyz info logs
gunicorn_logger = logging.getLogger("gunicorn.access")
gunicorn_logger.addFilter(HealthzAndMetricsFilter())

# Sets up the amqp logger with our custom handlers/formatters.
get_logger("amqp")

api_logger = get_logger("angelia_api")
send_logger = get_logger("angelia_api_send")
retry_logger = get_logger("angelia_retry")
history_logger = get_logger("angelia_history_logger")
sql_logger = get_logger("angelia_sqltime")
