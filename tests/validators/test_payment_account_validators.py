import falcon
import pytest
import voluptuous

from app.api.serializers import PaymentCardSerializer
from app.api.validators import _validate_req_schema, _validate_resp_schema, payment_accounts_add_schema


class TestReqObject:
    def __init__(self, media):
        self.media = media

    def get_media(self, default_when_empty=None):

        if self.media:
            return self.media
        else:
            return default_when_empty


@pytest.fixture
def resp_data():
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
def req_data():
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


def test_validate_req_schema_has_validation_error(req_data):
    req_data.pop("expiry_month")
    with pytest.raises(falcon.HTTPUnprocessableEntity):
        request = TestReqObject(req_data)
        _validate_req_schema(payment_accounts_add_schema, request)
    req_data["expiry_month"] = 10
    with pytest.raises(falcon.HTTPUnprocessableEntity):
        request = TestReqObject(req_data)
        _validate_req_schema(payment_accounts_add_schema, request)


def test_validate_req_schema_is_not_voluptous_schema(req_data):
    with pytest.raises(falcon.HTTPInternalServerError):
        request = TestReqObject(req_data)
        _validate_req_schema({"not": "schema"}, request)


# Todo: These are serializer tests and should be moved. Requires some reworking.
########################


def test_serialize_resp_success(resp_data):
    resp = TestReqObject(resp_data)
    _validate_resp_schema(PaymentCardSerializer, resp)
    assert resp.media == resp_data


def test_serialize_resp_cast_to_correct_types(resp_data):
    resp_data["name_on_card"] = 123
    resp = TestReqObject(resp_data)
    _validate_resp_schema(PaymentCardSerializer, resp)
    assert resp.media["name_on_card"] == "123"


def test_serialize_resp_missing_required_field(resp_data):
    resp_data.pop("name_on_card")
    resp = TestReqObject(resp_data)
    with pytest.raises(falcon.HTTPInternalServerError):
        _validate_resp_schema(PaymentCardSerializer, resp)


########################

# payment_accounts_add_schema tests

# fmt: off
VALID_EXPIRY_MONTHS = [
    "1", "01", "2", "02", "3", "03", "4", "04", "5", "05", "6", "06", "7", "07",
    "8", "08", "9", "09", "10", "11", "12", "  12  ", "\n12\n", "\r12\r", "\t12\t",
]
# fmt: on
INVALID_EXPIRY_MONTHS = ["0", "00", "000", 0, 1, "111", "13", "A12", "1P", "JJ", "jj", "j1", "Jan", None, ""]


@pytest.mark.parametrize("valid_expiry_month", VALID_EXPIRY_MONTHS)
def test_payment_accounts_add_schema_valid_expiry_month(req_data, valid_expiry_month):
    schema = payment_accounts_add_schema

    req_data["expiry_month"] = valid_expiry_month
    schema(req_data)


@pytest.mark.parametrize("invalid_expiry_month", INVALID_EXPIRY_MONTHS)
def test_payment_accounts_add_schema_invalid_expiry_month(req_data, invalid_expiry_month):
    schema = payment_accounts_add_schema

    req_data["expiry_month"] = invalid_expiry_month
    with pytest.raises(voluptuous.MultipleInvalid):
        schema(req_data)


VALID_EXPIRY_YEARS = ["00", "01", "10", "20", "99", "  12  ", "\n12\n", "\r12\r", "\t12\t"]
INVALID_EXPIRY_YEARS = [1, 20, "1", "2001", "1999", None, ""]


@pytest.mark.parametrize("valid_expiry_year", VALID_EXPIRY_YEARS)
def test_payment_accounts_add_schema_valid_expiry_year_valid(req_data, valid_expiry_year):
    schema = payment_accounts_add_schema

    req_data["expiry_year"] = valid_expiry_year
    schema(req_data)


@pytest.mark.parametrize("invalid_expiry_year", INVALID_EXPIRY_YEARS)
def test_payment_accounts_add_schema_invalid_expiry_year(req_data, invalid_expiry_year):
    schema = payment_accounts_add_schema

    req_data["expiry_year"] = invalid_expiry_year
    with pytest.raises(voluptuous.MultipleInvalid):
        schema(req_data)


