from falcon.http_error import HTTPError


def custom_error(ex, default_slug):
    raise CustomHTTPError(ex.status, set_dict(ex, default_slug))


class CustomHTTPError(HTTPError):

    """Represents a generic HTTP error.
    """

    def __init__(self, status, error):
        super(CustomHTTPError, self).__init__(status)
        self.status = status
        self.error = error

    def to_dict(self, obj_type=dict):
        """Returns a basic dictionary representing the error.
        """
        super(CustomHTTPError, self).to_dict(obj_type)
        obj = self.error
        return obj


def set_dict(ex, default_slug):
    err = {'error_message': ex.title}
    if ex.code:
        err['error_slug'] = ex.code
    else:
        err['error_slug'] = default_slug
    return err


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
    # TODO: Log the error
    custom_error(ex, 'NOT_FOUND')


def angelia_unauthorised(req, resp, ex, params):
    # TODO: Log the error
    custom_error(ex, 'UNAUTHORISED')


def angelia_bad_request(req, resp, ex, params):
    # TODO: Log the error
    custom_error(ex, 'MALFORMED_REQUEST')


def angelia_http_error(req, resp, ex, params):
    # TODO: Log the error
    custom_error(ex, 'HTTP_ERROR')
