import logging
import sys
import uuid
from copy import deepcopy
from functools import wraps

import falcon
from pythonjsonlogger import jsonlogger

from app.api.filter import hide_fields
from settings import LOG_LEVEL, LOG_FORMAT, JSON_LOGGING


class HealthZFilter(logging.Filter):
    def filter(self, record):
        return not record.getMessage().endswith('"GET /healthz HTTP/1.1" 200 -')


# class CustomFormatter(logging.Formatter):
#     def format(self, record):
#         return super(CustomFormatter, self).format(record)

def get_json_handler():
    json_handler = logging.StreamHandler(sys.stdout)
    json_handler.setFormatter(json_formatter)
    return json_handler


def get_console_handler():
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    return console_handler


def get_logger(logger_name):
    logger = logging.getLogger(logger_name)
    logger.setLevel(LOG_LEVEL)
    if JSON_LOGGING:
        logger.addHandler(get_json_handler())
    else:
        logger.addHandler(get_console_handler())
    logger.propagate = False
    return logger


def log_request_data(func):
    """
    Decorator function to log request and response information if logger is set to DEBUG.
    :param func: a falcon view to decorate
    :return: None
    """
    def _format_req_for_logging(req):
        # Deep copies used so any manipulation of data used for logging e.g filtering of fields
        # does not affect the original objects.
        media = hide_fields(deepcopy(req.media), {'account.authorise_fields'})
        headers = hide_fields(deepcopy(req.headers), {'AUTHORIZATION'})
        context = deepcopy({key: val for key, val in dict(req.context).items() if key != 'db_session'})

        # Extract non-sensitive auth data from the context for logging.
        service = req.context.auth.service
        context_auth_data = {
            "user_id": req.context.auth.user_id,
            "bundle_id": req.context.auth.bundle_id,
            "service": service.id if service else None
        }
        context.update({"auth": context_auth_data})
        return {
            "context": context,
            "media": media,
            "headers": headers,
        }

    def _format_resp_for_logging(resp):
        return {
            "context": dict(resp.context),
            "media": resp.media,
            "status": resp.status
        }

    @wraps(func)
    def _request_logger(*args, **kwargs):
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
        req.context.request_id = resp.context.request_id = request_id

        # Improve performance by bypassing request/response logging when not in debug mode
        if api_logger.getEffectiveLevel() != logging.DEBUG:
            func(*args, **kwargs)
            return

        req_log = _format_req_for_logging(req)
        api_logger.debug(f"Request to {func.__qualname__} - {req_log}")
        try:
            func(*args, **kwargs)
            resp_log = _format_resp_for_logging(resp)
            api_logger.debug(f"Response from {func.__qualname__} - {resp_log}")
        except Exception as e:
            api_logger.exception(f"Response from {func.__qualname__} - Error {repr(e)}")
            raise
    return _request_logger


json_formatter = jsonlogger.JsonFormatter(LOG_FORMAT)

# Sets up the root logger with our custom handlers/formatters.
logging.getLogger().setLevel(LOG_LEVEL)
get_logger('')

werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.addFilter(HealthZFilter())

api_logger = get_logger('daedalus_api')
consumer_logger = get_logger('daedalus_consumer')
dispatch_logger = get_logger('daedalus_dispatch')
updater_logger = get_logger('daedalus_updater')
retry_logger = get_logger('daedalus_retry')
