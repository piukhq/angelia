import typing
from dataclasses import dataclass
from datetime import datetime
from functools import cached_property
from typing import Iterable

import falcon
from shared_config_storage.ubiquity.bin_lookup import bin_to_provider
from sqlalchemy import select

from app.api.exceptions import ResourceNotFoundError
from app.handlers.base import BaseHandler
from app.hermes.models import PaymentAccount, PaymentAccountUserAssociation, PaymentCard, User
from app.lib.payment_card import PaymentAccountStatus
from app.messaging.sender import send_message_to_hermes
from app.report import api_logger


@dataclass
class WalletHandler(BaseHandler):
    joins = []
    loyalty_cards = []
    payment_accounts = []

    def get_response_dict(self) -> dict:
        self._query_db()
        return {"joins": self.joins, "loyalty_cards": self.loyalty_cards, "payment_accounts": self.payment_accounts}

    def _query_db(self):
        query = (
            select(PaymentAccount.id,
                   PaymentAccount.status,
                   PaymentAccount.card_nickname,
                   PaymentAccount.name_on_card,
                   PaymentAccount.expiry_month,
                   PaymentAccount.expiry_year,
                   )
            .join(PaymentAccountUserAssociation).join(User)
            .where(
                User.id == self.user_id,
                PaymentAccount.is_deleted.is_(False),
            )
        )

        accounts = self.db_session.execute(query).all()
        for account in accounts:
            self.payment_accounts.append(dict(account))




