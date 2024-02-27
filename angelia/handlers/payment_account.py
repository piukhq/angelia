import dataclasses
import typing
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from functools import cached_property

import falcon
from shared_config_storage.ubiquity.bin_lookup import bin_to_provider
from sqlalchemy import func, select
from sqlalchemy.engine import Row

from angelia.api.exceptions import ResourceNotFoundError
from angelia.handlers.base import BaseHandler
from angelia.hermes.models import (
    PaymentAccount,
    PaymentAccountUserAssociation,
    PaymentCard,
    PaymentSchemeAccountAssociation,
    SchemeAccount,
    User,
)
from angelia.lib.payment_card import PaymentAccountStatus
from angelia.messaging.sender import send_message_to_hermes
from angelia.report import api_logger

if typing.TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass
class PaymentAccountHandler(BaseHandler):
    expiry_month: str
    expiry_year: str
    token: str
    last_four_digits: str
    first_six_digits: str
    fingerprint: str
    name_on_card: str = ""
    card_nickname: str = ""
    issuer: str = ""
    type: str = ""
    country: str = ""
    currency_code: str = ""
    commit: bool = True
    send_to_hermes: bool = True
    hermes_messages: list[dict] = dataclasses.field(default_factory=list)

    @cached_property
    def payment_card(self) -> PaymentCard:
        slug = bin_to_provider(str(self.first_six_digits))
        return self.db_session.query(PaymentCard).filter(PaymentCard.slug == slug).first()

    @staticmethod
    def _process_existing_accounts(accounts: list[Row[PaymentAccount, User]]) -> tuple[list, list]:
        # Creating a set will eliminate duplicate records returned due to multiple users being linked
        # to the same PaymentAccount
        payment_accounts = {account[0] for account in accounts}
        sorted_payment_accounts = sorted(payment_accounts, key=lambda x: x.id, reverse=True)

        active_accounts = []
        deleted_accounts = []
        for account in sorted_payment_accounts:
            active_accounts.append(account) if not account.is_deleted else deleted_accounts.append(account)

        return active_accounts, deleted_accounts

    @staticmethod
    def _map_pcard_ids_to_users(accounts: list[Row[PaymentAccount, User]]) -> dict[int, set[User]]:
        payment_account_ids_to_users = {}
        for account in accounts:
            payment_acc, user = account
            if payment_acc.id not in payment_account_ids_to_users:
                payment_account_ids_to_users[payment_acc.id] = {user} if user else set()
            elif user:
                payment_account_ids_to_users[payment_acc.id].add(user)

        return payment_account_ids_to_users

    def _supersede_old_account(self, old_accounts: list[PaymentAccount]) -> tuple[PaymentAccount, dict]:
        # Get the latest account from old accounts. This should already be ordered by created date.
        old_account = old_accounts[0]

        account_data = self.get_create_data()
        account_data["token"] = old_account.token
        account_data["psp_token"] = old_account.psp_token

        new_payment_account = PaymentAccount(**account_data)

        new_payment_account, resp_data = self.create(new_payment_account)

        api_logger.debug(
            f"Previously deleted Payment Account (id={old_account.id}) has been superseded by a new account "
            f"(id={new_payment_account.id})"
        )

        return new_payment_account, resp_data

    def fields_match_existing(self, existing_account: PaymentAccount) -> bool:
        return (
            int(self.expiry_month) == existing_account.expiry_month
            and int(self.expiry_year) == existing_account.expiry_year
            and self.name_on_card == existing_account.name_on_card
            and self.card_nickname == existing_account.card_nickname
        )

    @staticmethod
    def to_dict(payment_account: PaymentAccount) -> dict:
        return {"id": payment_account.id}

    def get_create_data(self) -> dict:
        return {
            "name_on_card": self.name_on_card,
            "card_nickname": self.card_nickname,
            "expiry_month": self.expiry_month,
            "expiry_year": self.expiry_year,
            "status": 0,
            "order": 0,
            "created": datetime.now(),
            "updated": datetime.now(),
            "issuer_name": self.issuer,
            "issuer_id": None,
            "payment_card_id": self.payment_card.id,
            "token": self.token,
            "country": self.country or "UK",
            "currency_code": self.currency_code,
            "pan_end": self.last_four_digits,
            "pan_start": self.first_six_digits,
            "is_deleted": False,
            "fingerprint": self.fingerprint,
            "psp_token": self.token,
            "consents": [],
            "formatted_images": {},
            "pll_links": [],
            "agent_data": {},
        }

    def link(self, payment_account: PaymentAccount, linked_users: Iterable) -> PaymentAccount:
        """
        Link user to payment account if not already linked.
        Checks are performed to verify that the given data matches the existing account, updating them if they don't.
        """
        linked_user_ids = [user.id for user in linked_users]

        if self.user_id not in linked_user_ids:
            api_logger.debug(f"Linking user {self.user_id} to existing Payment Account {payment_account.id}")
            payment_account_user_association = PaymentAccountUserAssociation(
                payment_card_account_id=payment_account.id, user_id=self.user_id
            )
            self.db_session.add(payment_account_user_association)
        else:
            api_logger.debug(f"User {self.user_id} already linked to Payment Account {payment_account.id}")

        if not self.fields_match_existing(payment_account):
            api_logger.info(f"Updating existing Payment Account {payment_account.id} details")

            payment_account.expiry_month = self.expiry_month
            payment_account.expiry_year = self.expiry_year
            payment_account.name_on_card = self.name_on_card
            payment_account.card_nickname = self.card_nickname

        self.db_session.commit() if self.commit else self.db_session.flush()

        return payment_account

    def create(self, new_payment_account: PaymentAccount | None = None) -> tuple[PaymentAccount, dict]:
        """
        Create a new payment account from the details provided when instantiating the PaymentAccountHandler
        or from providing a new PaymentAccount instance.
        """
        api_logger.debug("Creating new Payment account")

        if not new_payment_account:
            account_data = self.get_create_data()
            new_payment_account = PaymentAccount(**account_data)

        self.db_session.add(new_payment_account)
        # Allows retrieving the id before committing so it can be committed at the same time
        # as the link to the user
        self.db_session.flush()

        # Create response data from PaymentAccount instance here since creating after the
        # session.commit() will cause a select query to be executed. This does mean, however, that
        # expiry_month and expiry_year are not converted to integers from string in resp_data but this
        # should be handled by the response serializer
        resp_data = self.to_dict(new_payment_account)

        statement_link_existing_to_user = PaymentAccountUserAssociation(
            payment_card_account_id=new_payment_account.id, user_id=self.user_id
        )

        self.db_session.add(statement_link_existing_to_user)
        self.db_session.commit() if self.commit else self.db_session.flush()

        return new_payment_account, resp_data

    def add_card(self) -> tuple[dict, bool]:
        api_logger.info("Adding Payment Account")
        created = False
        auto_link = True
        # Flag to identify if a previously deleted account is being superseded by a new account
        # This is required to copy previous tokens over for MC
        supersede = False

        # Outer join so that a payment account record will be returned even if there are no users linked
        # to an account
        query = (
            select(PaymentAccount, User)
            .select_from(PaymentAccount)
            .outerjoin(PaymentAccountUserAssociation)
            .outerjoin(User)
            .where(
                PaymentAccount.fingerprint == self.fingerprint,
            )
        )

        accounts = self.db_session.execute(query).all()
        active_accounts, deleted_accounts = self._process_existing_accounts(accounts)
        payment_account_ids_to_users = self._map_pcard_ids_to_users(accounts)

        existing_account_count = len(active_accounts)

        if existing_account_count < 1:
            # If the card was previously added and deleted then we reuse the previous tokens.
            if deleted_accounts:
                supersede = True
                payment_account, resp_data = self._supersede_old_account(deleted_accounts)
            else:
                payment_account, resp_data = self.create()

            created = True

        elif existing_account_count == 1:
            payment_account = active_accounts.pop()
            payment_account = self.link(payment_account, payment_account_ids_to_users[payment_account.id])
            resp_data = self.to_dict(payment_account)

        else:
            api_logger.error(
                f"Multiple Payment Accounts with the same fingerprint - fingerprint: {self.fingerprint} - "
                "Continuing processing using newest account"
            )
            payment_account = sorted(active_accounts, key=lambda x: x.id, reverse=True)[0]
            payment_account = self.link(payment_account, payment_account_ids_to_users[payment_account.id])
            resp_data = self.to_dict(payment_account)

        message_data = {
            "channel_slug": self.channel_id,
            "user_id": self.user_id,
            "payment_account_id": payment_account.id,
            "auto_link": auto_link,
            "created": created,
            "supersede": supersede,
        }
        if self.send_to_hermes:
            send_message_to_hermes("post_payment_account", message_data)
        else:
            self.hermes_messages.append({"post_payment_account": message_data})

        return resp_data, created

    @staticmethod
    def delete_card(db_session: "Session", channel_id: str, user_id: int, payment_account_id: int) -> None:
        query = select(PaymentAccountUserAssociation).where(
            PaymentAccountUserAssociation.payment_card_account_id == payment_account_id,
            PaymentAccountUserAssociation.user_id == user_id,
        )

        accounts = db_session.execute(query).all()
        no_of_accounts = len(accounts)

        if no_of_accounts < 1:
            raise ResourceNotFoundError

        elif no_of_accounts > 1:
            api_logger.error(
                "Multiple PaymentAccountUserAssociation objects were found for "
                f"user_id {user_id} and pca_id {payment_account_id} whilst handling"
                "pca delete request.",
            )
            raise falcon.HTTPInternalServerError

        else:
            message_data = {
                "channel_slug": channel_id,
                "user_id": user_id,
                "payment_account_id": payment_account_id,
            }

            send_message_to_hermes("delete_payment_account", message_data)

    def has_ubiquity_collisions(self, loyalty_plan_id: int) -> bool:
        return (
            self.db_session.scalar(
                select(func.count(PaymentSchemeAccountAssociation.id))
                .join(
                    PaymentAccount,
                    PaymentSchemeAccountAssociation.payment_card_account_id == PaymentAccount.id,
                )
                .join(
                    SchemeAccount,
                    PaymentSchemeAccountAssociation.scheme_account_id == SchemeAccount.id,
                )
                .where(
                    PaymentAccount.is_deleted.is_(False),
                    PaymentAccount.fingerprint == self.fingerprint,
                    SchemeAccount.scheme_id == loyalty_plan_id,
                )
            )
            > 0
        )


