import falcon

from app.api import middleware  # noqa
from app.api.custom_error_handlers import (
    angelia_bad_request,
    angelia_http_error,
    angelia_not_found,
    angelia_unauthorised,
)
from app.api.exceptions import uncaught_error_handler  # noqa
from app.hermes.db import DB  # noqa
from app.report import api_logger  # noqa
from app.resources.urls import INTERNAL_END_POINTS, RESOURCE_END_POINTS  # noqa
from settings import URL_PREFIX


def load_resources(app) -> None:
    for url, res in INTERNAL_END_POINTS.items():
        res(app, "", url, DB())

    for url, res in RESOURCE_END_POINTS.items():
        res(app, URL_PREFIX, url, DB())


def create_app():
    app = falcon.App(
        middleware=[
            middleware.MetricMiddleware(),
            middleware.DatabaseSessionManager(),
            middleware.AuthenticationMiddleware(),
        ]
    )
    app.add_error_handler(Exception, uncaught_error_handler)
    app.add_error_handler(falcon.HTTPNotFound, angelia_not_found)
    app.add_error_handler(falcon.HTTPBadRequest, angelia_bad_request)
    app.add_error_handler(falcon.HTTPUnauthorized, angelia_unauthorised)
    app.add_error_handler(falcon.HTTPError, angelia_http_error)
    # app.set_error_serializer(error_serializer)
    load_resources(app)
    return app
