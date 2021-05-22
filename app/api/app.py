import falcon

from app.api import middleware
from settings import RESOURCE_LIST
from app.report import api_logger
from settings import URL_PREFIX


def load_resources(app) -> None:
    for res in RESOURCE_LIST:
        res(app, URL_PREFIX)


def create_app():
    app = falcon.App(middleware=[
        middleware.MetricMiddleware(),
        middleware.DatabaseSessionManager(),
        middleware.AuthenticationMiddleware(),
    ])
    app.add_error_handler(Exception, uncaught_error_handler)
    load_resources(app)
    return app


def uncaught_error_handler(ex, req, resp, params):
    request_id = req.context.get('request_id')
    api_exc = isinstance(ex, falcon.HTTPError)
    if request_id and api_exc:
        err_msg = f"An exception has occurred for request_id: {request_id} - {repr(ex)}"
        api_logger.exception(err_msg)
        raise ex
    elif not request_id and api_exc:
        err_msg = f"An exception has occurred - {repr(ex)}"
        api_logger.exception(err_msg)
        raise ex
    elif request_id and not api_exc:
        err_msg = f"Unexpected exception has occurred for request_id: {request_id} - {repr(ex)}"
    else:
        err_msg = f"Unexpected exception has occurred - {repr(ex)}"
    api_logger.exception(err_msg)
    raise falcon.HTTPInternalServerError
