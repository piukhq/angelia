import falcon
from sqlalchemy import select

from app.api.auth import get_authenticated_user, get_authenticated_channel
from app.hermes.models import SchemeAccount, SchemeAccountUserAssociation
from app.api.serializers import WalletSerializer
from app.handlers.wallet import WalletHandler
from app.api.validators import empty_schema, validate
from .base_resource import Base


class Wallet(Base):

    @validate(req_schema=empty_schema, resp_schema=WalletSerializer)
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        handler = WalletHandler(
            user_id=get_authenticated_user(req),
            channel_id=get_authenticated_channel(req)
        )
        data = handler.wallet_data()




        """"

        statement = (
            select(SchemeAccountUserAssociation, SchemeAccount)
            .filter_by(user_id=user_id)
            .join(SchemeAccount)
            .filter_by(is_deleted=False)
        )
        results = self.session.execute(statement).all()
        loyalty_cards = []
        adds = []

        for (assoc, scheme_account) in results:
            balances = []
            if scheme_account.balances:
                values = scheme_account.balances
                # todo database fields do not match the api2.0 example
                balance = {
                    "value": values.get("value"),
                    "currency": "GBP",
                    "prefix": "£",
                    "updated_at": values.get("updated_at"),
                }
                balances.append(balance)

            card = {
                "id": scheme_account.id,
                "plan_id": scheme_account.scheme_id,
                "status": scheme_account.status,
                "deleted": scheme_account.is_deleted,
                "balances": balances,
            }
            loyalty_cards.append(card)

        joins = [
            {"id": 51, "plan_id": 21, "status": "pending"},
            {
                "id": 89,
                "plan_id": 43,
                "status": "failed",
                "errors": [
                    {
                        "error_code": "X202",
                        "error_message": "An account with those details already exists",
                    }
                ],
            },
        ]

        # adds_example = [
        #     {
        #         "id": 12,
        #         "plan_id": 24,
        #         "status": "failed",
        #         "errors": [
        #             {
        #                 "error_code": "X105",
        #                 "error_message": "Card is not registered"
        #             }
        #         ],
        #         "capabilities": [
        #             "register"
        #         ]
        #     }
        # ]

        # loyalty_cards_example = [
        #     {
        #         "id": 81,
        #         "loyalty_plan": 201,
        #         "authorisation": {
        #             "id": 55,
        #             "plan_id": 26,
        #             "status": "complete"
        #         },
        #         "balances": [
        #             {
        #                 "value": 100,
        #                 "currency": "GBP",
        #                 "prefix": "£",
        #                 "updated_at": 1515697663
        #             }
        #         ],
        #         "card": {
        #             "barcode": 633174911234568000,
        #             "barcode_type": 0,
        #             "loyalty_id": 633174911234568000,
        #             "colour": "#FFFFFF"
        #         }
        #     },
        #     {
        #         "id": 85,
        #         "loyalty_plan": 222,
        #         "authorisation": {
        #             "id": 55,
        #             "plan_id": 26,
        #             "status": "failed",
        #             "errors": [
        #                 {
        #                     "error_code": "X303",
        #                     "error_message": "Authorisation data rejected by merchant"
        #                 }
        #             ],
        #             "date_status": 1517549941
        #         },
        #         "capabilities": [
        #             "authorise"
        #         ]
        #     },
        #     {
        #         "id": 97,
        #         "loyalty_plan": 766,
        #         "join": {
        #             "id": 44,
        #             "status": "complete",
        #             "date_status": 1517549941
        #         },
        #         "capabilities": [
        #             "authorise"
        #         ]
        #     }
        # ]

        payment_card_accounts = [
            {
                "id": 432,
                "status": "authorised",
                "month": 12,
                "year": 24,
                "name_on_card": "Jeff Jeffries",
                "consents": [{"type": 0, "timestamp": 1517549941}],
            }
        ]

        pll_links = [
            {
                "payment_account": {
                    "payment_account_id": 555,
                    "payment_scheme": "VISA",
                },
                "loyalty_card": {"loyalty_card_id": 543, "loyalty_scheme": "iceland"},
                "status": "active",
                "id": 68686,
            }
        ]

        reply = [
            {"joins": joins},
            {"adds": adds},
            {"loyalty_cards": loyalty_cards},
            {"payment_accounts": payment_card_accounts},
            {"pll_links": pll_links},
        ]

        resp.media = reply
        """
