from unittest.mock import MagicMock, patch

from falcon import HTTP_200, HTTP_202

from tests.helpers.authenticated_request import get_authenticated_request

email_update_data = {"email": "test_email@email.com"}


@patch("angelia.resources.users.UserHandler")
def test_email_update(mock_handler: MagicMock) -> None:
    mock_handler.return_value.user_id = 1
    resp = get_authenticated_request(
        path="/v2/email_update", json=email_update_data, method="POST", user_id=1, channel="com.test.channel"
    )
    assert resp.status == HTTP_200


@patch("angelia.resources.users.UserHandler")
def test_delete_user(mock_handler: MagicMock) -> None:
    mock_handler.return_value.user_id = 1
    resp = get_authenticated_request(path="/v2/me", json=None, method="DELETE", user_id=1, channel="com.test.channel")
    assert resp.status == HTTP_202
