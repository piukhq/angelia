import falcon
import pytest
import voluptuous

from app.api.serializers import PaymentAccountPatchSerializer
from app.api.validators import _validate_req_schema, _validate_resp_schema, payment_accounts_add_schema


class TestReqObject:
    def __init__(self, media: dict, context: dict | None = None) -> None:
        self.media = media
        self.context = context

    def get_media(self, default_when_empty: dict | None = None) -> dict | None:
        if self.media:
            return self.media

        return default_when_empty


@pytest.fixture
def resp_data() -> dict:
    return {
        "id": 1,
        "status": None,
        "name_on_card": "first last",
        "card_nickname": "nickname",
        "issuer": "bank",
        "expiry_month": "10",
        "expiry_year": "2020",
    }


@pytest.fixture
def req_data() -> dict:
    return {
        "issuer": "issuer",
        "name_on_card": "First Last",
        "card_nickname": "nickname",
        "expiry_month": "10",
        "expiry_year": "20",
        "token": "token",
        "last_four_digits": "0987",
        "first_six_digits": "123456",
        "fingerprint": "fingerprint",
    }


def test_validate_req_schema_has_validation_error(req_data: dict) -> None:
    req_data.pop("expiry_month")
    with pytest.raises(falcon.HTTPUnprocessableEntity):
        request = TestReqObject(req_data)
        _validate_req_schema(payment_accounts_add_schema, request)
    req_data["expiry_month"] = 10
    with pytest.raises(falcon.HTTPUnprocessableEntity):
        request = TestReqObject(req_data)
        _validate_req_schema(payment_accounts_add_schema, request)


def test_validate_req_schema_is_not_voluptous_schema(req_data: dict) -> None:
    with pytest.raises(falcon.HTTPInternalServerError):
        request = TestReqObject(req_data)
        _validate_req_schema({"not": "schema"}, request)


# Todo: These are serializer tests and should be moved. Requires some reworking.
########################


def test_serialize_resp_success(resp_data: dict) -> None:
    resp = TestReqObject(resp_data)
    _validate_resp_schema(PaymentAccountPatchSerializer, resp)
    assert resp.media == resp_data


def test_serialize_resp_cast_to_correct_types(resp_data: dict) -> None:
    resp_data["name_on_card"] = 123
    resp = TestReqObject(resp_data)
    _validate_resp_schema(PaymentAccountPatchSerializer, resp)
    assert resp.media["name_on_card"] == "123"


def test_serialize_resp_missing_required_field(resp_data: dict) -> None:
    resp_data.pop("expiry_month")
    resp = TestReqObject(resp_data)
    with pytest.raises(falcon.HTTPInternalServerError):
        _validate_resp_schema(PaymentAccountPatchSerializer, resp)


########################

# payment_accounts_add_schema tests

# TODO: Remove in place of the tests below when implementing regex pattern validation
# ###############################################################
REQUIRED_FIELDS = ["expiry_month", "expiry_year", "token", "last_four_digits", "first_six_digits", "fingerprint"]


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_payment_accounts_add_schema_required_fields_not_empty(req_data: dict, field: str) -> None:
    schema = payment_accounts_add_schema

    req_data[field] = ""
    with pytest.raises(voluptuous.MultipleInvalid):
        schema(req_data)


# ###############################################################

