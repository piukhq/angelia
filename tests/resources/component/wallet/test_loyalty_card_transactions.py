import typing

import falcon

from angelia.handlers.loyalty_card import LoyaltyCardHandler
from angelia.hermes.models import Channel, Scheme, SchemeCredentialQuestion, ThirdPartyConsentLink, User
from angelia.lib.loyalty_card import LoyaltyCardStatus
from tests.factories import LoyaltyCardFactory, LoyaltyCardUserAssociationFactory
from tests.helpers.authenticated_request import get_authenticated_request

if typing.TYPE_CHECKING:
    from sqlalchemy.orm import Session


def test_on_get_loyalty_card_transactions_happy_path(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User, list[ThirdPartyConsentLink]],
    ],
) -> None:
    """Tests happy path for get loyalty card transactions"""
    transaction = [
        {
            "id": 239604,
            "status": "active",
            "amounts": [{"value": 1, "prefix": "", "suffix": "stamps", "currency": "stamps"}],
            "timestamp": 1591788226,
            "description": "Cambridge Petty Cury \u00a38.08",
        }
    ]
    expected_transaction = [
        {
            "id": "239604",
            "timestamp": 1591788226,
            "description": "Cambridge Petty Cury £8.08",
            "display_value": "1 stamps",
        }
    ]
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

    loyalty_card = LoyaltyCardFactory(
        scheme=loyalty_plan, card_number="9511143200133540455525", transactions=transaction
    )
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
        path=f"/v2/loyalty_cards/{loyalty_card_id}/transactions", method="GET", user_id=user_id, channel=channel
    )

    assert resp.status == falcon.HTTP_200
    assert resp.json == {"transactions": expected_transaction}


def test_on_get_loyalty_card_transactions_404() -> None:
    """Tests get loyalty card transactions where no loyalty card was found"""

    resp = get_authenticated_request(path="/v2/loyalty_cards/89/transactions", method="GET")

    assert resp.status == falcon.HTTP_404
    assert resp.json == {"error_message": "Could not find this account or card", "error_slug": "RESOURCE_NOT_FOUND"}
