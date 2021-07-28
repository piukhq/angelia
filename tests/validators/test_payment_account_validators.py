import falcon
import pytest

from app.api.serializers import PaymentCardSerializer
from app.api.validators import _validate_req_schema, _validate_resp_schema, payment_accounts_schema


class TestReqObject:
    def __init__(self, media):
        self.media = media


@pytest.fixture
def resp_data():
    return {
        "id": 1,
        "status": "",
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
        "expiry_year": "2020",
        "token": "token",
        "last_four_digits": "0987",
        "first_six_digits": "123456",
        "fingerprint": "fingerprint",
    }


def test_validate_req_schema_has_validation_error(req_data):
    req_data.pop("expiry_month")
    with pytest.raises(falcon.HTTPUnprocessableEntity):
        request = TestReqObject(req_data)
        _validate_req_schema(payment_accounts_schema, request)
    req_data["expiry_month"] = 10
    with pytest.raises(falcon.HTTPUnprocessableEntity):
        request = TestReqObject(req_data)
        _validate_req_schema(payment_accounts_schema, request)


def test_validate_req_schema_is_not_voluptous_schema(req_data):
    with pytest.raises(falcon.HTTPInternalServerError):
        request = TestReqObject(req_data)
        _validate_req_schema({"not": "schema"}, request)


def test_serialize_resp_success(resp_data):
    resp = TestReqObject(resp_data)
    assert _validate_resp_schema(PaymentCardSerializer, resp) == resp_data


def test_serialize_resp_cast_to_correct_types(resp_data):
    resp_data["name_on_card"] = 123
    resp = TestReqObject(resp_data)
    assert _validate_resp_schema(PaymentCardSerializer, resp)["name_on_card"] == "123"


def test_serialize_resp_missing_required_field(resp_data):
    resp_data.pop("name_on_card")
    resp = TestReqObject(resp_data)
    with pytest.raises(falcon.HTTPInternalServerError):
        _validate_resp_schema(PaymentCardSerializer, resp)
