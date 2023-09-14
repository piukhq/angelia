import json
from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING

import falcon
import pydantic
from voluptuous import (
    PREVENT_EXTRA,
    All,
    Any,
    Email,
    Invalid,
    Match,
    MatchInvalid,
    MultipleInvalid,
    Optional,
    Replace,
    Required,
    Schema,
    message,
)

from app.api.exceptions import ValidationError
from app.report import api_logger

if TYPE_CHECKING:  # pragma: no cover
    from typing import TypeVar

    from pydantic import BaseModel

    PydanticModelType = type[BaseModel]

    ResType = TypeVar("ResType")
    SameValType = TypeVar("SameValType")


class StripWhitespaceMatch(Match):
    """
    Custom Match class to strip whitespace before matching expression.

    NOTE: Falcon does not allow mutating the data in Request.media. So make sure that the output when validating
    is being set to a variable that is used instead of request.media or request.get_media().

    This is currently being set to request.context.validated_media in _validate_req_schema
    """

    INVALID = "Invalid value"

    def __init__(self, pattern: str, msg: str | None = None) -> None:
        super().__init__(pattern, msg)
        self.msg = StripWhitespaceMatch.INVALID

    def __call__(self, v: str) -> str:
        try:
            v = v.strip()
            match = self.pattern.match(v)
        except (TypeError, AttributeError):
            raise MatchInvalid("expected string or buffer") from None
        if not match:
            raise MatchInvalid(self.msg or "does not match regular expression")
        return v


class DictKeyReplace(Replace):
    """Replaces the value of a key.

    The original Replace validator doesn't work when a key is also required so the replace needs
    to be done on the entire dictionary value rather than specifically on a key. (Or at least I wasn't
    able to figure out how)
    """

    def __call__(self, v: dict) -> dict:
        return json.loads(self.pattern.sub(self.substitution, str(v).replace("'", '"')))


# Todo: remove when implementing regex pattern validation
# ###############################################################
class NotEmptyInvalid(Invalid):
    """The value is empty or null"""


@message("expected a non-empty value", cls=NotEmptyInvalid)
def NotEmpty(v: "SameValType") -> "SameValType":  # noqa: N802
    if not v:
        raise NotEmptyInvalid("Empty value")

    return v


# ###############################################################


def validate(req_schema: Schema | None = None, resp_schema: "PydanticModelType | None" = None) -> Callable:
    """
    Decorator function to validate input and serialize output for resources.
    This can be used per resource function such as on_post, on_get, on_put etc.

    req_schema: An instance of a voluptuous schema
    resp_schema: A pydantic serializer class subclassing pydantic.BaseModel
    """

    def decorator(func: "Callable[..., ResType]") -> "Callable[..., ResType]":
        return _validate(func, req_schema, resp_schema)

    return decorator


def _validate_req_schema(req_schema: Schema | None, req: falcon.Request) -> None:
    if req_schema is not None:
        err_msg = "Expected input_validator of type Schema"
        try:
            assert isinstance(req_schema, Schema), err_msg

            if getattr(req.context, "decrypted_media", None):
                req.context.validated_media = req_schema(req.context.decrypted_media)
            else:
                media = req.get_media(default_when_empty=None)
                req.context.validated_media = req_schema(media)
        except MultipleInvalid as e:
            api_logger.warning(e.errors)
            raise ValidationError(description=e.errors) from None
        except Invalid as e:
            api_logger.warning(e.error_message)
            raise ValidationError(description=e.error_message) from None
        except AssertionError:
            api_logger.exception(err_msg)
            raise falcon.HTTPInternalServerError(title="Request data failed validation") from None


def _validate_resp_schema(resp_schema: "PydanticModelType | None", resp: falcon.Response) -> None:
    if resp_schema is not None:
        try:
            if isinstance(resp.media, dict):
                resp.media = resp_schema(**resp.media).dict()
            elif isinstance(resp.media, list):
                resp.media = [resp_schema(**media).dict() for media in resp.media]
            else:
                err_msg = "Response must be a dict or list object to be validated by the response schema"
                api_logger.debug(f"{err_msg} - response: {resp.media}")
                raise pydantic.ValidationError(err_msg, model=resp_schema)
        except pydantic.ValidationError:
            api_logger.exception("Error validating response data")
            raise falcon.HTTPInternalServerError(
                title="Response data failed validation"
                # Do not return 'e.message' in the response to
                # prevent info about possible internal response
                # formatting bugs from leaking out to users.
            ) from None
        except TypeError:
            api_logger.exception("Invalid response schema - schema must be a subclass of pydantic.BaseModel")
            raise falcon.HTTPInternalServerError(title="Response data failed validation") from None


