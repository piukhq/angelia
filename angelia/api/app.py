import falcon
from falcon import media

from angelia.api import middleware
from angelia.api.custom_error_handlers import (
    angelia_bad_request,
    angelia_conflict_error,
    angelia_forbidden,
    angelia_generic_error_handler,
    angelia_internal_server_error,
    angelia_not_found,
    angelia_resource_not_found,
    angelia_unauthorised,
    angelia_validation_error,
)
from angelia.api.exceptions import (
    ResourceNotFoundError,
    ValidationError,
    uncaught_error_handler,
)
from angelia.api.helpers.vault import load_secrets
from angelia.encryption import JweException
from angelia.hermes.db import DB
from angelia.report import api_logger  # noqa: F401
from angelia.resources.urls import INTERNAL_END_POINTS, RESOURCE_END_POINTS


def load_resources(app: falcon.App) -> None:
    for endpoint in (*INTERNAL_END_POINTS, *RESOURCE_END_POINTS):
        endpoint["resource"](app, endpoint["url_prefix"], endpoint["url"], endpoint["kwargs"], DB())


def create_app() -> falcon.App:
    app = falcon.App(
        media_type=falcon.MEDIA_JSON,
        middleware=[
            middleware.AzureRefMiddleware(),
            middleware.MetricMiddleware(),
            middleware.SharedDataMiddleware(),
            middleware.DatabaseSessionManager(),
            middleware.AuthenticationMiddleware(),
            middleware.FailureEventMiddleware(),
        ],
    )
    app.add_error_handler(Exception, uncaught_error_handler)
    app.add_error_handler(JweException, angelia_generic_error_handler)
    app.add_error_handler(ValidationError, angelia_validation_error)

    app.add_error_handler(falcon.HTTPInternalServerError, angelia_internal_server_error)
    app.add_error_handler(falcon.HTTPNotFound, angelia_not_found)
    app.add_error_handler(falcon.HTTPBadRequest, angelia_bad_request)
    app.add_error_handler(falcon.HTTPUnauthorized, angelia_unauthorised)
    app.add_error_handler(falcon.HTTPForbidden, angelia_forbidden)
    app.add_error_handler(falcon.HTTPConflict, angelia_conflict_error)
    app.add_error_handler(ResourceNotFoundError, angelia_resource_not_found)

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
