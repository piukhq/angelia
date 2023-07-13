import base64
import hashlib
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from time import time
from uuid import uuid4

import arrow
import jwt
from sqlalchemy import func
from sqlalchemy.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.future import select
from sqlalchemy.orm import contains_eager

from app.api.exceptions import (
    AuthenticationFailed,
    MagicLinkExpiredTokenError,
    MagicLinkValidationError,
    ValidationError,
)
from app.api.helpers.vault import get_channel_jwt_secret
from app.handlers.base import BaseTokenHandler
from app.hermes.models import (
    Channel,
    ClientApplication,
    Scheme,
    SchemeAccount,
    SchemeAccountCredentialAnswer,
    SchemeAccountUserAssociation,
    SchemeChannelAssociation,
    SchemeCredentialQuestion,
    User,
)
from app.lib.credentials import EMAIL
from app.lib.loyalty_card import LoyaltyCardStatus
from app.messaging.sender import send_message_to_hermes
from app.report import api_logger
from settings import redis


@dataclass
class MagicLinkData:
    bundle_id: str
    slug: str
    external_name: str
    email: str
    email_from: str
    subject: str
    template: str
    url: str
    token: str
    locale: str


@dataclass
class MagicLinkHandler(BaseTokenHandler):
    @staticmethod
    def _get_jwt_secret(token: str) -> str:
        try:
            bundle_id = jwt.decode(
                token,
                options={"verify_signature": False},
                algorithms=["HS512", "HS256"],
            )["bundle_id"]

            jwt_secret = get_channel_jwt_secret(bundle_id)
        except (KeyError, jwt.DecodeError, AuthenticationFailed):
            api_logger.debug("failed to extract bundle_id from magic link temporary token.")
            raise MagicLinkValidationError from None

        return jwt_secret

    def _validate_token(self, token: str | None) -> tuple[str, str, str, int]:
        """
        :param token: magic link temporary token
        :return: email, bundle_id, md5 token hash, remaining token validity time in seconds
        """

        if not token:
            api_logger.debug("failed to provide a magic link temporary token.")
            raise MagicLinkValidationError

        token_secret = self._get_jwt_secret(token)

        token_hash = hashlib.md5(token.encode()).hexdigest()
        if redis.get(f"ml:{token_hash}"):
            api_logger.debug("magic link temporary token has already been used.")
            raise MagicLinkExpiredTokenError

        error_message: str | None = None
        try:
            token_data = jwt.decode(token, token_secret, algorithms=["HS512", "HS256"])
            email = token_data["email"]
            bundle_id = token_data["bundle_id"]
            exp = int(token_data["exp"])

        except jwt.ExpiredSignatureError:
            error_message = "magic link temporary token has expired."

        except (KeyError, ValueError):
            error_message = (
                "the provided magic link temporary token was signed correctly "
                "but did not contain the required information."
            )

        except jwt.DecodeError:
            error_message = (
                "the provided magic link temporary token was not signed correctly or was not in a valid format"
            )

        if error_message:
            api_logger.debug(error_message)
            raise MagicLinkValidationError

        return email, bundle_id, token_hash, exp - arrow.utcnow().int_timestamp

    def auto_add_membership_cards_with_email(self, user: User, scheme_slug: str) -> None:
        """
        Auto add loyalty card when user auth with magic link. Checks for schemes that have email as
        an auth field.
        """

        # Make sure scheme account is authorised with the same email in the magic link

        scheme_account_ids = (
            self.db_session.execute(
                select(SchemeAccount.id)
                .select_from(SchemeAccountCredentialAnswer)
                .join(
                    SchemeCredentialQuestion, SchemeCredentialQuestion.id == SchemeAccountCredentialAnswer.question_id
                )
                .join(
                    SchemeAccountUserAssociation,
                    SchemeAccountUserAssociation.id == SchemeAccountCredentialAnswer.scheme_account_entry_id,
                )
                .join(SchemeAccount, SchemeAccount.id == SchemeAccountUserAssociation.scheme_account_id)
                .join(Scheme, Scheme.id == SchemeAccount.scheme_id)
                .where(
                    SchemeCredentialQuestion.type == EMAIL,
                    SchemeCredentialQuestion.auth_field.is_(True),
                    Scheme.slug == scheme_slug,
                    SchemeAccountUserAssociation.link_status == LoyaltyCardStatus.ACTIVE,
                    SchemeAccountCredentialAnswer.answer == user.email,
                )
            )
            .scalars()
            .all()
        )
        entries_to_create = [
            SchemeAccountUserAssociation(
                scheme_account_id=scheme_account_id,
                user_id=user.id,
                link_status=LoyaltyCardStatus.PENDING,
                authorised=False,
            )
            for scheme_account_id in scheme_account_ids
        ]

        if entries_to_create:
            self.db_session.add_all(entries_to_create)
            self.db_session.flush()

    def get_or_create_user(self, tmp_token: str | None) -> dict:
        email, bundle_id, token_hash, valid_for = self._validate_token(tmp_token)

        if not (
            client_id := self.db_session.scalar(
                select(ClientApplication.client_id).join(Channel).where(Channel.bundle_id == bundle_id)
            )
        ):
            api_logger.debug(f"bundle_id: '{bundle_id}' provided in the magic link temporary token is not valid.")
            raise MagicLinkValidationError

        pending_changes = False
        try:
            user = self.db_session.execute(
                select(User).where(func.lower(User.email) == func.lower(email), User.client_id == client_id)
            ).scalar_one()

        except NoResultFound:
            salt = base64.b64encode(os.urandom(16))[:8].decode("utf-8")
            user = User(
                uid=uuid4(),
                client_id=client_id,
                bundle_id=bundle_id,
                email=email,
                external_id="",
                is_active=True,
                is_staff=False,
                is_superuser=False,
                is_tester=False,
                password=f"invalid$1${salt}${base64.b64encode(os.urandom(16)).decode('utf-8')}",
                salt=salt,
                date_joined=datetime.now(tz=UTC),
                last_accessed=datetime.now(tz=UTC).isoformat(),
                delete_token="",
            )

            self.db_session.add(user)
            self.db_session.flush()
            pending_changes = True

            # LOY-1609 - we only want to do this for wasabi for now until later on.
            # Remove this when we want to open this up for all schemes.
            if bundle_id == "com.wasabi.bink.web":
                # Auto add membership cards that has been authorised and using the same email
                # We only want to do this once when the user is created
                self.auto_add_membership_cards_with_email(user, "wasabi-club")

        if not user.magic_link_verified:
            user.magic_link_verified = datetime.now(tz=UTC)
            pending_changes = True

        if pending_changes:
            self.db_session.commit()

        redis.set(f"ml:{token_hash}", "y", valid_for + 1)
        token = user.create_token(self.db_session, bundle_id)
        return {"access_token": token}

    def send_magic_link_email(self, email: str, plan_id: int, locale: str, bundle_id: str) -> dict:
        data = self._validate_email_request_data(email, plan_id, locale, bundle_id)
        send_message_to_hermes("send_magic_link", asdict(data))
        return {}

    def _validate_email_request_data(self, email: str, plan_id: int, locale: str, bundle_id: str) -> MagicLinkData:
        try:
            query = (
                select(SchemeChannelAssociation)
                .join(Channel, SchemeChannelAssociation.bundle_id == Channel.id)
                .join(Scheme, SchemeChannelAssociation.scheme_id == Scheme.id)
                .options(
                    contains_eager(SchemeChannelAssociation.channel),
                    contains_eager(SchemeChannelAssociation.scheme),
                )
                .where(
                    SchemeChannelAssociation.scheme_id == plan_id,
                    Channel.bundle_id == bundle_id,
                    SchemeChannelAssociation.status == 0,
                )
            )
            scheme_channel_association = self.db_session.execute(query).scalar_one()
            channel = scheme_channel_association.channel
            scheme = scheme_channel_association.scheme

            if not channel.magic_link_url:
                raise ValidationError(f"Config: Magic links not permitted for bundle id {bundle_id}")

            if not channel.template:
                raise ValidationError(f"Config: Missing email template for bundle id {bundle_id}")

            lifetime = 60 if not channel.magic_lifetime else int(channel.magic_lifetime)
            jwt_secret = get_channel_jwt_secret(bundle_id)
            now = int(time())
            payload = {"email": email, "bundle_id": bundle_id, "iat": now, "exp": int(now + lifetime * 60)}
            return MagicLinkData(
                bundle_id=bundle_id,
                slug=scheme.slug,
                external_name=channel.external_name or "web",
                email=email,
                email_from=channel.email_from,
                subject=channel.subject,
                template=channel.template,
                url=channel.magic_link_url,
                token=jwt.encode(payload, jwt_secret, algorithm="HS512"),
                locale=locale,
            )
        except NoResultFound:
            raise ValidationError(
                f"Config: {bundle_id} was not found or is not active for loyalty plan {plan_id}"
            ) from None
        except MultipleResultsFound:
            raise ValidationError(
                f"Config: error multiple channel/loyalty_plan associations found for channel_id {bundle_id} / "
                f"loyalty plan {plan_id}"
            ) from None
