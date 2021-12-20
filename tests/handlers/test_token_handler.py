import typing
from unittest.mock import Mock, patch

from tests.authentication.helpers.test_jwtRS512 import private_key
from tests.factories import ChannelFactory, ServiceConsentFactory, UserFactory

if typing.TYPE_CHECKING:
    from unittest.mock import MagicMock

    from sqlalchemy.orm import Session

import falcon
from sqlalchemy import func, select

from app.handlers.token import TokenGen
from app.hermes.models import ServiceConsent, User


class TestTokenGen:
    @classmethod
    def setup_class(cls):
        cls.channel = "com.test.channel"
        cls.external_id = "testme"
        cls.email = "new@email.com"

    @patch("app.handlers.token.get_authenticated_external_user_email")
    def test_user_and_consent_created(self, mock_get_email: "MagicMock", db_session: "Session"):
        ChannelFactory()
        db_session.commit()

        handler = TokenGen(
            db_session=db_session,
            external_user_id=self.external_id,
            channel_id=self.channel,
            access_kid="test-kid",
            access_secret_key=private_key,
            grant_type="b2b",
            scope=["user"],
        )

        mock_get_email.return_value = self.email

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
    def test_existing_user(self, mock_get_email: "MagicMock", db_session: "Session"):
        channel = ChannelFactory()
        db_session.flush()

        UserFactory(client=channel.client_application, external_id="testme", email=self.email)
        db_session.commit()

        handler = TokenGen(
            db_session=db_session,
            external_user_id=self.external_id,
            channel_id=self.channel,
            access_kid="test-kid",
            access_secret_key=private_key,
            grant_type="b2b",
            scope=["user"],
        )

        mock_get_email.return_value = self.email

        mock_request = Mock(spec=falcon.Request)

        users_before = handler.db_session.execute(select(User)).all()
        consents_before = handler.db_session.execute(select(ServiceConsent)).all()

        handler.process_token(mock_request)

        users_after = handler.db_session.execute(select(User)).all()
        consents_after = handler.db_session.execute(select(ServiceConsent)).all()

        assert users_after == users_before
        assert consents_after == consents_before

    @patch("app.handlers.token.get_authenticated_external_user_email")
    def test_user_and_consent_created_optional_email(self, mock_get_email: "MagicMock", db_session: "Session"):
        ChannelFactory()
        db_session.commit()

        handler = TokenGen(
            db_session=db_session,
            external_user_id=self.external_id,
            channel_id=self.channel,
            access_kid="test-kid",
            access_secret_key=private_key,
            grant_type="b2b",
            scope=["user"],
        )

        mock_get_email.return_value = ""
        mock_request = Mock(spec=falcon.Request)

        users = handler.db_session.scalar(select(func.count(User.id)))
        consents = handler.db_session.scalar(select(func.count(ServiceConsent.user_id)))
        assert users == 0
        assert consents == 0

        handler.process_token(mock_request)

        users = handler.db_session.scalar(select(func.count(User.id)))
        consents = handler.db_session.scalar(select(func.count(ServiceConsent.user_id)))
        assert users == 1
        assert consents == 1

    @patch("app.handlers.token.get_authenticated_external_user_email")
    def test_existing_user_optional_email(self, mock_get_email: "MagicMock", db_session: "Session"):
        channel = ChannelFactory()
        db_session.flush()

        user = UserFactory(client=channel.client_application, external_id="testme", email="")
        db_session.flush()
        ServiceConsentFactory(user_id=user.id)
        db_session.commit()

        handler = TokenGen(
            db_session=db_session,
            external_user_id=self.external_id,
            channel_id=self.channel,
            access_kid="test-kid",
            access_secret_key=private_key,
            grant_type="b2b",
            scope=["user"],
        )

        mock_get_email.return_value = ""
        mock_request = Mock(spec=falcon.Request)

        users = handler.db_session.scalar(select(func.count(User.id)))
        consents = handler.db_session.scalar(select(func.count(ServiceConsent.user_id)))
        assert users == 1
        assert consents == 1

        handler.process_token(mock_request)

        users = handler.db_session.scalar(select(func.count(User.id)))
        consents = handler.db_session.scalar(select(func.count(ServiceConsent.user_id)))
        assert users == 1
        assert consents == 1
