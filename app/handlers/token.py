import base64
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from time import time

import falcon
import jwt
from sqlalchemy import select
from sqlalchemy.exc import DatabaseError

from app.api.auth import get_authenticated_client, get_authenticated_external_user_email, get_authenticated_user
from app.api.custom_error_handlers import UNAUTHORISED_CLIENT, UNSUPPORTED_GRANT_TYPE, TokenHTTPError
from app.handlers.base import BaseTokenHandler
from app.hermes.models import Channel, User
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
    access_life_time: int = 600
    refresh_life_time: int = 900

    def create_access_token(self):
        tod = int(time())
        encoded_jwt = jwt.encode(
            {"sub": self.user_id, "channel": self.channel_id, "iat": tod, "exp": tod + self.access_life_time},
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

    def process_refresh_token(self, req: falcon.Request):
        self.user_id = get_authenticated_user(req)
        self.client_id = get_authenticated_client(req)
        query = (
            select(User, Channel)
            .join(Channel, User.client_id == Channel.client_id)
            .where(
                User.id == self.user_id,
            )
        )
        try:
            user_channel_record = self.db_session.execute(query).all()
        except DatabaseError:
            api_logger.error(
                "Could get active user with external id {self.external_user_id} " "in channel {self.channel_id}"
            )
            raise falcon.HTTPInternalServerError

        user_data = user_channel_record[0][0]
        channel_data = user_channel_record[0][1]
        if len(user_channel_record) != 1 or not user_data.is_active or channel_data.bundle_id != self.channel_id:
            raise TokenHTTPError(UNAUTHORISED_CLIENT)
        self.refresh_life_time = channel_data.refresh_token_lifetime * 60
        self.access_life_time = channel_data.access_token_lifetime * 60

    def process_b2b_token(self, req: falcon.Request):
        self.email = get_authenticated_external_user_email(req)
        query = (
            select(User, Channel)
            .join(Channel, User.client_id == Channel.client_id)
            .where(
                User.external_id == self.external_user_id,
                User.email == self.email,
                User.is_active.is_(True),
                Channel.bundle_id == self.channel_id,
            )
        )
        try:
            user_channel_record = self.db_session.execute(query).all()
        except DatabaseError:
            api_logger.error(
                f"Could not get active user with external id {self.external_user_id} in channel {self.channel_id}"
            )
            raise falcon.HTTPInternalServerError

        if len(user_channel_record) > 1:
            raise falcon.HTTPConflict
        if len(user_channel_record) == 0:
            # Need to add user and get id
            query = select(Channel).where(Channel.bundle_id == self.channel_id)
            try:
                channel_record = self.db_session.execute(query).all()
            except DatabaseError:
                api_logger.error("Could not get channel {self.channel_id} when processing token and adding a user")
                raise falcon.HTTPInternalServerError

            try:
                channel_data = channel_record[0][0]
            except IndexError:
                api_logger.error(f"Could not get channel data for {self.channel_id} has that bundle been configured")
                raise TokenHTTPError(UNAUTHORISED_CLIENT)
            self.client_id = channel_data.client_id
            self.refresh_life_time = channel_data.refresh_token_lifetime * 60
            self.access_life_time = channel_data.access_token_lifetime * 60

            salt = base64.b64encode(os.urandom(16))[:8].decode("utf-8")
            user = User(
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
            )

            self.db_session.add(user)
            self.db_session.commit()
            self.user_id = user.id
        else:
            try:
                user_data = user_channel_record[0][0]
                channel_data = user_channel_record[0][1]
            except IndexError:
                api_logger.error(
                    f"Could not get user/channel data for {self.channel_id}. Has that bundle been configured"
                    f" or has user record with external id {self.external_user_id} corrupted"
                )
                raise TokenHTTPError(UNAUTHORISED_CLIENT)

            self.user_id = user_data.id
            self.client_id = user_data.client_id
            self.refresh_life_time = channel_data.refresh_token_lifetime * 60
            self.access_life_time = channel_data.access_token_lifetime * 60
