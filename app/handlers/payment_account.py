from dataclasses import dataclass
from datetime import datetime
from functools import cached_property

from shared_config_storage.ubiquity.bin_lookup import bin_to_provider

from app.handlers.base import BaseHandler
from app.hermes.models import PaymentAccount, PaymentAccountUserAssociation, PaymentCard, User
from app.lib.payment_card import PaymentAccountStatus
from app.report import api_logger


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
    provider: str = ""
    type: str = ""
    country: str = ""
    currency_code: str = ""

    @cached_property
    def payment_card(self):
        slug = bin_to_provider(str(self.first_six_digits))
        return self.db_session.query(PaymentCard).filter(PaymentCard.slug == slug).first()

    def fields_match_existing(self, existing_account: PaymentAccount):
        return (
            int(self.expiry_month) == existing_account.expiry_month
            and int(self.expiry_year) == existing_account.expiry_year
            and self.name_on_card == existing_account.name_on_card
            and self.card_nickname == existing_account.card_nickname
        )

    @staticmethod
    def to_dict(payment_account: PaymentAccount):
        return {
            "expiry_month": payment_account.expiry_month,
            "expiry_year": payment_account.expiry_year,
            "name_on_card": payment_account.name_on_card,
            "card_nickname": payment_account.card_nickname,
            "issuer": payment_account.issuer_name,
            "id": payment_account.id,
            "status": PaymentAccountStatus.to_str(payment_account.status),
        }

    def get_create_data(self):
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

    def link(self, payment_account, linked_users):
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

        self.db_session.commit()

        return payment_account

    def create(self):
        """
        Create a new payment account from the details provided when instantiating the PaymentAccountHandler
        """
        api_logger.debug("Creating new Payment account")

        account_data = self.get_create_data()
        new_payment_account = PaymentAccount(**account_data)

        self.db_session.add(new_payment_account)
        # Allows retrieving the id before committing so it can be committed at the same time
        # as the link to the user
        self.db_session.flush()

        # Create response data from PaymentAccount instance here since creating after the
        # session.commit() will cause a select query to be executed.
        resp_data = self.to_dict(new_payment_account)

        statement_link_existing_to_user = PaymentAccountUserAssociation(
            payment_card_account_id=new_payment_account.id, user_id=self.user_id
        )

        self.db_session.add(statement_link_existing_to_user)
        self.db_session.commit()

        return new_payment_account, resp_data

    def add_card(self) -> tuple[dict, bool]:
        api_logger.info("Adding Payment Account")
        created = False

        accounts = (
            self.db_session.query(PaymentAccount, User)
            .select_from(PaymentAccount)
            .join(PaymentAccountUserAssociation)
            .join(User)
            .filter(
                PaymentAccount.fingerprint == self.fingerprint,
                PaymentAccount.is_deleted.is_(False),
            )
            .all()
        )

        # Creating a set will eliminate duplicate records returned due to multiple users being linked
        # to the same PaymentAccount
        payment_accounts = {account[0] for account in accounts}
        linked_users = list({account[1] for account in accounts})

        existing_account_count = len(payment_accounts)
        if existing_account_count < 1:
            payment_account, resp_data = self.create()
            created = True

        elif existing_account_count == 1:
            payment_account = payment_accounts.pop()
            payment_account = self.link(payment_account, linked_users)
            resp_data = self.to_dict(payment_account)

        else:
            api_logger.error(
                f"Multiple Payment Accounts with the same fingerprint - fingerprint: {self.fingerprint} - "
                "Continuing processing using newest account"
            )
            payment_account = sorted(payment_accounts, key=lambda x: x.id)[0]
            payment_account = self.link(payment_account, linked_users)
            resp_data = self.to_dict(payment_account)

        return resp_data, created
