from unittest.mock import patch

from falcon import HTTP_200, HTTP_201, HTTP_202, HTTP_404

from tests.helpers.authenticated_request import get_authenticated_request

email_update_data = {"email": "test_email@email.com"}

@patch("app.resources.users.UserHandler")
def test_email_update(mock_handler):
    mock_handler.return_value.user_id = 1
    resp = get_authenticated_request(
        path="/v2/email_update", json=email_update_data, method="POST", user_id=1, channel="com.test.channel"
    )
    assert resp.status == HTTP_200


