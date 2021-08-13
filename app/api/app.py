import falcon
from falcon import media

from app.api import middleware  # noqa
from app.api.custom_error_handlers import (
    angelia_bad_request,
    angelia_http_error,
    angelia_not_found,
    angelia_unauthorised,
    angelia_validation_error,
)
from app.api.exceptions import ValidationError, uncaught_error_handler  # noqa
from app.api.helpers.vault import load_secrets
from app.hermes.db import DB  # noqa
from app.report import api_logger  # noqa
from app.resources.urls import INTERNAL_END_POINTS, RESOURCE_END_POINTS  # noqa


def load_resources(app) -> None:
    for endpoint in [*INTERNAL_END_POINTS, *RESOURCE_END_POINTS]:
        endpoint["resource"](app, endpoint["url_prefix"], endpoint["url"], endpoint["kwargs"], DB())


def create_app():
    app = falcon.App(
        media_type=falcon.MEDIA_JSON,
        middleware=[
            middleware.MetricMiddleware(),
            middleware.DatabaseSessionManager(),
            middleware.AuthenticationMiddleware(),
        ],
    )
    app.add_error_handler(Exception, uncaught_error_handler)
    app.add_error_handler(falcon.HTTPNotFound, angelia_not_found)
    app.add_error_handler(ValidationError, angelia_validation_error)
    app.add_error_handler(falcon.HTTPBadRequest, angelia_bad_request)
    app.add_error_handler(falcon.HTTPUnauthorized, angelia_unauthorised)
    app.add_error_handler(falcon.HTTPError, angelia_http_error)

    handlers = media.Handlers(
        {
            falcon.MEDIA_JSON: media.JSONHandler(),
        }
    )

    app.req_options.media_handlers = handlers
    app.resp_options.media_handlers = handlers

    load_resources(app)
    load_secrets("all")
    return app