def _validate(
    func: "Callable[..., ResType]", req_schema: Schema | None = None, resp_schema: "PydanticModelType | None" = None
) -> "Callable[..., ResType]":
    @wraps(func)
    def wrapper(self: Any, req: falcon.Request, resp: falcon.Response, *args: Any, **kwargs: Any) -> "ResType":
        _validate_req_schema(req_schema, req)
        result = func(self, req, resp, *args, **kwargs)
        _validate_resp_schema(resp_schema, resp)
        return result

    return wrapper


def must_provide_add_or_auth_fields(credentials: dict) -> dict:
    if not (credentials.get("add_fields") or credentials.get("authorise_fields")):
        raise Invalid("Must provide `add_fields` or `authorise_fields`")
    return credentials


def must_provide_single_add_field(credentials: dict) -> dict:
    if len(credentials["add_fields"]["credentials"]) != 1:
        api_logger.warning("Must provide exactly one 'add_fields' credential")
        raise Invalid("Must provide exactly one `add_fields` credential")
    return credentials


def must_provide_single_add_or_auth_field(credentials: dict) -> dict:
    add_fields = credentials.get("add_fields", {})
    auth_fields = credentials.get("authorise_fields", {})

    if len(add_fields.get("credentials", [])) + len(auth_fields.get("credentials", [])) != 1:
        api_logger.warning("Must provide exactly one 'add_fields' or 'authorise_fields' credential")
        raise Invalid("Must provide exactly one `add_fields` or 'authorise_fields' credential")

    return credentials


def must_provide_at_least_one_field(fields: dict) -> dict:
    if len(fields) < 1:
        api_logger.warning("No fields provided")
        raise Invalid("Must provide at least a single field")
    return fields


def email_must_be_passed(fields: dict) -> dict:
    if not fields:
        api_logger.warning("No body provided")
        raise Invalid("Missing required 'email' field in request body.")

    return fields


empty_schema = Schema(None, extra=PREVENT_EXTRA)

credential_field_schema = Schema(
    {"credential_slug": All(str, NotEmpty()), "value": All(Any(str, int, bool, float), NotEmpty())}, required=True
)

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

loyalty_card_merchant_fields_schema = Schema(
    All(
        {
            Required("account_id"): All(str, NotEmpty()),
        },
        DictKeyReplace("account_id", "merchant_identifier"),
    ),
    extra=PREVENT_EXTRA,
)

loyalty_card_trusted_add_account_schema = Schema(
    All(
        {
            # We allow Add fields to be optional here for the sake of SquareMeal-type schemes,
            # which doesn't have any add fields, so use auth fields as the key identifier instead.
            Optional("add_fields"): loyalty_card_field_schema_with_consents,
            Optional("authorise_fields"): loyalty_card_field_schema_with_consents,
            Required("merchant_fields"): loyalty_card_merchant_fields_schema,
        },
        must_provide_single_add_or_auth_field,
    ),
    extra=PREVENT_EXTRA,
)

loyalty_card_add_schema = Schema({"loyalty_plan_id": int, "account": loyalty_card_add_account_schema}, required=True)

loyalty_card_trusted_add_schema = Schema(
    {"loyalty_plan_id": int, "account": loyalty_card_trusted_add_account_schema}, required=True
)

loyalty_card_put_trusted_add_schema = Schema({"account": loyalty_card_trusted_add_account_schema}, required=True)

loyalty_card_add_and_auth_account_schema = Schema(
    All(
        {
            # We allow Add fields to be optional here for the sake of Harvey Nichols, who don't have any add fields
            # so use auth fields as the key identifier instead.
            Optional("add_fields"): loyalty_card_field_schema_with_consents,
            # Authorise fields can be optional to allow linking with a single add field if the merchant supports it
            Optional("authorise_fields"): loyalty_card_field_schema_with_consents,
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
            Optional("add_fields"): loyalty_card_field_schema_with_consents,
            Required("authorise_fields"): loyalty_card_field_schema_with_consents,
        },
    ),
    extra=PREVENT_EXTRA,
)

