from dataclasses import dataclass
from datetime import datetime

import falcon
from sqlalchemy import update, insert
from sqlalchemy.orm import Session

from app.hermes.models import PaymentAccount, User, PaymentAccountUserAssociation
from app.report import api_logger


@dataclass
class BaseHandler:
    db_session: Session
    user_id: int
    channel_id: str


@dataclass
class PaymentAccountHandler(BaseHandler):
    expiry_month: str
    expiry_year: str
    token: str
    last_four_digits: str
    first_six_digits: str
    fingerprint: str
    name_on_card: str = None
    card_nickname: str = None
    issuer: str = None
    provider: str = None
    type: str = None
    country: str = None
    currency_code: str = None

    def fields_match_existing(self, existing_account: PaymentAccount):
        return (
            int(self.expiry_month) == existing_account.expiry_month and
            int(self.expiry_year) == existing_account.expiry_year and
            self.name_on_card == existing_account.name_on_card
            # and self.card_nickname == existing_account.card_nickname
        )

    @staticmethod
    def to_dict(payment_account: PaymentAccount):
        return {
            "expiry_month": str(payment_account.expiry_month),
            "expiry_year": str(payment_account.expiry_year),
            "name_on_card": payment_account.name_on_card,
            # "card_nickname": existing_payment_account.card_nickname,  Todo: Requires migration to add new field
            # Todo: Should be name field of bank Issuer record not the payment card issuer id
            "issuer": payment_account.issuer_id,
            "id": payment_account.id,
            "status": payment_account.status,    # Todo: needs mapping to string value
        }

    def get_create_data(self):
        return {
            "name_on_card": self.name_on_card,
            "expiry_month": self.expiry_month,
            "expiry_year": self.expiry_year,
            "status": 0,
            "order": 0,
            "created": datetime.now(),
            "updated": datetime.now(),
            # Todo: Get issuer based on given data and check if the issuer is allowed for current bundle.
            #  currently defaults to barclays in hermes core
            "issuer_id": 3,
            "payment_card_id": 1,
            "token": self.token,
            "country": self.country or 'UK',
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
        If the user is already linked, checks are performed to verify that the given data matches
        the existing account, updating them if they don't.
        """
        linked_user_ids = [user.id for user in linked_users]
        if self.user_id in linked_user_ids:
            if not self.fields_match_existing(payment_account):
                api_logger.info(f"UPDATING EXISTING ACCOUNT {payment_account.id} DETAILS WITH NEW INFORMATION")

                statement_update_existing_account = update(PaymentAccount) \
                    .where(PaymentAccount.id == payment_account.id) \
                    .values(expiry_month=self.expiry_month,
                            expiry_year=self.expiry_year,
                            name_on_card=self.name_on_card)

                self.db_session.add(statement_update_existing_account)
                self.db_session.commit()
        else:
            api_logger.info("ACCOUNT EXISTS IN ANOTHER WALLET - LINK THIS USER")
            statement_link_existing_to_user = insert(PaymentAccountUserAssociation) \
                .values(payment_card_account_id=payment_account.id,
                        user_id=self.user_id)
            self.db_session.add(statement_link_existing_to_user)
            self.db_session.commit()

        return payment_account

    def create(self):
        """
        Create a new payment account from the details provided when instantiating the PaymentAccountHandler
        """
        api_logger.info("THIS IS A NEW ACCOUNT")

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
            payment_card_account_id=new_payment_account.id,
            user_id=self.user_id
        )

        self.db_session.add(statement_link_existing_to_user)
        self.db_session.commit()

        return new_payment_account, resp_data

    def add_card(self) -> tuple[dict, bool]:
        created = False

        accounts = self.db_session.query(PaymentAccount, User) \
            .select_from(PaymentAccount) \
            .join(PaymentAccountUserAssociation) \
            .join(User) \
            .filter(PaymentAccount.fingerprint == self.fingerprint, PaymentAccount.is_deleted.is_(False)) \
            .all()

        # Creating a set will eliminate duplicate records returned due to multiple users being linked
        # to the same PaymentAccount
        payment_accounts = {account[0] for account in accounts}
        linked_users = list({account[1] for account in accounts})

        existing_account_count = len(payment_accounts)
        if existing_account_count < 1:
            payment_account, resp_data = self.create()
            created = True

        elif existing_account_count == 1:
            payment_account = self.link(payment_accounts.pop(), linked_users)
            resp_data = self.to_dict(payment_account)

        else:
            api_logger.error(
                "Multiple payment accounts with the same fingerprint - "
                f"fingerprint: {self.fingerprint}"
            )
            raise falcon.HTTPInternalServerError

        return resp_data, created
