import typing
from json import loads

from tests.factories import ChannelFactory

if typing.TYPE_CHECKING:
    from sqlalchemy.orm import Session

from unittest.mock import patch

from falcon import HTTP_200, HTTP_202

from tests.authentication.helpers.test_jwtRS512 import private_key, public_key
from tests.authentication.helpers.token_helpers import create_b2b_token
from tests.helpers.authenticated_request import get_authenticated_request, get_client

email_update_data = {"email": "test_email@email.com"}


def test_user_add(db_session: "Session"):
    channel_obj = ChannelFactory()
    db_session.commit()
    external_id = "test_external_id"
    channel = channel_obj.bundle_id
    email = "customer1@test.com"
    kid = "test-1"
    b2b = create_b2b_token(private_key, sub=external_id, kid=kid, email=email)
    json = {"grant_type": "b2b", "scope": ["user"]}
    with patch("app.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret:
        mock_get_secret.return_value = {"key": public_key, "channel": channel}
        with patch("app.resources.token.get_current_token_secret") as current_token:
            current_token.return_value = kid, "test_access_secret"
            with patch("app.messaging.sender._send_message") as mock_send_message:
                mock_send_message.return_value = None
                resp = get_client().simulate_request(
                    path="/v2/token", json=json, headers={"Authorization": b2b}, method="POST"
                )
                assert resp.status == HTTP_200
                sent_message = mock_send_message.call_args_list[0].kwargs
                sent_body = loads(sent_message["payload"])
                assert sent_message["headers"]["X-http-path"] == "history"
                assert sent_body["user"] == external_id
                assert sent_body["channel"] == channel
                assert sent_body["event"] == "create"
                assert sent_body["table"] == "user"
                payload = sent_body["payload"]
                assert payload["email"] == email
                assert payload["external_id"] == external_id


@patch("app.resources.users.UserHandler")
def test_email_update(mock_handler):
    mock_handler.return_value.user_id = 1
    resp = get_authenticated_request(
        path="/v2/email_update", json=email_update_data, method="POST", user_id=1, channel="com.test.channel"
    )
    assert resp.status == HTTP_200


@patch("app.resources.users.UserHandler")
def test_delete_user(mock_handler):
    mock_handler.return_value.user_id = 1
    resp = get_authenticated_request(path="/v2/me", json=None, method="DELETE", user_id=1, channel="com.test.channel")
    assert resp.status == HTTP_202
