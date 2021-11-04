from dataclasses import dataclass
from app.handlers.base import BaseHandler
from sqlalchemy import update
from app.hermes.models import User
from sqlalchemy.exc import DatabaseError
import falcon

from app.report import api_logger


@dataclass
class UserHandler(BaseHandler):
    new_email: str = None

    def handle_email_update(self):

        query = update(User).where(User.id == self.user_id).values(email=self.new_email)
        try:
            self.db_session.execute(query)
        except DatabaseError:
            api_logger.error("Unable to update user information in Database")
            raise falcon.HTTPInternalServerError

        self.db_session.commit()
