import typing
from unittest.mock import patch

import falcon
import pytest
from sqlalchemy.future import select

from angelia.hermes.models import Channel, User
from tests.factories import ChannelFactory, ClientApplicationFactory, OrganisationFactory, UserFactory
from tests.helpers.authenticated_request import get_authenticated_request

if typing.TYPE_CHECKING:
    from unittest.mock import MagicMock

    from sqlalchemy.orm import Session


@pytest.fixture(scope="function")
def channel(db_session: "Session") -> Channel:
    channel = ChannelFactory()
    db_session.commit()
    return channel


@pytest.fixture(scope="function")
def user(db_session: "Session", channel: Channel) -> User:
    user = UserFactory(email="whatever@whatever.com", client=channel.client_application)
    db_session.commit()
    return user


def test_on_post_email_update_incorrect_payload_422(db_session: "Session") -> None:
    resp = get_authenticated_request(
        path="/v2/email_update", json={"dead": "beef"}, method="POST", user_id=1, channel="com.test.channel"
    )
    assert resp.status == falcon.HTTP_422
    assert resp.json["error_message"] == "Could not validate fields"
    assert resp.json["error_slug"] == "FIELD_VALIDATION_ERROR"
    assert resp.json["fields"] == ["extra keys not allowed @ data['dead']"]


def test_on_post_email_update_malformed_payload_400(db_session: "Session") -> None:
    resp = get_authenticated_request(
        path="/v2/email_update", body=b"\xf0\x9f\x92\xa9", method="POST", user_id=1, channel="com.test.channel"
    )
    assert resp.status == falcon.HTTP_400
    assert resp.json == {
        "error_message": "Invalid JSON",
        "error_slug": "MALFORMED_REQUEST",
    }


def test_on_post_email_update_200(db_session: "Session", user: User) -> None:
    user_id = user.id
    resp = get_authenticated_request(
        path="/v2/email_update",
        json={"email": "validemail@test.com"},
        method="POST",
        user_id=user_id,
        channel="com.test.channel",
    )
    assert resp.status == falcon.HTTP_200
    assert resp.json == {"id": user_id}
    assert db_session.execute(
        select(User).where(User.id == user_id, User.email == "validemail@test.com")
    ).scalar_one_or_none()


def test_on_post_email_update_409(db_session: "Session", user: User, channel: Channel) -> None:
    other_user = UserFactory(email="other@bink.com", client=channel.client_application)
    db_session.commit()

    resp = get_authenticated_request(
        path="/v2/email_update",
        json={"email": other_user.email},
        method="POST",
        user_id=user.id,
        channel="com.test.channel",
    )
    assert resp.status == falcon.HTTP_409
    assert resp.json == {
        "error_message": "This email is already in use for this channel",
        "error_slug": "DUPLICATE_EMAIL",
    }


def test_on_post_email_update_other_channel_200(db_session: "Session", user: User, channel: Channel) -> None:
    organisation = OrganisationFactory(name="whatever")
    client_app = ClientApplicationFactory(organisation=organisation, client_id="whatever", name="whatever")
    ChannelFactory(bundle_id="com.whatever.other", client_application=client_app)
    other_user = UserFactory(email="other@bink.com", client=client_app)
    db_session.commit()

    user_id = user.id
    resp = get_authenticated_request(
        path="/v2/email_update",
        json={"email": other_user.email},
        method="POST",
        user_id=user_id,
        channel="com.test.channel",
    )
    assert resp.status == falcon.HTTP_200
    assert resp.json == {"id": user_id}


def test_on_post_email_update_multuple_users_same_email_address(
    db_session: "Session", user: User, channel: Channel
) -> None:
    other_email = "other@bink.com"
    UserFactory(email=other_email, client=channel.client_application, external_id="x")
    UserFactory(email=other_email, client=channel.client_application, external_id="y")
    db_session.commit()

    resp = get_authenticated_request(
        path="/v2/email_update",
        json={"email": other_email},
        method="POST",
        user_id=user.id,
        channel="com.test.channel",
    )
    assert resp.status == falcon.HTTP_500
    assert resp.json == {
        "error_message": "500 Internal Server Error",
        "error_slug": "INTERNAL_SERVER_ERROR",
    }


@patch("angelia.handlers.user.send_message_to_hermes")
def test_on_delete_me(
    mock_send_message_to_hermes: "MagicMock", db_session: "Session", user: User, channel: Channel
) -> None:
    user_id = user.id
    resp = get_authenticated_request(
        path="/v2/me",
        method="DELETE",
        user_id=user_id,
        channel="com.test.channel",
    )
    assert resp.status == falcon.HTTP_202
    assert not resp.json
    mock_send_message_to_hermes.assert_called_once_with(
        "delete_user",
        {"user_id": user_id, "channel_slug": "com.test.channel"},
    )
