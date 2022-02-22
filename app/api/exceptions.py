import falcon

from app.api.metrics import Metric
from app.report import api_logger


def uncaught_error_handler(ex, req, resp, params):
    request_id = req.context.get("request_id")
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
    metric = Metric(req, falcon.HTTP_500)
    metric.route_metric()
    raise falcon.HTTPInternalServerError


def _force_str(s, encoding="utf-8", errors="strict"):
    if issubclass(type(s), str):
        return s

    if isinstance(s, bytes):
        s = str(s, encoding, errors)
    else:
        s = str(s)

    return s


def _get_error_details(data):
    if isinstance(data, list):
        ret = [_get_error_details(item) for item in data]
        return ret
    elif isinstance(data, dict):
        ret = {key: _get_error_details(value) for key, value in data.items()}
        return ret

    return _force_str(data)


class CredentialError(falcon.HTTPUnprocessableEntity):
    def __init__(self, description=None, headers=None, title=None, **kwargs):
        super().__init__(
            title=title or "Credentials provided are not correct",
            code="CARD_CREDENTIALS_INCORRECT",
            description=description,
            headers=headers,
            **kwargs,
        )


class ResourceNotFoundError(falcon.HTTPNotFound):
    """Specific ResourceNotFound error to be used as opposed to standard 404 in case of incorrect or non-existent
    url"""

    def __init__(self, description=None, headers=None, title=None, **kwargs):
        super().__init__(
            title=title or "Could not find this account or card",
            code="RESOURCE_NOT_FOUND",
            description=description,
            headers=headers,
            **kwargs,
        )

    def to_dict(self, obj_type=dict):
        """
        Override to_dict so a ResourceNotFoundError raised with non-hashable objects for the description
        is handled and converted to strings.
        """
        obj = obj_type()

        obj["error_message"] = self.title
        obj["error_slug"] = self.code

        if self.description is not None:
            obj["fields"] = _get_error_details(self.description)

        return obj


class ValidationError(falcon.HTTPUnprocessableEntity):
    def __init__(self, description=None, headers=None, title=None, **kwargs):
        super().__init__(
            title=title or "Could not validate fields",
            code="FIELD_VALIDATION_ERROR",
            description=description,
            headers=headers,
            **kwargs,
        )

    def to_dict(self, obj_type=dict):
        """
        Override to_dict so a ValidationError raised with non-hashable objects for the description
        (E.g voluptuous.MultipleInvalid) is handled and converted to strings.
        """
        obj = obj_type()

        obj["error_message"] = self.title
        obj["error_slug"] = self.code

        if self.description is not None:
            obj["fields"] = _get_error_details(self.description)

        return obj
