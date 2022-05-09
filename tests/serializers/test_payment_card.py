import pytest

from app.api.serializers import PaymentAccountPostSerializer, PaymentAccountPatchSerializer


@pytest.fixture
def post_payment_account_data():
    return {
        "id": 1,
    }


@pytest.fixture
def patch_payment_account_data():
    return {
        "id": 1,
        "status": None,
        "name_on_card": "first last",
        "card_nickname": "nickname",
        "issuer": "bank",
        "expiry_month": "10",
        "expiry_year": "2020",
    }


def test_payment_card_post_serializer_all_as_expected(post_payment_account_data):
    payment_account_serialized = PaymentAccountPostSerializer(**post_payment_account_data)
    assert payment_account_serialized.id == post_payment_account_data["id"]
    assert type(payment_account_serialized.id) == int
    assert payment_account_serialized == post_payment_account_data


def test_payment_card_patch_serializer_all_as_expected(patch_payment_account_data):
    payment_account_serialized = PaymentAccountPatchSerializer(**patch_payment_account_data)
    assert payment_account_serialized.id == patch_payment_account_data["id"]
    assert payment_account_serialized.status == patch_payment_account_data["status"]
    assert payment_account_serialized.name_on_card == patch_payment_account_data["name_on_card"]
    assert payment_account_serialized.card_nickname == patch_payment_account_data["card_nickname"]
    assert payment_account_serialized.issuer == patch_payment_account_data["issuer"]
    assert payment_account_serialized.expiry_month == patch_payment_account_data["expiry_month"]
    assert payment_account_serialized.expiry_year == patch_payment_account_data["expiry_year"]


def test_payment_card_patch_serializer_casts_data_correct(patch_payment_account_data):
    patch_payment_account_data["id"] = "123"
    patch_payment_account_data["card_nickname"] = 78990
    patch_payment_account_data["expiry_year"] = 2020
    payment_account_serialized = PaymentAccountPatchSerializer(**patch_payment_account_data)
    assert type(payment_account_serialized.id) == int
    assert type(payment_account_serialized.card_nickname) == str
    assert type(payment_account_serialized.expiry_year) == str


def test_payment_card_patch_serializer_no_extra_fields(patch_payment_account_data):
    payment_account_serialized = PaymentAccountPatchSerializer(**patch_payment_account_data)
    assert payment_account_serialized == patch_payment_account_data
