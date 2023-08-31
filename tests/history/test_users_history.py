import typing

import kombu.exceptions

from app.api.shared_data import SharedData
from tests.factories import ChannelFactory, LoyaltyCardFactory, UserFactory

if typing.TYPE_CHECKING:
    from sqlalchemy.orm import Session

from unittest.mock import MagicMock, patch

from falcon import HTTP_200, HTTP_202

from tests.authentication.helpers.keys import private_key_rsa, public_key_rsa
from tests.authentication.helpers.token_helpers import create_b2b_token
from tests.helpers.authenticated_request import get_authenticated_request, get_client
from tests.helpers.database_set_up import setup_database


def test_user_add(db_session: "Session") -> None:
    channel_obj = ChannelFactory()
    db_session.commit()
    external_id = "test_external_id"
    channel = channel_obj.bundle_id
    email = "customer1@test.com"
    kid = "test-1"
    b2b = create_b2b_token(private_key_rsa, sub=external_id, kid=kid, email=email)
    json = {"grant_type": "b2b", "scope": ["user"]}

    request = MagicMock()
    request.context.auth_instance.auth_data = {"sub": external_id, "channel": channel}
    SharedData(request, MagicMock(), MagicMock(), MagicMock())

    with patch("app.api.auth.dynamic_get_b2b_token_secret") as mock_get_secret:
        mock_get_secret.return_value = {"key": public_key_rsa, "channel": channel}
        with patch("app.resources.token.get_current_token_secret") as current_token:
            current_token.return_value = kid, "test_access_secret"
            with patch("app.messaging.sender.sending_service") as mock_sending_service:
                mock_producer = MagicMock()
                mock_producer.send_message.return_value = None
                mock_sending_service.queues = {"HERMES": mock_producer}
                resp = get_client().simulate_request(
                    path="/v2/token", json=json, headers={"Authorization": b2b}, method="POST"
                )
                assert resp.status == HTTP_200
                assert (
                    len(mock_producer.send_message.call_args_list) == 3
                )  # mapped_history followed by update last_accessed followed by refresh_balances
                sent_message = mock_producer.send_message.call_args_list[0].kwargs  # 1st is mapped_history
                sent_body = sent_message["payload"]
                assert sent_message["headers"]["X-http-path"] == "mapped_history"
                assert sent_body["user_id"] == external_id
                assert sent_body["channel_slug"] == channel
                assert sent_body["event"] == "create"
                assert sent_body["table"] == "user"
                assert not sent_body["change"]
                payload = sent_body["payload"]
                assert payload["email"] == email
                assert payload["external_id"] == external_id


def test_user_update(db_session: "Session") -> None:
    channels, users = setup_database(db_session)
    user = users["bank2_2"]
    user_id = user.id
    email_update_data = {"email": "test_email@email.com"}
    with patch("app.messaging.sender.sending_service") as mock_sending_service:
        mock_producer = MagicMock()
        mock_producer.send_message.return_value = None
        mock_sending_service.queues = {"HERMES": mock_producer}
        resp = get_authenticated_request(
            path="/v2/email_update", json=email_update_data, method="POST", user_id=user_id, channel="com.bank2.test"
        )
        assert resp.status == HTTP_200
        assert len(mock_producer.send_message.call_args_list) == 1
        sent_message = mock_producer.send_message.call_args_list[0].kwargs
        assert sent_message["headers"]["X-http-path"] == "sql_history"
        sent_body = sent_message["payload"]
        assert sent_body["user_id"] == str(user_id)
        assert sent_body["channel_slug"] == "com.bank2.test"
        assert sent_body["event"] == "update"
        assert sent_body["table"] == "user"
        assert sent_body["id"] == user_id
        assert sent_body["change"] == "email"


