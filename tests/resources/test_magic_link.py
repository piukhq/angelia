import pytest
from falcon import HTTP_202, HTTP_422
from pytest_mock import MockerFixture

from tests.helpers.authenticated_request import get_authenticated_request, get_client


def test_access_tokens_on_post(mocker: MockerFixture) -> None:
    sample_token = "sample value"

    mock_response = {"access_token": "test value"}
    mock_handler = mocker.MagicMock()
    mocker.patch("app.resources.magic_link.MagicLinkHandler", return_value=mock_handler)
    mock_handler.get_or_create_user.return_value = mock_response

    resp = get_authenticated_request(method="POST", path="/v2/magic_link/access_token", json={"token": sample_token})

    assert resp.status == HTTP_202
    assert resp.json == mock_response

    mock_handler.get_or_create_user.assert_called_once_with(sample_token)


def test_on_post_email(mocker: MockerFixture) -> None:
    mock_handler = mocker.MagicMock()
    mocker.patch("app.resources.magic_link.MagicLinkHandler", return_value=mock_handler)
    mock_handler.send_magic_link_email.return_value = {}

    client = get_client()
    resp = client.simulate_post(
        path="/v2/magic_link",
        json={"email": "test@bink.test", "loyalty_plan_id": 1, "locale": "en_GB", "channel_id": "test.bundle.id"},
    )

    assert resp.status == HTTP_202
    assert resp.json == {}

    mock_handler.send_magic_link_email.assert_called_once_with("test@bink.test", 1, "en_GB", "test.bundle.id")


@pytest.mark.parametrize(
    ("payload"),
    (
        {"loyalty_plan_id": 1, "locale": "en_GB", "channel_id": "test.bundle.id"},
        {"email": "test@bink.test", "locale": "en_GB", "channel_id": "test.bundle.id"},
        {"email": "test@bink.test", "loyalty_plan_id": 1, "channel_id": "test.bundle.id"},
        {"email": "test@bink.test", "loyalty_plan_id": 1, "locale": "en_GB"},
        # bad locale - only support "en_GB"
        {"email": "test@bink.test", "loyalty_plan_id": 1, "locale": "en_US", "bundle_id": "test.bundle.id"},
    ),
)
def test_on_post_email_bad_data(payload: dict, mocker: MockerFixture) -> None:
    mock_handler = mocker.MagicMock()
    mocker.patch("app.resources.magic_link.MagicLinkHandler", return_value=mock_handler)
    mock_handler.send_magic_link_email.return_value = {}

    client = get_client()
    resp = client.simulate_post(path="/v2/magic_link", json=payload)

    assert resp.status == HTTP_422

    mock_handler.send_magic_link_email.assert_not_called()
