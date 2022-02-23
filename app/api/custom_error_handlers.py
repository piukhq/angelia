import falcon
from falcon.http_error import HTTPError

from app.api.metrics import Metric
from settings import URL_PREFIX


def custom_error(ex, default_slug):
    raise CustomHTTPError(ex.status, set_dict(ex, default_slug))


class CustomHTTPError(HTTPError):
    """Represents a generic HTTP error."""

    def __init__(self, status, error):
        super(CustomHTTPError, self).__init__(status)
        self.status = status
        self.error = error

    def to_dict(self, obj_type=dict):
        """Returns a basic dictionary representing the error."""
        super(CustomHTTPError, self).to_dict(obj_type)
        obj = self.error
        return obj


def set_dict(ex, default_slug):
    err = {"error_message": ex.title}
    if ex.code:
        err["error_slug"] = ex.code
    else:
        err["error_slug"] = default_slug
    return err


class TokenHTTPError(HTTPError):
    """Represents a generic HTTP error."""

    def __init__(self, args):
        super().__init__(args[0])
        self.error = args[1]

    def to_dict(self, obj_type=dict) -> dict:
        """Forces a basic error only dictionary response for OAuth style Token endpoint errors"""
        super().to_dict(dict)
        obj = {"error": self.error}

        metric = Metric(method="POST", status=falcon.HTTP_400, path=URL_PREFIX + "/token")
        metric.route_metric()

        return obj


# For angelia custom errors raise the mapped falcon response and are not used in app code
# using title for error_message and code for error slug you can fully customise the error response
# which conforms to angelia standard ie
# {
#   "error_message": as title= or uses falcons default message
#   "error_slug": as code= or our use our preset default if not given
# }
# eg raise falcon.HTTPBadRequest(title="Malformed request", code="MALFORMED_REQUEST")
# or raise falcon.HTTPBadRequest(title="Malformed request") uses our default code which is "MALFORMED_REQUEST"
# or raise falcon.HTTPBadRequest() uses default falcon title and our default code
# Use falcon.HTTPError(falcon.http_error) to raise specific error codes is required
# falcon's HTTPUnauthorized, HTTPBadRequest, HTTPNotFound have mapped defaults but other
# falcon errors will reply with 'HTTP_ERROR' unless code is set
# if raised internally by falcon the default code will be used together with falcons title


def angelia_not_found(req, resp, ex, params):
    metric = Metric(request=req, status=ex)
    metric.route_metric()

    custom_error(ex, "NOT_FOUND")


def angelia_unauthorised(req, resp, ex, params):
    metric = Metric(request=req, status=ex)
    metric.route_metric()

    custom_error(ex, "UNAUTHORISED")


def angelia_bad_request(req, resp, ex, params):
    metric = Metric(request=req, status=ex)
    metric.route_metric()

    custom_error(ex, "MALFORMED_REQUEST")


def angelia_validation_error(req, resp, ex, params):
    metric = Metric(request=req, status=ex)
    metric.route_metric()

    raise ex


def angelia_conflict_error(req, resp, ex, params):
    metric = Metric(request=req, status=ex)
    metric.route_metric()

    custom_error(ex, "CONFLICT")


def angelia_resource_not_found(req, resp, ex, params):
    metric = Metric(request=req, status=ex)
    metric.route_metric()

    raise ex


INVALID_REQUEST = "400", "invalid_request"
INVALID_GRANT = "400", "invalid_grant"
UNAUTHORISED_CLIENT = "400", "unauthorized_client"
UNSUPPORTED_GRANT_TYPE = "400", "unsupported_grant_type"
INVALID_CLIENT = "401", "invalid_client"