def test_delete_user_no_history(db_session: "Session") -> None:
    channels, users = setup_database(db_session)
    user = users["bank2_2"]
    with patch("app.messaging.sender.sending_service") as mock_sending_service:
        mock_producer = MagicMock()
        mock_producer.send_message.return_value = None
        mock_sending_service.queues = {"HERMES": mock_producer}
        resp = get_authenticated_request(
            path="/v2/me", json=None, method="DELETE", user_id=user.id, channel="com.bank2.test"
        )
        # No History request is sent just delete_user hermes request
        assert len(mock_producer.send_message.call_args_list) == 1
        sent_message = mock_producer.send_message.call_args_list[0].kwargs
        assert sent_message["headers"]["X-http-path"] == "delete_user"
        assert resp.status == HTTP_202


@patch("app.hermes.db.send_message_to_hermes")
def test_history_sessions_send_hermes_messages(mock_send_hermes_msg: MagicMock, db_session: "Session") -> None:
    request = MagicMock()
    request.context.auth_instance.auth_data = {"sub": 1, "channel": "com.bink.whatever"}
    SharedData(request, MagicMock(), MagicMock(), MagicMock())
    user = UserFactory()

    # Create User
    db_session.add(user)
    db_session.commit()

    # Update and Create in single transaction
    loyalty_card = LoyaltyCardFactory()
    user.email = "updated@email.com"

    db_session.add(loyalty_card)
    db_session.add(user)
    db_session.commit()

    # Delete
    db_session.delete(user)
    db_session.commit()

    assert mock_send_hermes_msg.call_count == 4

    # The messages should be in order of each transaction.
    # If there are multiple operations in a single transaction then updates are executed before creates,
    # regardless of the order of db_session.add()
    for event, args in zip(("create", "update", "create", "delete"), mock_send_hermes_msg.call_args_list, strict=True):
        assert args.args[0] == "mapped_history"
        assert args.args[1]["event"] == event


@patch("app.hermes.db.send_message_to_hermes")
def test_history_sessions_retries_on_failure(mock_send_hermes_msg: MagicMock, db_session: "Session") -> None:
    request = MagicMock()
    request.context.auth_instance.auth_data = {"sub": 1, "channel": "com.bink.whatever"}
    SharedData(request, MagicMock(), MagicMock(), MagicMock())
    user = UserFactory()

    mock_send_hermes_msg.side_effect = [
        kombu.exceptions.ConnectionError("Can't connect to queue"),  # AMQP error
        kombu.exceptions.OperationalError("Something has gone horribly wrong"),  # Kombu error
        None,  # Success
    ]

    # Create User
    db_session.add(user)
    db_session.commit()

    assert mock_send_hermes_msg.call_count == 3
    for event, args in zip(("create", "create", "create"), mock_send_hermes_msg.call_args_list, strict=True):
        assert args.args[0] == "mapped_history"
        assert args.args[1]["event"] == event


@patch("app.hermes.db.send_message_to_hermes")
def test_history_sessions_re_queue_after_failed_retries(mock_send_hermes_msg: MagicMock, db_session: "Session") -> None:
    request = MagicMock()
    request.context.auth_instance.auth_data = {"sub": 1, "channel": "com.bink.whatever"}
    SharedData(request, MagicMock(), MagicMock(), MagicMock())
    user = UserFactory()
    loyalty_card = LoyaltyCardFactory()

    # Default retry count is 3 so this should re-queue after the 3rd failure
    mock_send_hermes_msg.side_effect = [
        kombu.exceptions.ConnectionError("Can't connect to queue"),  # AMQP error
        kombu.exceptions.OperationalError("Something has gone horribly wrong"),  # Kombu error
        kombu.exceptions.OperationalError("Something has gone horribly wrong again"),  # Kombu error
        None,  # Success user 2
        None,  # Success user 1
    ]

    # Create User
    db_session.add(user)
    db_session.add(loyalty_card)
    db_session.commit()

    assert mock_send_hermes_msg.call_count == 5

    # The messages should generally be in order of each operation but this can change if they're in a
    # single transaction based on how sqlalchemy handles inserts
    # e.g in this case scheme accounts are always inserted before users
    for table, args in zip(
        ("scheme_schemeaccount", "scheme_schemeaccount", "scheme_schemeaccount", "user", "scheme_schemeaccount"),
        mock_send_hermes_msg.call_args_list,
        strict=True,
    ):
        assert args.args[0] == "mapped_history"
        assert args.args[1]["table"] == table
