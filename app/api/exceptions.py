from collections.abc import Callable
from typing import Any

import falcon

from app.api.metrics import Metric
from app.report import api_logger


def uncaught_error_handler(ex: type[Exception], req: falcon.Request, resp: falcon.Response, params: dict) -> None:
    request_id = req.context.get("request_id")
    api_exc = isinstance(ex, falcon.HTTPError)
    if request_id and api_exc:
        err_msg = f"An exception has occurred for request_id: {request_id} - {type(ex)}"
        api_logger.exception(err_msg, exc_info=False)
        raise ex
    elif not request_id and api_exc:
        err_msg = f"An exception has occurred - {type(ex)}"
        api_logger.exception(err_msg, exc_info=False)
        raise ex
    elif request_id and not api_exc:
        err_msg = f"Unexpected exception has occurred for request_id: {request_id} - {type(ex)}"
    else:
        err_msg = f"Unexpected exception has occurred - {type(ex)}"
    api_logger.exception(err_msg, exc_info=False)
    metric = Metric(req, falcon.HTTP_500)
    metric.route_metric()
    raise falcon.HTTPInternalServerError


def _force_str(s: Any, encoding: str = "utf-8", errors: str = "strict") -> str:
    if issubclass(type(s), str):
        return s

    s = str(s, encoding, errors) if isinstance(s, bytes) else str(s)

    return s


def _get_error_details(data: list[dict] | dict[str, dict]) -> list | dict | str:
    if isinstance(data, list):
        return [_get_error_details(item) for item in data]

    elif isinstance(data, dict):
        return {key: _get_error_details(value) for key, value in data.items()}

    return _force_str(data)


class CredentialError(falcon.HTTPUnprocessableEntity):
    def __init__(
        self, description: str | None = None, headers: dict | None = None, title: str | None = None, **kwargs: Any
    ) -> None:
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

    def __init__(
        self, description: str | None = None, headers: dict | None = None, title: str | None = None, **kwargs: Any
    ) -> None:
        super().__init__(
            title=title or "Could not find this account or card",
            code="RESOURCE_NOT_FOUND",
            description=description,
            headers=headers,
            **kwargs,
        )

    def to_dict(self, obj_type: "Callable[..., dict]" = dict) -> dict:
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
    def __init__(
        self, description: str | None = None, headers: dict | None = None, title: str | None = None, **kwargs: Any
    ) -> None:
        super().__init__(
            title=title or "Could not validate fields",
            code="FIELD_VALIDATION_ERROR",
            description=description,
            headers=headers,
            **kwargs,
        )

    def to_dict(self, obj_type: "Callable[..., dict]" = dict) -> dict:
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
