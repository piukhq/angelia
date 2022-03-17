import pytest

from app.api.serializers import PaymentAccountSerializer


@pytest.fixture
def payment_account_data():
    return {
        "id": 1,
        "status": None,
        "name_on_card": "first last",
        "card_nickname": "nickname",
        "issuer": "bank",
        "expiry_month": "10",
        "expiry_year": "2020",
    }


def test_payment_card_serializer_all_as_expected(payment_account_data):
    payment_account_serialized = PaymentAccountSerializer(**payment_account_data)
    assert payment_account_serialized.id == payment_account_data["id"]
    assert payment_account_serialized.status == payment_account_data["status"]
    assert payment_account_serialized.name_on_card == payment_account_data["name_on_card"]
    assert payment_account_serialized.card_nickname == payment_account_data["card_nickname"]
    assert payment_account_serialized.issuer == payment_account_data["issuer"]
    assert payment_account_serialized.expiry_month == payment_account_data["expiry_month"]
    assert payment_account_serialized.expiry_year == payment_account_data["expiry_year"]


def test_payment_card_serializer_casts_data_correct(payment_account_data):
    payment_account_data["id"] = "123"
    payment_account_data["card_nickname"] = 78990
    payment_account_data["expiry_year"] = 2020
    payment_account_serialized = PaymentAccountSerializer(**payment_account_data)
    assert type(payment_account_serialized.id) == int
    assert type(payment_account_serialized.card_nickname) == str
    assert type(payment_account_serialized.expiry_year) == str


def test_payment_card_serializer_no_extra_fields(payment_account_data):
    payment_account_serialized = PaymentAccountSerializer(**payment_account_data)
    assert payment_account_serialized == payment_account_data
