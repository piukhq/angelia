from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.exc import DatabaseError
from app.handlers.base import BaseHandler
from app.hermes.models import Channel, User
from app.report import api_logger
from app.api.helpers.vault import get_current_token_secret
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

    def make_token(self, expiry=600):
        kid, secret = get_current_token_secret()
        tod = int(time())
        encoded_jwt = jwt.encode(
            {
                "sub": self.user_id,
                "channel": self.channel_id,
                "iat": tod,
                "exp": tod + expiry
            },
            key=secret,
            headers={"kid": kid},
            algorithm="HS512"
        )
        return encoded_jwt

    def make_access_token(self):
        print(self.grant_type, self.scope, self.external_user_id, self.email, self.channel_id, self.user_id)
        query = select(User).join(Channel, User.client_id == Channel.client_id).where(
                User.external_id == self.external_user_id,
                User.is_active.is_(True),
                Channel.bundle_id == self.channel_id
            )
        try:
            user_record = self.db_session.execute(query).all()
        except DatabaseError:
            api_logger.error("Unable to fetch loyalty plan records from database")
            raise falcon.HTTPInternalServerError

        if len(user_record) > 1:
            raise falcon.HTTPConflict
        if len(user_record) == 0:
            # Need to add user and get id
            pass
        else:
            self.user_id = user_record[0][0].id

        return self.make_token(self.access_life_time)

