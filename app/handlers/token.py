from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.exc import DatabaseError
from app.handlers.base import BaseHandler
from app.hermes.models import Channel, User
from app.report import api_logger
from time import time
import falcon
import jwt


@dataclass
class TokenGen(BaseHandler):
    grant_type: str
    scope: list
    external_user_id: str
    email: str
    refresh_life_time: int
    access_life_time: int
    access_kid: str
    access_secret_key: str

    def create_access_token(self):
        tod = int(time())
        encoded_jwt = jwt.encode(
            {
                "sub": self.user_id,
                "channel": self.channel_id,
                "iat": tod,
                "exp": tod + self.access_life_time
            },
            key=self.access_secret_key,
            headers={"kid": self.access_kid},
            algorithm="HS512"
        )
        return encoded_jwt

    def create_refresh_token(self):
        tod = int(time())
        encoded_jwt = jwt.encode(
            {
                "sub": self.user_id,
                "channel": self.channel_id,
                "type": 'refresh',
                "email": self.email,
                "grant_type": self.grant_type,
                "external_id": self.external_user_id,
                "iat": tod,
                "exp": tod + self.refresh_life_time
            },
            key=self.access_secret_key,
            headers={"kid": self.access_kid},
            algorithm="HS512"
        )
        return encoded_jwt

    def verify_client_token(self):
        print(self.grant_type, self.scope, self.external_user_id, self.email, self.channel_id, self.user_id)
        query = select(User).join(Channel, User.client_id == Channel.client_id).where(
                User.external_id == self.external_user_id,
                User.is_active.is_(True),
                Channel.bundle_id == self.channel_id
            )
        try:
            user_record = self.db_session.execute(query).all()
        except DatabaseError:
            api_logger.error("Could get active user with external id {self.external_user_id} "
                             "in channel {self.channel_id}")
            raise falcon.HTTPInternalServerError

        if len(user_record) > 1:
            raise falcon.HTTPConflict
        if len(user_record) == 0:
            # Need to add user and get id
            pass
        else:
            self.user_id = user_record[0][0].id
