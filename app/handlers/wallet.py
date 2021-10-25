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
    user_id: int = None
    channel_id: int = None

    def wallet_data(self):
        pass