VALID_FREE_TEXT = [
    "John Fisher",
    r"±!@£$%^&*(()_+[]{}\|\"'/?.>,<;:~`",
    "⽆⿶é",
    "1002323",
    "  a ",
    "\ra\r",
    "\ta\t",
    "\na\n",
]
INVALID_FREE_TEXT = [1, "", "  ", "\n\n", "\t\t", "\r\r", None]

FREE_TEXT_FIELDS = ["name_on_card", "card_nickname", "issuer"]


@pytest.mark.parametrize("free_text_field", FREE_TEXT_FIELDS)
# VALID_FREE_TEXT list is common and used in other tests with max length limits so test length separately
@pytest.mark.parametrize("valid_field_value", VALID_FREE_TEXT + [250 * "a"])
def test_payment_accounts_add_schema_valid_free_text_fields(req_data, valid_field_value, free_text_field):
    schema = payment_accounts_add_schema

    req_data[free_text_field] = valid_field_value
    data = schema(req_data)

    assert data[free_text_field] == valid_field_value.strip()


@pytest.mark.parametrize("free_text_field", FREE_TEXT_FIELDS)
@pytest.mark.parametrize("invalid_field_value", INVALID_FREE_TEXT)
def test_payment_accounts_add_schema_invalid_free_text_fields(req_data, invalid_field_value, free_text_field):
    schema = payment_accounts_add_schema

    req_data[free_text_field] = invalid_field_value
    with pytest.raises(voluptuous.MultipleInvalid):
        schema(req_data)


VALID_TOKENS = VALID_FREE_TEXT + [255 * "a"]
INVALID_TOKENS = INVALID_FREE_TEXT + [256 * "a"]


@pytest.mark.parametrize("valid_token", VALID_TOKENS)
def test_payment_accounts_add_schema_valid_token(req_data, valid_token):
    schema = payment_accounts_add_schema

    req_data["token"] = valid_token
    data = schema(req_data)

    assert data["token"] == valid_token.strip()


@pytest.mark.parametrize("invalid_token", INVALID_TOKENS)
def test_payment_accounts_add_schema_invalid_token(req_data, invalid_token):
    schema = payment_accounts_add_schema

    req_data["token"] = invalid_token
    with pytest.raises(voluptuous.MultipleInvalid):
        schema(req_data)


VALID_FINGERPRINTS = VALID_FREE_TEXT + [100 * "a"]
INVALID_FINGERPRINTS = INVALID_FREE_TEXT + [101 * "a"]


@pytest.mark.parametrize("valid_fingerprint", VALID_FINGERPRINTS)
def test_payment_accounts_add_schema_valid_fingerprint(req_data, valid_fingerprint):
    schema = payment_accounts_add_schema

    req_data["fingerprint"] = valid_fingerprint
    data = schema(req_data)

    assert data["fingerprint"] == valid_fingerprint.strip()


@pytest.mark.parametrize("invalid_fingerprint", INVALID_FINGERPRINTS)
def test_payment_accounts_add_schema_invalid_fingerprint(req_data, invalid_fingerprint):
    schema = payment_accounts_add_schema

    req_data["fingerprint"] = invalid_fingerprint
    with pytest.raises(voluptuous.MultipleInvalid):
        schema(req_data)


VALID_PROVIDERS = VALID_FREE_TEXT + [200 * "a"]
INVALID_PROVIDERS = INVALID_FREE_TEXT + [201 * "a"]


@pytest.mark.parametrize("valid_provider", VALID_PROVIDERS)
def test_payment_accounts_add_schema_valid_provider(req_data, valid_provider):
    schema = payment_accounts_add_schema

    req_data["provider"] = valid_provider
    data = schema(req_data)

    assert data["provider"] == valid_provider.strip()


@pytest.mark.parametrize("invalid_provider", INVALID_PROVIDERS)
def test_payment_accounts_add_schema_invalid_provider(req_data, invalid_provider):
    schema = payment_accounts_add_schema

    req_data["provider"] = invalid_provider
    with pytest.raises(voluptuous.MultipleInvalid):
        schema(req_data)


VALID_TYPES = VALID_FREE_TEXT + [40 * "a"]
INVALID_TYPES = INVALID_FREE_TEXT + [41 * "a"]


@pytest.mark.parametrize("valid_type", VALID_TYPES)
def test_payment_accounts_add_schema_valid_type(req_data, valid_type):
    schema = payment_accounts_add_schema

    req_data["type"] = valid_type
    data = schema(req_data)

    assert data["type"] == valid_type.strip()


