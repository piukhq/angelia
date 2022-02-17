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
from tests.helpers.database_set_up import setup_database


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
                assert len(mock_send_message.call_args_list) == 2  # mapped_history followed by refresh_update
                sent_message = mock_send_message.call_args_list[0].kwargs  # 1st is mapped_history
                sent_body = loads(sent_message["payload"])
                assert sent_message["headers"]["X-http-path"] == "mapped_history"
                assert sent_body["user"] == external_id
                assert sent_body["channel"] == channel
                assert sent_body["event"] == "create"
                assert sent_body["table"] == "user"
                assert sent_body["change"] is None
                payload = sent_body["payload"]
                assert payload["email"] == email
                assert payload["external_id"] == external_id


def test_user_update(db_session: "Session"):
    channels, users = setup_database(db_session)
    user = users["bank2_2"]
    user_id = user.id
    email_update_data = {"email": "test_email@email.com"}
    with patch("app.messaging.sender._send_message") as mock_send_message:
        mock_send_message.return_value = None
        resp = get_authenticated_request(
            path="/v2/email_update", json=email_update_data, method="POST", user_id=user_id, channel="com.bank2.test"
        )
        assert resp.status == HTTP_200
        assert len(mock_send_message.call_args_list) == 1
        sent_message = mock_send_message.call_args_list[0].kwargs
        assert sent_message["headers"]["X-http-path"] == "sql_history"
        sent_body = loads(sent_message["payload"])
        assert sent_body["user"] == str(user_id)
        assert sent_body["channel"] == "com.bank2.test"
        assert sent_body["event"] == "update"
        assert sent_body["table"] == "user"
        assert sent_body["id"] == user_id
        assert sent_body["change"] == "email"


def test_delete_user_no_history(db_session: "Session"):
    channels, users = setup_database(db_session)
    user = users["bank2_2"]
    with patch("app.messaging.sender._send_message") as mock_send_message:
        mock_send_message.return_value = None
        resp = get_authenticated_request(
            path="/v2/me", json=None, method="DELETE", user_id=user.id, channel="com.bank2.test"
        )
        # No History request is sent just delete_user hermes request
        assert len(mock_send_message.call_args_list) == 1
        sent_message = mock_send_message.call_args_list[0].kwargs
        assert sent_message["headers"]["X-http-path"] == "delete_user"
        assert resp.status == HTTP_202