loyalty_card_register_account_schema = Schema(
    All(
        {
            Required("register_ghost_card_fields"): loyalty_card_field_schema_with_consents,
        },
    ),
    extra=PREVENT_EXTRA,
)

loyalty_card_join_account_schema = Schema(
    All(
        {
            Required("join_fields"): loyalty_card_field_schema_with_consents,
        },
    ),
    extra=PREVENT_EXTRA,
)

loyalty_card_add_and_register_schema = Schema(
    {"loyalty_plan_id": int, "account": loyalty_card_add_and_register_account_schema}, required=True
)

loyalty_card_authorise_schema = Schema({"account": loyalty_card_authorise_account_schema}, required=True)
loyalty_card_register_schema = Schema({"account": loyalty_card_register_account_schema}, required=True)


loyalty_card_join_schema = Schema({"loyalty_plan_id": int, "account": loyalty_card_join_account_schema}, required=True)

payment_accounts_add_schema = Schema(
    {
        Required("expiry_month"): All(str, NotEmpty()),
        Required("expiry_year"): All(str, NotEmpty()),
        Optional("name_on_card"): str,
        Optional("card_nickname"): str,
        Optional("issuer"): str,
        Required("token"): All(str, NotEmpty()),
        Required("last_four_digits"): All(str, NotEmpty()),
        Required("first_six_digits"): All(str, NotEmpty()),
        Required("fingerprint"): All(str, NotEmpty()),
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


# Todo: uncomment and replace validators of the same name when implementing regex pattern validation
# ###############################################################
#         Required("expiry_month"): StripWhitespaceMatch(r"^(0?[1-9]|1[012])$"),
#         Required("expiry_year"): StripWhitespaceMatch(r"^[0-9]{2}$"),
#         Optional("name_on_card"): StripWhitespaceMatch(r"^[\u0000-\u2FFF]{1,150}$"),
#         Optional("card_nickname"): StripWhitespaceMatch(r"^[\u0000-\u2FFF]{1,150}$"),
#         Optional("issuer"): StripWhitespaceMatch(r"^[\u0000-\u2FFF]{1,200}$"),
#         Required("token"): StripWhitespaceMatch(r"^[\u0000-\u2FFF]{1,255}$"),
#         Required("last_four_digits"): StripWhitespaceMatch(r"^[0-9]{4,4}$"),
#         Required("first_six_digits"): StripWhitespaceMatch(r"^[0-9]{6,6}$"),
#         Required("fingerprint"): StripWhitespaceMatch(r"^[\u0000-\u2FFF]{1,100}$"),
#         Optional("provider"): StripWhitespaceMatch(r"^[\u0000-\u2FFF]{1,200}$"),
#         Optional("type"): StripWhitespaceMatch(r"^[\u0000-\u2FFF]{1,40}$"),
#         Optional("country"): StripWhitespaceMatch(r"^[\u0000-\u2FFF]{1,40}$"),
#         Optional("currency_code"): StripWhitespaceMatch(r"^([A-Za-z]{3}|[0-9]{3})$"),
#     },
#
#
#     All(
#             Optional("expiry_month"): StripWhitespaceMatch(r"^(0?[1-9]|1[012])$"),
#             Optional("expiry_year"): StripWhitespaceMatch(r"^[0-9]{2}$"),
#             Optional("name_on_card"): StripWhitespaceMatch(r"^[\u0000-\u2FFF]{1,150}$"),
#             Optional("card_nickname"): StripWhitespaceMatch(r"^[\u0000-\u2FFF]{1,150}$"),
#             Optional("issuer"): StripWhitespaceMatch(r"^[\u0000-\u2FFF]{1,200}$"),
#         },
#         must_provide_at_least_one_field,
#     ),
# ###############################################################

token_schema = Schema(
    {Required("grant_type"): All(str, NotEmpty()), Required("scope"): All([str])},
)

email_update_schema = Schema(All({"email": Email()}, email_must_be_passed), extra=PREVENT_EXTRA)

# Used as a discrete check on email validity by the token endpoint
check_valid_email = Schema(All({"email": Email()}, email_must_be_passed))