@pytest.mark.parametrize("invalid_type", INVALID_TYPES)
def test_payment_accounts_add_schema_invalid_type(req_data, invalid_type):
    schema = payment_accounts_add_schema

    req_data["type"] = invalid_type
    with pytest.raises(voluptuous.MultipleInvalid):
        schema(req_data)


VALID_COUNTRIES = VALID_FREE_TEXT + [40 * "a"]
INVALID_COUNTRIES = INVALID_FREE_TEXT + [41 * "a"]


@pytest.mark.parametrize("valid_country", VALID_COUNTRIES)
def test_payment_accounts_add_schema_valid_country(req_data, valid_country):
    schema = payment_accounts_add_schema

    req_data["country"] = valid_country
    data = schema(req_data)

    assert data["country"] == valid_country.strip()


@pytest.mark.parametrize("invalid_country", INVALID_COUNTRIES)
def test_payment_accounts_add_schema_invalid_country(req_data, invalid_country):
    schema = payment_accounts_add_schema

    req_data["country"] = invalid_country
    with pytest.raises(voluptuous.MultipleInvalid):
        schema(req_data)


VALID_LAST_FOUR_DIGITS = ["0000", "1000", "9999", "  1234  ", "\n1234\n", "\r1234\r", "\t1234\t"]
INVALID_LAST_FOUR_DIGITS = [1234, 0, "1", "abcd", None, "", "12 34", "12345"]


@pytest.mark.parametrize("valid_last_four_digits", VALID_LAST_FOUR_DIGITS)
def test_payment_accounts_add_schema_valid_last_four_digits(req_data, valid_last_four_digits):
    schema = payment_accounts_add_schema

    req_data["last_four_digits"] = valid_last_four_digits
    data = schema(req_data)

    assert data["last_four_digits"] == valid_last_four_digits.strip()


@pytest.mark.parametrize("invalid_last_four_digits", INVALID_LAST_FOUR_DIGITS)
def test_payment_accounts_add_schema_invalid_last_four_digits(req_data, invalid_last_four_digits):
    schema = payment_accounts_add_schema

    req_data["last_four_digits"] = invalid_last_four_digits
    with pytest.raises(voluptuous.MultipleInvalid):
        schema(req_data)


VALID_FIRST_SIX_DIGITS = ["000000", "999999", "  123456  ", "\n123456\n", "\r123456\r", "\t123456\t"]
INVALID_FIRST_SIX_DIGITS = [123456, 0, "1", "abcdef", None, "", "123 456", "1234567"]


@pytest.mark.parametrize("valid_first_six_digits", VALID_FIRST_SIX_DIGITS)
def test_payment_accounts_add_schema_valid_first_six_digits(req_data, valid_first_six_digits):
    schema = payment_accounts_add_schema

    req_data["first_six_digits"] = valid_first_six_digits
    data = schema(req_data)

    assert data["first_six_digits"] == valid_first_six_digits.strip()


@pytest.mark.parametrize("invalid_first_six_digits", INVALID_FIRST_SIX_DIGITS)
def test_payment_accounts_add_schema_invalid_first_six_digits(req_data, invalid_first_six_digits):
    schema = payment_accounts_add_schema

    req_data["first_six_digits"] = invalid_first_six_digits
    with pytest.raises(voluptuous.MultipleInvalid):
        schema(req_data)


VALID_CURRENCY_CODES = ["GBP", "gbp", "  GBP  ", "\nGBP\n", "\rGBP\r", "\tGBP\t", "123"]
INVALID_CURRENCY_CODES = [123, 0, "1", "1234", "abcdef", None, ""]


@pytest.mark.parametrize("valid_currency_code", VALID_CURRENCY_CODES)
def test_payment_accounts_add_schema_valid_currency_code(req_data, valid_currency_code):
    schema = payment_accounts_add_schema

    req_data["currency_code"] = valid_currency_code
    data = schema(req_data)

    assert data["currency_code"] == valid_currency_code.strip()


@pytest.mark.parametrize("invalid_currency_code", INVALID_CURRENCY_CODES)
def test_payment_accounts_add_schema_invalid_currency_code(req_data, invalid_currency_code):
    schema = payment_accounts_add_schema

    req_data["currency_code"] = invalid_currency_code
    with pytest.raises(voluptuous.MultipleInvalid):
        schema(req_data)
