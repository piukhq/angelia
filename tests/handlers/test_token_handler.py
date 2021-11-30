import typing
from unittest.mock import Mock, patch

from tests.authentication.helpers.test_jwtRS512 import private_key
from tests.factories import ChannelFactory, UserFactory

if typing.TYPE_CHECKING:
    from unittest.mock import MagicMock

    from sqlalchemy.orm import Session

import falcon
from sqlalchemy import select

from app.handlers.token import TokenGen
from app.hermes.models import ServiceConsent, User


@patch("app.handlers.token.get_authenticated_external_user_email")
def test_user_and_consent_created(mock_get_email: "MagicMock", db_session: "Session"):

    channel_id = "com.test.channel"
    external_id = "testme"
    email = "new@email.com"

    ChannelFactory()
    db_session.commit()

    handler = TokenGen(
        db_session=db_session,
        external_user_id=external_id,
        channel_id=channel_id,
        access_kid="test-kid",
        access_secret_key=private_key,
        grant_type="b2b",
        scope=["user"],
    )

    mock_get_email.return_value = email

    mock_request = Mock(spec=falcon.Request)

    users_before = handler.db_session.execute(select(User)).all()
    consents_before = handler.db_session.execute(select(ServiceConsent)).all()

    assert users_before == []
    assert consents_before == []

    handler.process_token(mock_request)

    users_after = handler.db_session.execute(select(User)).all()
    consents_after = handler.db_session.execute(select(ServiceConsent)).all()

    assert users_after
    assert consents_after


@patch("app.handlers.token.get_authenticated_external_user_email")
def test_existing_user(mock_get_email: "MagicMock", db_session: "Session"):

    channel_id = "com.test.channel"
    external_id = "testme"
    email = "new@email.com"

    channel = ChannelFactory()
    db_session.flush()

    UserFactory(client=channel.client_application, external_id="testme", email=email)
    db_session.commit()

    handler = TokenGen(
        db_session=db_session,
        external_user_id=external_id,
        channel_id=channel_id,
        access_kid="test-kid",
        access_secret_key=private_key,
        grant_type="b2b",
        scope=["user"],
    )

    mock_get_email.return_value = email

    mock_request = Mock(spec=falcon.Request)

    users_before = handler.db_session.execute(select(User)).all()
    consents_before = handler.db_session.execute(select(ServiceConsent)).all()

    handler.process_token(mock_request)

    users_after = handler.db_session.execute(select(User)).all()
    consents_after = handler.db_session.execute(select(ServiceConsent)).all()

    assert users_after == users_before
    assert consents_after == consents_before
