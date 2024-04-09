import typing

import falcon

from angelia.handlers.loyalty_card import LoyaltyCardHandler
from angelia.hermes.models import Channel, Scheme, SchemeCredentialQuestion, ThirdPartyConsentLink, User
from angelia.lib.loyalty_card import LoyaltyCardStatus
from tests.factories import LoyaltyCardFactory, LoyaltyCardUserAssociationFactory
from tests.helpers.authenticated_request import get_authenticated_request

if typing.TYPE_CHECKING:
    from sqlalchemy.orm import Session


def test_on_get_loyalty_card_balance_happy_path(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User, list[ThirdPartyConsentLink]],
    ],
) -> None:
    """Tests happy path for get loyalty card balance"""
    balance = {
        "value": 3,
        "prefix": "",
        "suffix": "stamps",
        "currency": "stamps",
        "updated_at": 1637323977,
        "description": "",
        "reward_tier": 0,
    }
    expected_balance = {
        "updated_at": 1637323977,
        "current_display_value": "3 stamps",
        "loyalty_currency_name": "stamps",
        "prefix": None,
        "suffix": "stamps",
        "current_value": "3",
        "target_value": None,
    }
    answer_fields = {
        "register_ghost_card_fields": {
            "credentials": [
                {"credential_slug": "postcode", "value": "007"},
            ],
            "consents": [
                {"consent_slug": "Consent_1", "value": "consent_value"},
            ],
        },
    }
    loyalty_card_handler, loyalty_plan, _, _, user, _ = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, consents=True
    )
    db_session.flush()

    loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525", balances=balance)
    db_session.flush()

    user_id, loyalty_card_id = user.id, loyalty_card.id

    user_asc = LoyaltyCardUserAssociationFactory(
        scheme_account_id=loyalty_card_id,
        user_id=user_id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )

    db_session.commit()

    loyalty_card_handler.link_to_user = user_asc
    loyalty_card_handler.card_id = loyalty_card.id
    channel = "com.test.channel"

    resp = get_authenticated_request(
        path=f"/v2/loyalty_cards/{loyalty_card_id}/balance", method="GET", user_id=user_id, channel=channel
    )

    assert resp.status == falcon.HTTP_200
    assert resp.json == {"balance": expected_balance}


def test_on_get_loyalty_card_balance_404() -> None:
    """Tests get loyalty card balance where no loyalty card was found"""

    resp = get_authenticated_request(path="/v2/loyalty_cards/89/balance", method="GET")

    assert resp.status == falcon.HTTP_404
    assert resp.json == {"error_message": "Could not find this account or card", "error_slug": "RESOURCE_NOT_FOUND"}
