import typing
from unittest.mock import Mock, patch

import jwt
import pytest

from app.api.auth import AccessToken
from tests.authentication.helpers.token_helpers import create_refresh_token, setup_mock_request
from tests.factories import ChannelFactory, ServiceConsentFactory, UserFactory

if typing.TYPE_CHECKING:
    from unittest.mock import MagicMock

    from sqlalchemy.orm import Session

import falcon
from sqlalchemy import func, select

from app.handlers.token import TokenGen
from app.hermes.models import ServiceConsent, User


@pytest.fixture()
def token_gen_handler(db_session: "Session"):
    handler = TokenGen(
        db_session=db_session,
        external_user_id="testme",
        channel_id="com.test.channel",
        access_kid="test-kid",
        access_secret_key="some-key",
        grant_type="b2b",
        scope=["user"],
    )
    return handler


class TestTokenGen:
    @classmethod
    def setup_class(cls):
        cls.channel = "com.test.channel"
        cls.external_id = "testme"
        cls.email = "new@email.com"

        cls.secrets_dict = {"test_key-1": "my_secret_1"}
        cls.payload = {
            "sub": 39624,
            "channel": "com.test.wallet",
            "client_id": "dv18jwdwoFhjklsdvzxcPQslovceTQWBWEVlwdFGHikkkwdfff34wefw2zXAKlz",
            "grant_type": "b2b",
            "external_id": "test_user",
        }
        base_key = "test_key-1"
        cls.test_secret_key = f"refresh-{base_key}"  # refresh token must be prefixed with "refresh-"
        cls.base_key = base_key

    @patch("app.handlers.token.get_authenticated_external_user_email")
    def test_user_and_consent_created(
        self, mock_get_email: "MagicMock", db_session: "Session", token_gen_handler: TokenGen
    ):
        ChannelFactory()
        db_session.commit()

        mock_get_email.return_value = self.email
        mock_request = Mock(spec=falcon.Request)

        users_before = token_gen_handler.db_session.execute(select(User)).all()
        consents_before = token_gen_handler.db_session.execute(select(ServiceConsent)).all()

        assert users_before == []
        assert consents_before == []

        token_gen_handler.process_token(mock_request)

        users_after = token_gen_handler.db_session.execute(select(User)).all()
        consents_after = token_gen_handler.db_session.execute(select(ServiceConsent)).all()

        assert users_after
        assert consents_after

    @patch("app.handlers.token.get_authenticated_external_user_email")
    def test_existing_user(self, mock_get_email: "MagicMock", db_session: "Session", token_gen_handler: TokenGen):
        channel = ChannelFactory()
        db_session.flush()

        UserFactory(client=channel.client_application, external_id="testme", email=self.email)
        db_session.commit()

        mock_get_email.return_value = self.email
        mock_request = Mock(spec=falcon.Request)

        users_before = token_gen_handler.db_session.execute(select(User)).all()
        consents_before = token_gen_handler.db_session.execute(select(ServiceConsent)).all()

        token_gen_handler.process_token(mock_request)

        users_after = token_gen_handler.db_session.execute(select(User)).all()
        consents_after = token_gen_handler.db_session.execute(select(ServiceConsent)).all()

        assert users_after == users_before
        assert consents_after == consents_before

    @patch("app.handlers.token.get_authenticated_external_user_email")
    def test_user_and_consent_created_optional_email(
        self, mock_get_email: "MagicMock", db_session: "Session", token_gen_handler: TokenGen
    ):
        ChannelFactory()
        db_session.commit()

        mock_get_email.return_value = ""
        mock_request = Mock(spec=falcon.Request)

        users = token_gen_handler.db_session.scalar(select(func.count(User.id)))
        consents = token_gen_handler.db_session.scalar(select(func.count(ServiceConsent.user_id)))
        assert users == 0
        assert consents == 0

        token_gen_handler.process_token(mock_request)

        users = token_gen_handler.db_session.scalar(select(func.count(User.id)))
        consents = token_gen_handler.db_session.scalar(select(func.count(ServiceConsent.user_id)))
        assert users == 1
        assert consents == 1

    @patch("app.handlers.token.get_authenticated_external_user_email")
    def test_existing_user_optional_email(
        self, mock_get_email: "MagicMock", db_session: "Session", token_gen_handler: TokenGen
    ):
        channel = ChannelFactory()
        db_session.flush()

        user = UserFactory(client=channel.client_application, external_id="testme", email="")
        db_session.flush()
        ServiceConsentFactory(user_id=user.id)
        db_session.commit()

        mock_get_email.return_value = ""
        mock_request = Mock(spec=falcon.Request)

        users = token_gen_handler.db_session.scalar(select(func.count(User.id)))
        consents = token_gen_handler.db_session.scalar(select(func.count(ServiceConsent.user_id)))
        assert users == 1
        assert consents == 1

        token_gen_handler.process_token(mock_request)

        users = token_gen_handler.db_session.scalar(select(func.count(User.id)))
        consents = token_gen_handler.db_session.scalar(select(func.count(ServiceConsent.user_id)))
        assert users == 1
        assert consents == 1

    @patch("app.handlers.token.get_authenticated_external_user_email")
    def test_create_access_token_b2b_grant(
        self, mock_get_email: "MagicMock", token_gen_handler: TokenGen, db_session: "Session"
    ):
        ChannelFactory(is_trusted=True)
        db_session.commit()
        mock_get_email.return_value = ""
        mock_request = Mock(spec=falcon.Request)
        token_gen_handler.grant_type = "b2b"
        token_gen_handler.process_token(mock_request)

        access_token = token_gen_handler.create_access_token()

        decoded_token = jwt.decode(access_token, token_gen_handler.access_secret_key, algorithms=["HS512"])

        for claim in ["sub", "channel", "is_tester", "is_trusted_channel", "iat", "exp"]:
            assert claim in decoded_token

        assert decoded_token["is_trusted_channel"] is True
        assert 6 == len(decoded_token)

    @patch("app.handlers.token.get_authenticated_external_user_email")
    def test_create_access_token_refresh_grant(
        self, mock_get_email: "MagicMock", token_gen_handler: TokenGen, db_session: "Session"
    ):
        channel = ChannelFactory()
        user = UserFactory(client=channel.client_application, external_id="testme", email="")
        db_session.flush()

        mock_get_email.return_value = ""
        token_gen_handler.grant_type = "refresh_token"
        auth_token = create_refresh_token(self.base_key, self.secrets_dict, self.test_secret_key, self.payload)
        mock_request = setup_mock_request(auth_token, AccessToken)
        mock_request.context.auth_instance.auth_data = {"sub": user.id, "client_id": ""}
        token_gen_handler.process_token(mock_request)

        access_token = token_gen_handler.create_access_token()

        decoded_token = jwt.decode(access_token, token_gen_handler.access_secret_key, algorithms=["HS512"])

        for claim in ["sub", "channel", "is_tester", "is_trusted_channel", "iat", "exp"]:
            assert claim in decoded_token

        assert 6 == len(decoded_token)

    @patch("app.handlers.token.get_authenticated_external_user_email")
    def test_create_refresh_token_b2b_grant(
        self, mock_get_email: "MagicMock", token_gen_handler: TokenGen, db_session: "Session"
    ):
        ChannelFactory()
        db_session.commit()
        mock_get_email.return_value = ""
        mock_request = Mock(spec=falcon.Request)
        token_gen_handler.grant_type = "b2b"
        token_gen_handler.process_token(mock_request)

        access_token = token_gen_handler.create_refresh_token()

        decoded_token = jwt.decode(access_token, token_gen_handler.access_secret_key, algorithms=["HS512"])

        for claim in ["sub", "channel", "client_id", "grant_type", "external_id", "iat", "exp"]:
            assert claim in decoded_token

        assert 7 == len(decoded_token)

    @patch("app.handlers.token.get_authenticated_external_user_email")
    def test_create_refresh_token_refresh_grant(
        self, mock_get_email: "MagicMock", token_gen_handler: TokenGen, db_session: "Session"
    ):
        channel = ChannelFactory()
        user = UserFactory(client=channel.client_application, external_id="testme", email="")
        db_session.flush()

        mock_get_email.return_value = ""
        token_gen_handler.grant_type = "refresh_token"
        auth_token = create_refresh_token(self.base_key, self.secrets_dict, self.test_secret_key, self.payload)
        mock_request = setup_mock_request(auth_token, AccessToken)
        mock_request.context.auth_instance.auth_data = {"sub": user.id, "client_id": ""}
        token_gen_handler.process_token(mock_request)

        access_token = token_gen_handler.create_refresh_token()

        decoded_token = jwt.decode(access_token, token_gen_handler.access_secret_key, algorithms=["HS512"])

        for claim in ["sub", "channel", "client_id", "grant_type", "external_id", "iat", "exp"]:
            assert claim in decoded_token

        assert 7 == len(decoded_token)
