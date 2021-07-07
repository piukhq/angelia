import falcon

from app.api import middleware  # noqa
from app.api.exceptions import uncaught_error_handler  # noqa
from app.hermes.db import DB  # noqa
from app.report import api_logger  # noqa
from app.resources.urls import RESOURCE_END_POINTS, INTERNAL_END_POINTS  # noqa
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
    app.add_error_handler(falcon.HTTPError, uncaught_error_handler)
    # app.set_error_serializer(error_serializer)
    load_resources(app)
    return app
