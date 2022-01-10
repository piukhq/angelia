from dataclasses import dataclass

import falcon
from sqlalchemy import select, update
from sqlalchemy.exc import DatabaseError

from app.handlers.base import BaseHandler
from app.hermes.models import Channel, User
from app.messaging.sender import send_message_to_hermes
from app.report import api_logger
from app.api.exceptions import ResourceNotFoundError


@dataclass
class UserHandler(BaseHandler):
    new_email: str = None

    def handle_email_update(self) -> None:

        self.check_for_existing_email()

        query = update(User).where(User.id == self.user_id).values(email=self.new_email)
        try:
            self.db_session.execute(query)
        except DatabaseError:
            api_logger.error("Unable to update user information in Database")
            raise falcon.HTTPInternalServerError

        self.db_session.commit()

    def check_for_existing_email(self) -> None:
        get_user_email = (
            select(User)
            .join(Channel, Channel.client_id == User.client_id)
            .where(Channel.bundle_id == self.channel_id, User.email == self.new_email, User.delete_token == "")
        )

        existing_user_with_email = self.db_session.execute(get_user_email).all()

        if len(existing_user_with_email) > 1:
            api_logger.error(f"Multiple users found with email {self.new_email} for channel {self.channel_id}.")
            raise falcon.HTTPInternalServerError

        if existing_user_with_email and existing_user_with_email[0].User.id != self.user_id:
            # User is permitted to update their email to its current value.
            raise falcon.HTTPConflict(code="DUPLICATE_EMAIL", title="This email is already in use for this channel")

    def send_for_deletion(self) -> None:
        """
        Sends message to hermes via rabbitMQ to request soft-deletion of the user, and onward cleanup of associated PLL
        links, loyalty cards, payment cards etc.
        """
        user_data = {
            "user_id": self.user_id,
            "channel": self.channel_id,
        }

        send_message_to_hermes("delete_user", user_data)
