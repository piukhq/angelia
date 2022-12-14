import base64
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from time import time

import arrow
import falcon
import jwt
from sqlalchemy import func, select
from sqlalchemy.exc import DatabaseError, NoResultFound

from app.api.auth import (
    get_authenticated_external_user_email,
    get_authenticated_token_client,
    get_authenticated_token_user,
)
from app.api.custom_error_handlers import (
    INVALID_CLIENT,
    INVALID_GRANT,
    UNAUTHORISED_CLIENT,
    UNSUPPORTED_GRANT_TYPE,
    TokenHTTPError,
)
from app.handlers.base import BaseTokenHandler
from app.hermes.models import Channel, ServiceConsent, User
from app.messaging.sender import send_message_to_hermes
from app.report import api_logger


@dataclass
class TokenGen(BaseTokenHandler):
    grant_type: str
    channel_id: str
    scope: list
    external_user_id: str
    access_kid: str
    access_secret_key: str
    user_id: int = None
    email: str = None
    client_id: str = None
    is_tester: bool = False
    is_trusted_channel: bool = False
    access_life_time: int = 600
    refresh_life_time: int = 900

    def create_access_token(self):
        tod = int(time())
        encoded_jwt = jwt.encode(
            {
                "sub": self.user_id,
                "channel": self.channel_id,
                "is_tester": self.is_tester,
                "is_trusted_channel": self.is_trusted_channel,
                "iat": tod,
                "exp": tod + self.access_life_time,
            },
            key=self.access_secret_key,
            headers={"kid": self.access_kid},
            algorithm="HS512",
        )
        return encoded_jwt

    def create_refresh_token(self):
        tod = int(time())
        encoded_jwt = jwt.encode(
            {
                "sub": self.user_id,
                "channel": self.channel_id,
                "client_id": self.client_id,
                "grant_type": self.grant_type,
                "external_id": self.external_user_id,
                "iat": tod,
                "exp": tod + self.refresh_life_time,
            },
            key=self.access_secret_key,
            headers={"kid": f"refresh-{self.access_kid}"},
            algorithm="HS512",
        )
        return encoded_jwt

    def process_token(self, req: falcon.Request):
        if self.grant_type == "b2b":
            self.process_b2b_token(req)
        elif self.grant_type == "refresh_token":
            self.process_refresh_token(req)
        else:
            raise TokenHTTPError(UNSUPPORTED_GRANT_TYPE)

        # update last_accessed time if I am a good user
        if self.user_id:
            self.update_access_time()

    def process_refresh_token(self, req: falcon.Request):
        self.user_id = get_authenticated_token_user(req)
        self.client_id = get_authenticated_token_client(req)
        query = (
            select(User, Channel)
            .join(Channel, User.client_id == Channel.client_id)
            .where(User.id == self.user_id)
            .where(Channel.bundle_id == self.channel_id)
        )
        try:
            user_channel_record = self.db_session.execute(query).all()
        except DatabaseError as e:
            api_logger.error(
                f"DatabaseError: When refreshing token for B2B user, external id = {self.external_user_id},"
                f" channel = {self.channel_id}, error = {e}"
            )
            raise falcon.HTTPInternalServerError

        if len(user_channel_record) != 1:
            api_logger.error(
                f"DatabaseError: When refreshing token for B2B user, external id = {self.external_user_id}"
                f" Duplicate bundle_id found for channel_id = {self.channel_id}"
            )
            raise falcon.HTTPInternalServerError

        user_data = user_channel_record[0][0]
        channel_data = user_channel_record[0][1]

        if not user_data.is_active:
            raise TokenHTTPError(UNAUTHORISED_CLIENT)

        self._set_token_data(user_data, channel_data)

    def process_b2b_token(self, req: falcon.Request):
        query = (
            select(User, Channel)
            .join(Channel, User.client_id == Channel.client_id)
            .where(
                User.external_id == self.external_user_id,
                User.is_active.is_(True),
                Channel.bundle_id == self.channel_id,
            )
        )
        try:
            user_channel_record = self.db_session.execute(query).all()
        except DatabaseError as e:
            api_logger.error(
                "Database Error: When looking up user for B2B token processing, user external id = "
                f"{self.external_user_id}, channel = {self.channel_id}, error = {e}"
            )
            raise falcon.HTTPInternalServerError

        if len(user_channel_record) > 1:
            raise falcon.HTTPConflict
        if len(user_channel_record) == 0:
            # Need to add user and get id
            query = select(Channel).where(Channel.bundle_id == self.channel_id)
            try:
                channel_data = self.db_session.execute(query).scalar_one()
            except (DatabaseError, NoResultFound):
                api_logger.error(f"Could not get channel data for {self.channel_id}. Has this bundle been configured?")
                raise TokenHTTPError(UNAUTHORISED_CLIENT)

            self.email = get_authenticated_external_user_email(req, email_required=channel_data.email_required)
            if self.email:
                self._validate_if_email_exists(channel_data)

            self.client_id = channel_data.client_id

            salt = base64.b64encode(os.urandom(16))[:8].decode("utf-8")
            user_data = User(
                email=self.email,
                external_id=self.external_user_id,
                client_id=self.client_id,
                password=f"invalid$1${salt}${base64.b64encode(os.urandom(16)).decode('utf-8')}",
                uid=uuid.uuid4(),
                is_superuser=False,
                is_active=True,
                is_staff=False,
                is_tester=False,
                date_joined=datetime.now(timezone.utc),
                salt=salt,
                delete_token="",
                bundle_id=self.channel_id,
                last_accessed=arrow.utcnow().isoformat(),
            )

            self.db_session.add(user_data)
            self.db_session.flush()
            self.db_session.refresh(user_data)

            consent = ServiceConsent(user_id=user_data.id, latitude=None, longitude=None, timestamp=datetime.now())

            self.db_session.add(consent)

            self.db_session.commit()
        else:
            try:
                user_data = user_channel_record[0][0]
                channel_data = user_channel_record[0][1]
            except IndexError:
                api_logger.error(
                    f"Could not get user/channel data for {self.channel_id}. Has this bundle been configured"
                    f" or has user record with external id {self.external_user_id} been corrupted?"
                )
                raise TokenHTTPError(UNAUTHORISED_CLIENT)

            self.email = get_authenticated_external_user_email(req, email_required=channel_data.email_required)

            if channel_data.email_required and self.email.lower() != user_data.email.lower():
                api_logger.error(
                    f'Client email in B2B token "{self.email.lower()}" does not match "{user_data.email.lower()}" '
                    "in user record. Has the client forgotten to update the email using the api?"
                )
                raise TokenHTTPError(INVALID_CLIENT)

        self.user_id = user_data.id
        self.client_id = user_data.client_id
        self._set_token_data(user_data, channel_data)

    def _set_token_data(self, user_data: User, channel_data: Channel) -> None:
        self.is_tester = user_data.is_tester
        self.is_trusted_channel = channel_data.is_trusted
        self.refresh_life_time = channel_data.refresh_token_lifetime * 60
        self.access_life_time = channel_data.access_token_lifetime * 60

    def _validate_if_email_exists(self, channel_data):
        query = select(func.count(User.id)).where(
            User.client_id == channel_data.client_id, User.email == self.email, User.delete_token == ""
        )
        try:
            num_matching_users = self.db_session.execute(query).scalar()
        except DatabaseError:
            api_logger.error(f"Could not get channel {self.channel_id} when processing token and adding a user")
            raise falcon.HTTPInternalServerError

        if num_matching_users > 0:
            raise TokenHTTPError(INVALID_GRANT)

    def refresh_balances(self) -> None:
        """
        Sends message to hermes via rabbitMQ to request a balance refresh
        """
        user_data = {
            "user_id": self.user_id,
            "channel_slug": self.channel_id,
        }
        send_message_to_hermes("refresh_balances", user_data)

    def update_access_time(self) -> None:
        session_data = {
            "time": arrow.utcnow().isoformat(),
            "user_id": self.user_id,
            "token_type": self.grant_type,
            "channel_slug": self.channel_id,
        }

        send_message_to_hermes("user_session", session_data)
