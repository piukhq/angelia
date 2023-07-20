import logging
import threading
import uuid
from copy import deepcopy
from functools import wraps
from typing import TYPE_CHECKING, Any

import falcon
from bink_logging_utils import init_loguru_root_sink
from bink_logging_utils.gunicorn import gunicorn_logger_factory
from bink_logging_utils.handlers import loguru_intercept_handler_factory
from loguru import logger

from app.api.filter import hide_fields
from settings import JSON_LOGGING, LOG_FORMAT, LOG_LEVEL

if TYPE_CHECKING:
    from collections.abc import Callable

    from falcon import Request, Response
    from loguru import Record


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


def log_request_data(func: "Callable") -> "Callable":  # noqa: C901
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
        if LOG_LEVEL != logging.DEBUG:
            func(*args, **kwargs)
            return

        api_logger.debug(f"Request to {func.__qualname__}")
        try:
            func(*args, **kwargs)
            resp_log = _format_resp_for_logging(resp)
            api_logger.debug(f"Response from {func.__qualname__} - {resp_log}")
        except Exception as e:
            api_logger.exception(f"Response from {func.__qualname__} - Error {e!r}")
            raise

    return _request_logger


ctx = _Context()


InterceptHandler = loguru_intercept_handler_factory()
CustomGunicornLogger = gunicorn_logger_factory(intercept_handler_class=InterceptHandler)


def generate_format(record: "Record") -> str:
    """Adds user_id and request_id to the log if they have a context value"""
    fmt = LOG_FORMAT
    if ctx.request_id or ctx.user_id:
        log_items = LOG_FORMAT.rsplit(" | ", 2)
        for name, val in (("user_id", ctx.user_id), ("request_id", ctx.request_id)):
            if val:
                record["extra"][name] = val
                log_item = "{name} - {{extra[{name}]}}".format(name=name)
                log_items.insert(1, log_item)

        fmt = " | ".join(log_items)

    return fmt + "\n"


init_loguru_root_sink(
    json_logging=JSON_LOGGING, sink_log_level=LOG_LEVEL, show_pid=False, custom_formatter=generate_format
)

logger.configure(extra={"logger_type": "root"})
# funnels all logs into loguru
logging.basicConfig(handlers=[InterceptHandler()])


api_logger = logger.bind(logger_type="angelia_api")
send_logger = logger.bind(logger_type="angelia_api_send")
retry_logger = logger.bind(logger_type="angelia_retry")
history_logger = logger.bind(logger_type="angelia_history_logger")
sql_logger = logger.bind(logger_type="angelia_sqltime")
