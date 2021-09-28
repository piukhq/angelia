from functools import wraps

import falcon
import pydantic
import voluptuous
from voluptuous import PREVENT_EXTRA, All, Any, Invalid, Optional, Required, Schema

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
            api_logger.warning(e.errors)
            raise ValidationError(description=e.errors)
        except voluptuous.Invalid as e:
            api_logger.warning(e.error_message)
            raise ValidationError(description=e.error_message)
        except AssertionError:
            api_logger.exception(err_msg)
            raise falcon.HTTPInternalServerError(title="Request data failed validation")


def _validate_resp_schema(resp_schema, resp):
    if resp_schema is not None:
        try:
            resp.media = resp_schema(**resp.media).dict(exclude_none=True)
            return resp.media
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
    if len(credentials["add_fields"]["credentials"]) != 1:
        api_logger.warning("Must provide exactly one 'add_fields' credential")
        raise Invalid("Must provide exactly one `add_fields` credential")
    return credentials


def must_provide_at_least_one_field(fields):
    if len(fields) < 1:
        api_logger.warning("No fields provided")
        raise Invalid("Must provide at least a single field")
    return fields


credential_field_schema = Schema({"credential_slug": str, "value": Any(str, int, bool, float)}, required=True)

consent_field_schema = Schema({"consent_slug": str, "value": Any(str)}, required=True)

loyalty_card_field_schema_with_consents = Schema(
    All({Required("credentials"): [credential_field_schema], Optional("consents"): [consent_field_schema]})
)

loyalty_card_field_schema_no_consents = Schema(All({Required("credentials"): [credential_field_schema]}))

loyalty_card_add_account_schema = Schema(
    All(
        {
            Required("add_fields"): loyalty_card_field_schema_no_consents,
        },
        must_provide_single_add_field,
    ),
    extra=PREVENT_EXTRA,
)

loyalty_card_add_schema = Schema({"loyalty_plan_id": int, "account": loyalty_card_add_account_schema}, required=True)


loyalty_card_add_and_auth_account_schema = Schema(
    All(
        {
            Optional("add_fields"): loyalty_card_field_schema_with_consents,
            Required("authorise_fields"): loyalty_card_field_schema_with_consents,
            # We allow Add fields to be optional here for the sake of Harvey Nichols, who don't have any add fields
            # so use auth fields as the key identifier instead.
        },
        must_provide_add_or_auth_fields,
    ),
    extra=PREVENT_EXTRA,
)

loyalty_card_add_and_auth_schema = Schema(
    {"loyalty_plan_id": int, "account": loyalty_card_add_and_auth_account_schema}, required=True
)

loyalty_card_add_and_register_account_schema = Schema(
    All(
        {
            Required("add_fields"): loyalty_card_field_schema_with_consents,
            Required("register_ghost_card_fields"): loyalty_card_field_schema_with_consents,
        },
        must_provide_single_add_field,
    ),
    extra=PREVENT_EXTRA,
)

loyalty_card_authorise_account_schema = Schema(
    All(
        {
            Required("authorise_fields"): loyalty_card_field_schema_with_consents,
        },
    ),
    extra=PREVENT_EXTRA,
)

loyalty_card_add_and_register_schema = Schema(
    {"loyalty_plan_id": int, "account": loyalty_card_add_and_register_account_schema}, required=True
)

loyalty_card_authorise_schema = Schema({"account": loyalty_card_authorise_account_schema}, required=True)


payment_accounts_add_schema = Schema(
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
    extra=PREVENT_EXTRA,
)


payment_accounts_update_schema = Schema(
    All(
        {
            Optional("expiry_month"): str,
            Optional("expiry_year"): str,
            Optional("name_on_card"): str,
            Optional("card_nickname"): str,
            Optional("issuer"): str,
        },
        must_provide_at_least_one_field,
    ),
    extra=PREVENT_EXTRA,
)