# # fmt: off
#     "1", "01", "2", "02", "3", "03", "4", "04", "5", "05", "6", "06", "7", "07",
#     "8", "08", "9", "09", "10", "11", "12", "  12  ", "\n12\n", "\r12\r", "\t12\t",
# # fmt: on
#
#
#     "John Fisher",
#     "⽆⿶é",
#     "1002323",
#     "  a ",
#     "\ra\r",
#     "\ta\t",
#     "\na\n",
#
#     for field, min_length, max_length in [
#
#
#
#
#
# @pytest.mark.parametrize("valid_expiry_month", VALID_EXPIRY_MONTHS)
# def test_payment_accounts_add_schema_valid_expiry_month(req_data, valid_expiry_month) -> None:
#
#
#
# @pytest.mark.parametrize("invalid_expiry_month", INVALID_EXPIRY_MONTHS)
# def test_payment_accounts_add_schema_invalid_expiry_month(req_data, invalid_expiry_month) -> None:
#
#     with pytest.raises(voluptuous.MultipleInvalid):
#
#
# @pytest.mark.parametrize("valid_expiry_year", VALID_EXPIRY_YEARS)
# def test_payment_accounts_add_schema_valid_expiry_year_valid(req_data, valid_expiry_year) -> None:
#
#
#
# @pytest.mark.parametrize("invalid_expiry_year", INVALID_EXPIRY_YEARS)
# def test_payment_accounts_add_schema_invalid_expiry_year(req_data, invalid_expiry_year) -> None:
#
#     with pytest.raises(voluptuous.MultipleInvalid):
#
#
# @pytest.mark.parametrize("free_text_field", FREE_TEXT_FIELDS)
# @pytest.mark.parametrize("valid_field_value", VALID_FREE_TEXT)
# def test_payment_accounts_add_schema_valid_free_text_fields(req_data, valid_field_value, free_text_field) -> None:
#
#
#
#
# @pytest.mark.parametrize("free_text_field", FREE_TEXT_FIELDS)
# @pytest.mark.parametrize("invalid_field_value", INVALID_FREE_TEXT)
# def test_payment_accounts_add_schema_invalid_free_text_fields(req_data, invalid_field_value, free_text_field) -> None:
#
#     with pytest.raises(voluptuous.MultipleInvalid):
#
#
# @pytest.mark.parametrize("free_text_field", FREE_TEXT_FIELDS_WITH_LENGTH)
# def test_payment_accounts_add_schema_valid_free_text_fields_lengths(req_data, free_text_field) -> None:
#
#
#
#
#
#
# @pytest.mark.parametrize("free_text_field", FREE_TEXT_FIELDS_WITH_LENGTH)
# def test_payment_accounts_add_schema_invalid_free_text_fields_lengths(req_data, free_text_field) -> None:
#
#     with pytest.raises(voluptuous.MultipleInvalid):
#
#     with pytest.raises(voluptuous.MultipleInvalid):
#
#
# @pytest.mark.parametrize("valid_last_four_digits", VALID_LAST_FOUR_DIGITS)
# def test_payment_accounts_add_schema_valid_last_four_digits(req_data, valid_last_four_digits) -> None:
#
#
#
#
# @pytest.mark.parametrize("invalid_last_four_digits", INVALID_LAST_FOUR_DIGITS)
# def test_payment_accounts_add_schema_invalid_last_four_digits(req_data, invalid_last_four_digits) -> None:
#
#     with pytest.raises(voluptuous.MultipleInvalid):
#
#
# @pytest.mark.parametrize("valid_first_six_digits", VALID_FIRST_SIX_DIGITS)
# def test_payment_accounts_add_schema_valid_first_six_digits(req_data, valid_first_six_digits) -> None:
#
#
#
#
# @pytest.mark.parametrize("invalid_first_six_digits", INVALID_FIRST_SIX_DIGITS)
# def test_payment_accounts_add_schema_invalid_first_six_digits(req_data, invalid_first_six_digits) -> None:
#
#     with pytest.raises(voluptuous.MultipleInvalid):
#
#
# @pytest.mark.parametrize("valid_currency_code", VALID_CURRENCY_CODES)
# def test_payment_accounts_add_schema_valid_currency_code(req_data, valid_currency_code) -> None:
#
#
#
#
# @pytest.mark.parametrize("invalid_currency_code", INVALID_CURRENCY_CODES)
# def test_payment_accounts_add_schema_invalid_currency_code(req_data, invalid_currency_code) -> None:
#
#     with pytest.raises(voluptuous.MultipleInvalid):
#
#
# # payment_accounts_update_schema tests
#
#
# @pytest.fixture
# def update_req_data() -> None:
#     return {
#
#
#     for field, min_length, max_length in [
#
#
# @pytest.mark.parametrize("valid_expiry_month", VALID_EXPIRY_MONTHS)
# def test_payment_accounts_update_schema_valid_expiry_month(update_req_data, valid_expiry_month) -> None:
#
#
#
# @pytest.mark.parametrize("invalid_expiry_month", INVALID_EXPIRY_MONTHS)
# def test_payment_accounts_update_schema_invalid_expiry_month(update_req_data, invalid_expiry_month) -> None:
#
#     with pytest.raises(voluptuous.MultipleInvalid):
#
#
# @pytest.mark.parametrize("free_text_field", UPDATE_FREE_TEXT_FIELDS)
# @pytest.mark.parametrize("valid_field_value", VALID_FREE_TEXT)
# def test_payment_accounts_update_schema_valid_free_text_fields(update_req_data, valid_field_value, free_text_field)
#
#
#
#
# @pytest.mark.parametrize("free_text_field", UPDATE_FREE_TEXT_FIELDS)
# @pytest.mark.parametrize("invalid_field_value", INVALID_FREE_TEXT)
# def test_payment_accounts_update_schema_invalid_free_text_fields(
#     update_req_data, invalid_field_value, free_text_field
# ):
#
#     with pytest.raises(voluptuous.MultipleInvalid):
#
#
# @pytest.mark.parametrize("valid_expiry_year", VALID_EXPIRY_YEARS)
# def test_payment_accounts_update_schema_valid_expiry_year_valid(update_req_data, valid_expiry_year) -> None:
#
#
#
# @pytest.mark.parametrize("invalid_expiry_year", INVALID_EXPIRY_YEARS)
# def test_payment_accounts_update_schema_invalid_expiry_year(update_req_data, invalid_expiry_year) -> None:
#
#     with pytest.raises(voluptuous.MultipleInvalid):
#
#
# @pytest.mark.parametrize("free_text_field", UPDATE_FREE_TEXT_FIELDS_WITH_LENGTH)
# def test_payment_accounts_update_schema_valid_free_text_fields_lengths(update_req_data, free_text_field) -> None:
#
#
#
#
#
#
# @pytest.mark.parametrize("free_text_field", UPDATE_FREE_TEXT_FIELDS_WITH_LENGTH)
# def test_payment_accounts_update_schema_invalid_free_text_fields_lengths(update_req_data, free_text_field) -> None:
#
#     with pytest.raises(voluptuous.MultipleInvalid):
#
#     with pytest.raises(voluptuous.MultipleInvalid):
#
#
# def test_payment_accounts_update_schema_no_data_raises_error() -> None:
#     with pytest.raises(voluptuous.MultipleInvalid):

# ###############################################################
