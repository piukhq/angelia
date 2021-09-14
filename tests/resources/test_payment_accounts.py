from falcon import HTTP_200, HTTP_201, HTTP_202, HTTP_404, HTTP_422, HTTP_500, HTTPInternalServerError
from app.api.exceptions import ResourceNotFoundError

from tests.helpers.authenticated_request import get_authenticated_request

resp_data = {
    "id": 1,
    "status": "",
    "name_on_card": "first last",
    "card_nickname": "nickname",
    "issuer": "bank",
    "expiry_month": "10",
    "expiry_year": "2020",
}

req_data = {
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


def test_post_payment_accounts_created(mocker):
    mocked_resp = mocker.patch("app.handlers.payment_account.PaymentAccountHandler.add_card")
    mocked_resp.return_value = resp_data, True
    resp = get_authenticated_request(path="/v2/payment_accounts", json=req_data, method="POST")
    assert resp.status == HTTP_201


def test_post_payment_accounts_exists(mocker):
    mocked_resp = mocker.patch("app.handlers.payment_account.PaymentAccountHandler.add_card")
    mocked_resp.return_value = resp_data, False
    resp = get_authenticated_request(path="/v2/payment_accounts", json=req_data, method="POST")
    assert resp.status == HTTP_200


def test_post_payment_accounts_required_req_fields_missing(mocker):
    req_data_missing = {
        "issuer": "issuer",
        "name_on_card": "First Last",
        "fingerprint": "fingerprint",
    }
    mocked_resp = mocker.patch("app.handlers.payment_account.PaymentAccountHandler.add_card")
    mocked_resp.return_value = resp_data, False
    resp = get_authenticated_request(path="/v2/payment_accounts", json=req_data_missing, method="POST")
    assert resp.status == HTTP_422


def test_post_payment_accounts_required_resp_fields_missing(mocker):
    resp_data_missing = {
        "id": 1,
        "status": "",
        "name_on_card": "first last",
        "card_nickname": "nickname",
    }
    mocked_resp = mocker.patch("app.handlers.payment_account.PaymentAccountHandler.add_card")
    mocked_resp.return_value = resp_data_missing, False
    resp_data.pop("id")
    resp = get_authenticated_request(path="/v2/payment_accounts", json=req_data, method="POST")
    assert resp.status == HTTP_500


def test_delete_payment_account_success(mocker):
    mocker.patch("app.handlers.payment_account.PaymentAccountHandler.delete_card")
    resp = get_authenticated_request(path="/v2/payment_accounts/1", json=req_data, method="DELETE")
    assert resp.status == HTTP_202


def test_delete_payment_account_by_nonexistent_id(mocker):
    mocked_resp = mocker.patch("app.handlers.payment_account.PaymentAccountHandler.delete_card")
    mocked_resp.side_effect = ResourceNotFoundError()
    resp = get_authenticated_request(path="/v2/payment_accounts/1", json=req_data, method="DELETE")

    assert resp.status == HTTP_404
    assert resp.json["error_slug"] == "RESOURCE_NOT_FOUND"
    assert resp.json["error_message"] == "Could not find this account or card"


def test_delete_internal_error_occurred(mocker):
    mocked_resp = mocker.patch("app.handlers.payment_account.PaymentAccountHandler.delete_card")
    mocked_resp.side_effect = HTTPInternalServerError
    resp = get_authenticated_request(path="/v2/payment_accounts/1", json=req_data, method="DELETE")

    assert resp.status == HTTP_500
