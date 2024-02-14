from typing import TYPE_CHECKING

from app.handlers.token import TokenGen
from tests.authentication.helpers.keys import private_key_rsa, public_key_rsa
from tests.factories import ChannelFactory

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class MockAuthConfig:
    channel: ChannelFactory
    user_id: int
    external_id: str | None
    email: str | None
    access_kid: str = "test-kid-1"
    access_secret_key: str = "some-key"
    public_secret_key: str
    private_secret_key: str = private_key_rsa
    scope: list[str]
    grant_type: str

    def __init__(
        self,
        channel: ChannelFactory,
        user_id: int = 1,
        external_id: str | None = "testme",
        email: str | None = "new@email.com",
        grant_type: str = "b2b",
        public_key: str = public_key_rsa,
    ) -> None:
        self.channel = channel
        self.user_id = user_id
        self.external_id = external_id
        self.email = email
        self.scope = ["user"]
        self.grant_type = grant_type
        self.public_secret_key = public_key

    @property
    def channel_id(self) -> str:
        return self.channel.bundle_id

    @property
    def secrets_dict(self) -> dict:
        return {"key": self.public_secret_key, "channel": self.channel_id}

    @property
    def access_life_time(self) -> int:
        return self.channel.access_token_lifetime * 60

    @property
    def refresh_life_time(self) -> int:
        return self.channel.refresh_token_lifetime * 60

    def mock_token_gen(
        self,
        db_session: "Session",
    ) -> TokenGen:
        return TokenGen(
            db_session=db_session,
            external_user_id=self.external_id or "",
            channel_id=self.channel.bundle_id,
            access_kid=self.access_kid,
            access_secret_key=self.access_secret_key,
            grant_type=self.grant_type,
            scope=["user"],
            is_trusted_channel=self.channel.is_trusted,
            user_id=self.user_id,
            access_life_time=self.access_life_time,
            refresh_life_time=self.refresh_life_time,
            client_id=self.channel.client_id,
        )
