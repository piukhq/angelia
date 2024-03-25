from typing import TYPE_CHECKING, Any

import falcon

from angelia.api.auth import (
    TokenType,
    WalletClientToken,
    get_authenticated_channel,
    get_authenticated_external_channel,
    get_authenticated_external_user,
    get_authenticated_user,
    trusted_channel_only,
)
from angelia.api.helpers.vault import get_current_token_secret
from angelia.api.metrics import Metric
from angelia.api.serializers import (
    WalletCreateTrustedSerializer,
    WalletLoyaltyCardBalanceSerializer,
    WalletLoyaltyCardsChannelLinksSerializer,
    WalletLoyaltyCardSerializer,
    WalletLoyaltyCardTransactionsSerializer,
    WalletLoyaltyCardVoucherSerializer,
    WalletOverViewSerializer,
    WalletSerializer,
)
from angelia.api.validators import create_trusted_schema, empty_schema, validate
from angelia.encryption import decrypt_payload
from angelia.handlers.loyalty_card import TRUSTED_ADD, LoyaltyCardHandler
from angelia.handlers.payment_account import PaymentAccountHandler
from angelia.handlers.token import TokenGen
from angelia.handlers.wallet import WalletHandler
from angelia.messaging.sender import send_message_to_hermes
from angelia.report import ctx, log_request_data
from angelia.resources.base_resource import Base

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

    @trusted_channel_only()
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


class WalletRetailer(Base):
    auth_class = WalletClientToken
    hermes_messages: list[dict]

    def combine_and_send_messages_to_hermes(self) -> None:
        combined_dict = {}
        for message in self.hermes_messages:
            for key, value in message.items():
                if isinstance(value, dict):
                    combined_dict.update(value)
                else:
                    combined_dict[key] = value
        send_message_to_hermes("create_trusted", combined_dict)

    def get_token_loyalty_and_payment_card_handlers(
        self, req: falcon.Request, journey: str
    ) -> tuple[TokenGen, LoyaltyCardHandler, PaymentAccountHandler]:
        self.hermes_messages = []
        channel = get_authenticated_external_channel(req)
        external_user_id = get_authenticated_external_user(req)
        kid, secret = get_current_token_secret()
        token_handler = TokenGen(
            db_session=self.session,
            external_user_id=external_user_id,
            channel_id=channel,
            access_kid=kid,
            access_secret_key=secret,
            commit=False,
            send_to_hermes=False,
            hermes_messages=self.hermes_messages,
            **req.context.validated_media["token"],
        )
        token_handler.process_token(req)
        if not token_handler.user_id:
            raise ValueError("User ID has not been generated")

        req.context.events_context["user_and_channel"] = (token_handler.user_id, channel)
        media = req.context.validated_media.get("loyalty_card", {})
        loyalty_card_handler = LoyaltyCardHandler(
            db_session=self.session,
            user_id=token_handler.user_id,
            channel_id=channel,
            journey=journey,
            loyalty_plan_id=media.get("loyalty_plan_id", None),
            all_answer_fields=media.get("account", {}),
            commit=False,
            send_to_hermes=False,
            hermes_messages=self.hermes_messages,
        )
        payment_card_handler = PaymentAccountHandler(
            db_session=self.session,
            user_id=token_handler.user_id,
            channel_id=channel,
            commit=False,
            send_to_hermes=False,
            hermes_messages=self.hermes_messages,
            **req.context.validated_media["payment_card"],
        )
        return token_handler, loyalty_card_handler, payment_card_handler

    @decrypt_payload
    @log_request_data
    @trusted_channel_only(token_type=TokenType.LOGIN_TOKEN)
    @validate(req_schema=create_trusted_schema, resp_schema=WalletCreateTrustedSerializer)
    def on_post_create_trusted(self, req: falcon.Request, resp: falcon.Response, *args: Any) -> None:  # noqa: ARG002
        lc_created = False
        pc_created = False
        token_handler, lc_handler, pa_handler = self.get_token_loyalty_and_payment_card_handlers(req, TRUSTED_ADD)

        # Token
        access_token = token_handler.create_access_token()
        refresh_token = token_handler.create_refresh_token()
        token_handler.refresh_balances()

        # Trusted add
        req.context.events_context["handler"] = lc_handler
        lc_created = lc_handler.handle_trusted_add_card()
        # Add payment card
        payment_card_resp_data, pc_created = pa_handler.add_card()
        resp.media = {
            "token": {
                "access_token": access_token,
                "token_type": "bearer",
                "expires_in": token_handler.access_life_time,
                "refresh_token": refresh_token,
                "scope": ["user"],
            },
            "loyalty_card": {"id": lc_handler.card_id},
            "payment_card": payment_card_resp_data,
        }
        already_existing_records = (not created for created in (token_handler.new_user_created, lc_created, pc_created))
        if all(already_existing_records):
            resp.status = falcon.HTTP_200
        # Lightweight ubiquity check
        elif pa_handler.has_ubiquity_collisions(lc_handler.loyalty_plan_id):
            raise falcon.HTTPConflict(
                code="CONFLICT",
                title="You may encounter this conflict when a provided payment card is already linked "
                "to a different loyalty account. The new wallet will not be created.",
            )
        elif not token_handler.new_user_created:
            raise falcon.HTTPConflict(code="USER_EXISTS", title="User already exists.")
        else:
            resp.status = falcon.HTTP_201
            self.session.commit()
            self.combine_and_send_messages_to_hermes()
        metric = Metric(request=req, status=resp.status)
        metric.route_metric()
