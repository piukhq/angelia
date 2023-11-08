from typing import TYPE_CHECKING

import falcon

from app.api.auth import get_authenticated_channel, get_authenticated_user, trusted_channel_only
from app.api.metrics import Metric
from app.api.serializers import (
    WalletLoyaltyCardBalanceSerializer,
    WalletLoyaltyCardsChannelLinksSerializer,
    WalletLoyaltyCardSerializer,
    WalletLoyaltyCardTransactionsSerializer,
    WalletLoyaltyCardVoucherSerializer,
    WalletOverViewSerializer,
    WalletSerializer,
)
from app.api.validators import empty_schema, validate
from app.handlers.wallet import WalletHandler
from app.report import ctx
from app.resources.base_resource import Base

if TYPE_CHECKING:
    from pydantic import BaseModel


def get_voucher_serializers() -> "list[type[BaseModel]]":
    serializers: list[type[BaseModel]] = [
        WalletSerializer,
        WalletLoyaltyCardVoucherSerializer,
        WalletLoyaltyCardSerializer,
    ]

    return serializers


class Wallet(Base):
    def get_wallet_handler(self, req: falcon.Request) -> WalletHandler:
        user_id = ctx.user_id = get_authenticated_user(req)
        channel = get_authenticated_channel(req)
        return WalletHandler(db_session=self.session, user_id=user_id, channel_id=channel)

    @validate(req_schema=empty_schema, resp_schema=get_voucher_serializers()[0])
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        handler = self.get_wallet_handler(req)
        resp.media = handler.get_wallet_response()
        handler.send_to_hermes_view_wallet_event()
        metric = Metric(request=req, status=resp.status)
        metric.route_metric()

    @validate(req_schema=empty_schema, resp_schema=WalletOverViewSerializer)
    def on_get_overview(self, req: falcon.Request, resp: falcon.Response) -> None:
        handler = self.get_wallet_handler(req)
        resp.media = handler.get_overview_wallet_response()
        handler.send_to_hermes_view_wallet_event()
        metric = Metric(request=req, status=resp.status)
        metric.route_metric()

    @trusted_channel_only
    @validate(req_schema=empty_schema, resp_schema=WalletLoyaltyCardsChannelLinksSerializer)
    def on_get_payment_account_channel_links(self, req: falcon.Request, resp: falcon.Response) -> None:
        handler = self.get_wallet_handler(req)
        resp.media = handler.get_payment_account_channel_links()
        metric = Metric(request=req, status=resp.status)
        metric.route_metric()

    @validate(req_schema=empty_schema, resp_schema=WalletLoyaltyCardTransactionsSerializer)
    def on_get_loyalty_card_transactions(
        self, req: falcon.Request, resp: falcon.Response, loyalty_card_id: int
    ) -> None:
        handler = self.get_wallet_handler(req)
        resp.media = handler.get_loyalty_card_transactions_response(loyalty_card_id)

    @validate(req_schema=empty_schema, resp_schema=WalletLoyaltyCardBalanceSerializer)
    def on_get_loyalty_card_balance(self, req: falcon.Request, resp: falcon.Response, loyalty_card_id: int) -> None:
        handler = self.get_wallet_handler(req)
        resp.media = handler.get_loyalty_card_balance_response(loyalty_card_id)

    @validate(req_schema=empty_schema, resp_schema=get_voucher_serializers()[1])
    def on_get_loyalty_card_vouchers(self, req: falcon.Request, resp: falcon.Response, loyalty_card_id: int) -> None:
        handler = self.get_wallet_handler(req)
        resp.media = handler.get_loyalty_card_vouchers_response(loyalty_card_id)

    @validate(req_schema=empty_schema, resp_schema=get_voucher_serializers()[2])
    def on_get_loyalty_card_by_id(self, req: falcon.Request, resp: falcon.Response, loyalty_card_id: int) -> None:
        handler = self.get_wallet_handler(req)
        resp.media = handler.get_loyalty_card_by_id_response(loyalty_card_id)

        metric = Metric(request=req, status=resp.status, resource_id=loyalty_card_id, resource="loyalty_card_id")
        metric.route_metric()
