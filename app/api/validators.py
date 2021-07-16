from functools import wraps

import falcon
import pydantic
import voluptuous
from voluptuous import REMOVE_EXTRA, All, Any, Invalid, Optional, Required, Schema

from app.api.exceptions import ValidationError
from app.report import api_logger


def validate(req_schema=None, resp_schema=None):
    """
    Decorator function to validate input and serialize output for resources.
    This can be used per resource function such as on_post, on_get, on_put etc.

    req_schema: An instance of a voluptuous schema
    resp_schema: A pydantic serializer class subclassing pydantic.BaseModel
    """

    def decorator(func):
        return _validate(func, req_schema, resp_schema)

    return decorator


def _validate(func, req_schema=None, resp_schema=None):
    @wraps(func)
    def wrapper(self, req, resp, *args, **kwargs):
        if req_schema is not None:
            err_msg = "Expected input_validator of type voluptuous.Schema"
            try:
                assert isinstance(req_schema, voluptuous.Schema), err_msg
                req_schema(req.media)
            except voluptuous.MultipleInvalid as e:
                raise ValidationError(description=e.errors)
            except AssertionError:
                api_logger.exception(err_msg)
                raise falcon.HTTPInternalServerError(title="Request data failed validation")

        result = func(self, req, resp, *args, **kwargs)

        if resp_schema is not None:
            try:
                resp.media = resp_schema(**resp.media).dict()
            except pydantic.ValidationError:
                api_logger.exception("Error validating response data")
                raise falcon.HTTPInternalServerError(
                    title="Response data failed validation"
                    # Do not return 'e.message' in the response to
                    # prevent info about possible internal response
                    # formatting bugs from leaking out to users.
                )
            except TypeError:
                api_logger.exception("Invalid response schema - schema must be a subclass of pydantic.BaseModel")
                raise falcon.HTTPInternalServerError(title="Response data failed validation")

        return result

    return wrapper


def must_provide_add_or_auth_fields(credentials):
    if not (credentials.get("add_fields") or credentials.get("authorise_fields")):
        raise Invalid("Must provide `add_fields` or `authorise_fields`")
    return credentials


credential_field_schema = Schema({"credential_slug": str, "value": Any(str, int, bool, float)}, required=True)


loyalty_add_account_schema = Schema(
    All(
        {
            "add_fields": Optional([credential_field_schema]),
            "authorise_fields": Optional([credential_field_schema]),
        },
        must_provide_add_or_auth_fields,
    ),
    extra=REMOVE_EXTRA,
)


loyalty_cards_adds_schema = Schema({"loyalty_plan": int, "account": loyalty_add_account_schema}, required=True)


payment_accounts_schema = Schema(
    {
        Required("expiry_month"): str,
        Required("expiry_year"): str,
        Optional("name_on_card"): str,
        Optional("card_nickname"): str,
        Optional("issuer"): str,
        Required("token"): str,
        Required("last_four_digits"): str,
        Required("first_six_digits"): str,
        Required("fingerprint"): str,
        Optional("provider"): str,
        Optional("type"): str,
        Optional("country"): str,
        Optional("currency_code"): str,
    },
    extra=REMOVE_EXTRA,
)
