from unittest.mock import MagicMock, patch

from falcon import HTTP_200, HTTP_201, HTTP_202, HTTP_403, HTTP_404

from tests.helpers.authenticated_request import get_authenticated_request


@patch("angelia.resources.loyalty_cards.LoyaltyCardHandler")
def test_add_response_created(mock_handler: MagicMock, add_req_data: dict) -> None:
    mock_handler.return_value.card_id = 1
    mock_handler.return_value.handle_add_only_card.return_value = True
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add", json=add_req_data, method="POST", user_id=1, channel="com.test.channel"
    )
    assert resp.status == HTTP_201


@patch("angelia.resources.loyalty_cards.LoyaltyCardHandler")
def test_add_response_returned_or_linked(mock_handler: MagicMock, add_req_data: dict) -> None:
    mock_handler.return_value.card_id = 1
    mock_handler.return_value.handle_add_only_card.return_value = False
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add", json=add_req_data, method="POST", user_id=1, channel="com.test.channel"
    )
    assert resp.status == HTTP_200


def test_trusted_add_response_forbidden(trusted_add_req_data: dict) -> None:
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_trusted",
        json=trusted_add_req_data,
        method="POST",
        user_id=1,
        channel="com.test.channel",
        is_trusted_channel=False,
    )
    assert resp.status == HTTP_403


@patch("angelia.resources.loyalty_cards.LoyaltyCardHandler")
def test_trusted_add_response_created(mock_handler: MagicMock, trusted_add_req_data: dict) -> None:
    mock_handler.return_value.card_id = 1
    mock_handler.return_value.handle_trusted_add_card.return_value = True

    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_trusted",
        json=trusted_add_req_data,
        method="POST",
        user_id=1,
        channel="com.test.channel",
        is_trusted_channel=True,
    )
    assert resp.status == HTTP_201


@patch("angelia.resources.loyalty_cards.LoyaltyCardHandler")
def test_trusted_add_response_returned_or_linked(mock_handler: MagicMock, trusted_add_req_data: dict) -> None:
    mock_handler.return_value.card_id = 1
    mock_handler.return_value.handle_trusted_add_card.return_value = False
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_trusted",
        json=trusted_add_req_data,
        method="POST",
        user_id=1,
        channel="com.test.channel",
        is_trusted_channel=True,
    )
    assert resp.status == HTTP_200


@patch("angelia.resources.loyalty_cards.LoyaltyCardHandler")
def test_add_and_auth_response_created(mock_handler: MagicMock, add_and_auth_req_data: dict) -> None:
    mock_handler.return_value.card_id = 1
    mock_handler.return_value.handle_add_auth_card.return_value = True
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_and_authorise",
        json=add_and_auth_req_data,
        method="POST",
        user_id=1,
        channel="com.test.channel",
    )
    assert resp.status == HTTP_202


@patch("angelia.resources.loyalty_cards.LoyaltyCardHandler")
def test_add_and_auth_response_returned_or_linked(mock_handler: MagicMock, add_and_auth_req_data: dict) -> None:
    mock_handler.return_value.card_id = 1
    mock_handler.return_value.handle_add_auth_card.return_value = False
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_and_authorise",
        json=add_and_auth_req_data,
        method="POST",
        user_id=1,
        channel="com.test.channel",
    )
    assert resp.status == HTTP_202


@patch("angelia.resources.loyalty_cards.LoyaltyCardHandler")
def test_authorise_response_return_existing(mock_handler: MagicMock, auth_req_data: dict) -> None:
    mock_handler.return_value.card_id = 1
    mock_handler.return_value.handle_authorise_card.return_value = False
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/123/authorise",
        json=auth_req_data,
        method="PUT",
        user_id=1,
        channel="com.test.channel",
    )
    assert resp.status == HTTP_200


@patch("angelia.resources.loyalty_cards.LoyaltyCardHandler")
def test_authorise_response_update_accepted(mock_handler: MagicMock, auth_req_data: dict) -> None:
    mock_handler.return_value.card_id = 1
    mock_handler.return_value.handle_authorise_card.return_value = True
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/123/authorise",
        json=auth_req_data,
        method="PUT",
        user_id=1,
        channel="com.test.channel",
    )
    assert resp.status == HTTP_202


@patch("angelia.resources.loyalty_cards.LoyaltyCardHandler")
def test_authorise_error_not_int(mock_handler: MagicMock, auth_req_data: dict) -> None:
    mock_handler.return_value.card_id = 1
    mock_handler.return_value.handle_authorise_card.return_value = True
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/eer2/authorise",
        json=auth_req_data,
        method="PUT",
        user_id=1,
        channel="com.test.channel",
    )
    assert resp.status == HTTP_404


@patch("angelia.resources.loyalty_cards.LoyaltyCardHandler")
def test_register_response_new_register_intent(mock_handler: MagicMock, register_req_data: dict) -> None:
    mock_handler.return_value.card_id = 1
    mock_handler.return_value.handle_update_register_card.return_value = True
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/123/register",
        json=register_req_data,
        method="PUT",
        user_id=1,
        channel="com.test.channel",
    )
    assert resp.status == HTTP_202


@patch("angelia.resources.loyalty_cards.LoyaltyCardHandler")
def test_register_response_registration_in_progress(mock_handler: MagicMock, register_req_data: dict) -> None:
    mock_handler.return_value.card_id = 1
    mock_handler.return_value.handle_update_register_card.return_value = False
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/123/register",
        json=register_req_data,
        method="PUT",
        user_id=1,
        channel="com.test.channel",
    )
    assert resp.status == HTTP_200


@patch("angelia.resources.loyalty_cards.LoyaltyCardHandler")
def test_join_response(mock_handler: MagicMock, join_req_data: dict) -> None:
    mock_handler.return_value.card_id = 1
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/join",
        json=join_req_data,
        method="POST",
        user_id=1,
        channel="com.test.channel",
    )
    assert resp.status == HTTP_202


@patch("angelia.resources.loyalty_cards.LoyaltyCardHandler")
def test_delete_loyalty_card_response(mock_handler: MagicMock) -> None:
    mock_handler.return_value.card_id = 1
    mock_handler.return_value.handle_add_register_card.return_value = False
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/123",
        method="DELETE",
        user_id=1,
        channel="com.test.channel",
    )
    assert resp.status == HTTP_202


@patch("angelia.resources.loyalty_cards.LoyaltyCardHandler")
def test_patch_failed_join_response(mock_handler: MagicMock, join_req_data: dict) -> None:
    mock_handler.return_value.card_id = 1
    mock_handler.return_value.handle_add_register_card.return_value = False
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/1/join",
        json=join_req_data,
        method="PUT",
        user_id=1,
        channel="com.test.channel",
    )
    assert resp.status == HTTP_202