@dataclass
class PaymentAccountUpdateHandler(BaseHandler):
    """Handles PaymentAccount detail updates"""

    account_id: int

    expiry_month: str = ""
    expiry_year: str = ""
    name_on_card: str = ""
    card_nickname: str = ""
    issuer: str = ""

    @staticmethod
    def to_dict(payment_account: PaymentAccount) -> dict:
        return {
            "expiry_month": payment_account.expiry_month,
            "expiry_year": payment_account.expiry_year,
            "name_on_card": payment_account.name_on_card,
            "card_nickname": payment_account.card_nickname,
            "issuer": payment_account.issuer_name,
            "id": payment_account.id,
            "status": PaymentAccountStatus.to_str(payment_account.status),
        }

    def _update_card_details(
        self, existing_account: PaymentAccount, update_fields: list[str]
    ) -> tuple[PaymentAccount, list]:
        # mapping required for fields where the payload does not match the db level field name or type
        field_name_map = {"issuer": "issuer_name"}

        field_type_map = {
            "expiry_month": int,
            "expiry_year": int,
        }

        def is_match(update_field: str, existing_acc: PaymentAccount) -> bool:
            conv = field_type_map.get(update_field)
            update_val = conv(getattr(self, field)) if conv else getattr(self, field)
            return update_val == getattr(existing_acc, field_name_map.get(field, field))

        fields_updated = []
        for field in update_fields:
            matched_value = is_match(field, existing_account)
            if not matched_value:
                db_field_name = field_name_map.get(field, field)
                setattr(existing_account, db_field_name, getattr(self, field))
                fields_updated.append(db_field_name)

        if fields_updated:
            self.db_session.commit()

        return existing_account, fields_updated

    def update_card(self, update_fields: list[str]) -> dict:
        api_logger.info("Updating Payment Account")

        query = (
            select(PaymentAccount)
            .join(PaymentAccountUserAssociation)
            .where(
                PaymentAccountUserAssociation.payment_card_account_id == self.account_id,
                PaymentAccountUserAssociation.user_id == self.user_id,
            )
        )

        accounts = self.db_session.execute(query).all()
        no_of_accounts = len(accounts)

        if no_of_accounts < 1:
            raise ResourceNotFoundError

        # Realistically this will never happen due to the db level unique constraint. Could possibly be removed.
        elif no_of_accounts > 1:
            api_logger.error(
                "Multiple PaymentAccountUserAssociation objects were found for "
                f"user_id {self.user_id} and pca_id {self.account_id} whilst handling"
                "pca update request.",
            )
            raise falcon.HTTPInternalServerError

        payment_account, fields_updated = self._update_card_details(accounts.pop()[0], update_fields)
        api_logger.debug(f"Updated the following fields for PaymentAccount (id={self.account_id}) - {fields_updated}")

        return self.to_dict(payment_account)
