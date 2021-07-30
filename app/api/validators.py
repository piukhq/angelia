from functools import wraps

import falcon
import pydantic
import voluptuous
from voluptuous import REMOVE_EXTRA, PREVENT_EXTRA, All, Any, Invalid, Optional, Required, Schema

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


def _validate_req_schema(req_schema, req):
    if req_schema is not None:
        err_msg = "Expected input_validator of type voluptuous.Schema"
        try:
            assert isinstance(req_schema, voluptuous.Schema), err_msg
            req_schema(req.media)
        except voluptuous.MultipleInvalid as e:
            api_logger.error(e.errors)
            raise ValidationError(description=e.errors)
        except voluptuous.Invalid as e:
            api_logger.error(e.error_message)
            raise ValidationError(description=e.error_message)
        except AssertionError:
            api_logger.exception(err_msg)
            raise falcon.HTTPInternalServerError(title="Request data failed validation")


def _validate_resp_schema(resp_schema, resp):
    if resp_schema is not None:
        try:
            resp.media = resp_schema(**resp.media).dict()
            return resp.media
        except pydantic.ValidationError:
            raise falcon.HTTPInternalServerError(
                title="Response data failed validation"
                # Do not return 'e.message' in the response to
                # prevent info about possible internal response
                # formatting bugs from leaking out to users.
            )
        except TypeError:
            api_logger.exception("Invalid response schema - schema must be a subclass of pydantic.BaseModel")
            raise falcon.HTTPInternalServerError(title="Response data failed validation")


def _validate(func, req_schema=None, resp_schema=None):
    @wraps(func)
    def wrapper(self, req, resp, *args, **kwargs):
        _validate_req_schema(req_schema, req)
        result = func(self, req, resp, *args, **kwargs)
        _validate_resp_schema(resp_schema, resp)
        return result

    return wrapper


def must_provide_add_or_auth_fields(credentials):
    if not (credentials.get("add_fields") or credentials.get("authorise_fields")):
        raise Invalid("Must provide `add_fields` or `authorise_fields`")
    return credentials


def must_provide_single_add_field(credentials):
    if len(credentials["add_fields"]) != 1:
        api_logger.error("Must provide exactly one 'add_fields' credential")
        raise Invalid("Must provide exactly one `add_fields` credential")
    return credentials


credential_field_schema = Schema({"credential_slug": str, "value": Any(str, int, bool, float)}, required=True)


loyalty_card_add_account_schema = Schema(All(
        {
            "add_fields": Required([credential_field_schema]),
        },
        must_provide_single_add_field),
        extra=PREVENT_EXTRA,
)

loyalty_card_add_schema = Schema({"loyalty_plan": int, "account": loyalty_card_add_account_schema}, required=True)

loyalty_card_add_and_auth_account_schema = Schema(
    All(
        {
            "add_fields": Optional([credential_field_schema]),
            "authorise_fields": Optional([credential_field_schema]),
        },
        must_provide_add_or_auth_fields,
    ),
    extra=REMOVE_EXTRA,
)

loyalty_card_add_and_auth_schema = Schema({"loyalty_plan": int, "account": loyalty_card_add_and_auth_account_schema},
                                          required=True
                                          )


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
