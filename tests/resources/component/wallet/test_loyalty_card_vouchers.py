import typing

import falcon

from angelia.handlers.loyalty_card import LoyaltyCardHandler
from angelia.hermes.models import Channel, Scheme, SchemeCredentialQuestion, ThirdPartyConsentLink, User
from angelia.lib.loyalty_card import LoyaltyCardStatus
from tests.factories import LoyaltyCardFactory, LoyaltyCardUserAssociationFactory
from tests.helpers.authenticated_request import get_authenticated_request

if typing.TYPE_CHECKING:
    from sqlalchemy.orm import Session


def test_on_get_loyalty_card_vouchers_happy_path(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User, list[ThirdPartyConsentLink]],
    ],
) -> None:
    """Tests happy path for get loyalty card vouchers"""
    vouchers = [
        {
            "burn": {"type": "voucher", "value": None, "prefix": "Free", "suffix": "Meal", "currency": ""},
            "earn": {
                "type": "stamps",
                "value": 3.0,
                "prefix": "",
                "suffix": "stamps",
                "currency": "",
                "target_value": 7.0,
            },
            "state": "inprogress",
            "subtext": "",
            "headline": "Spend \u00a37.00 or more to get a stamp. Collect 7 stamps to get a"
            " Meal Voucher of up to \u00a37 off your next meal.",
            "body_text": "",
            "barcode_type": 0,
            "terms_and_conditions_url": "",
        },
        {
            "burn": {"type": "voucher", "value": None, "prefix": "Free", "suffix": "Meal", "currency": ""},
            "code": "12YC945M",
            "earn": {
                "type": "stamps",
                "value": 7.0,
                "prefix": "",
                "suffix": "stamps",
                "currency": "",
                "target_value": 7.0,
            },
            "state": "cancelled",
            "subtext": "",
            "headline": "",
            "body_text": "",
            "date_issued": 1590066834,
            "expiry_date": 1591747140,
            "barcode_type": 0,
            "terms_and_conditions_url": "",
        },
    ]
    expected_vouchers = {
        "vouchers": [
            {
                "state": "inprogress",
                "earn_type": "stamps",
                "reward_text": "Free Meal",
                "headline": (
                    "Spend £7.00 or more to get a stamp. "
                    "Collect 7 stamps to get a Meal Voucher "
                    "of up to £7 off your next meal."
                ),
                "voucher_code": None,
                "barcode_type": 0,
                "progress_display_text": "3/7 stamps",
                "current_value": "3",
                "target_value": "7",
                "prefix": None,
                "suffix": "stamps",
                "body_text": None,
                "terms_and_conditions": None,
                "issued_date": None,
                "expiry_date": None,
                "redeemed_date": None,
                "conversion_date": None,
            },
            {
                "state": "cancelled",
                "earn_type": "stamps",
                "reward_text": "Free Meal",
                "headline": None,
                "voucher_code": "12YC945M",
                "barcode_type": 0,
                "progress_display_text": "7/7 stamps",
                "current_value": "7",
                "target_value": "7",
                "prefix": None,
                "suffix": "stamps",
                "body_text": None,
                "terms_and_conditions": None,
                "issued_date": "1590066834",
                "expiry_date": "1591747140",
                "redeemed_date": None,
                "conversion_date": None,
            },
        ]
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

    loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525", vouchers=vouchers)
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
        path=f"/v2/loyalty_cards/{loyalty_card_id}/vouchers", method="GET", user_id=user_id, channel=channel
    )

    assert resp.status == falcon.HTTP_200
    assert resp.json == expected_vouchers


def test_on_get_loyalty_card_transactions_404() -> None:
    """Tests get loyalty card vouchers where no loyalty card was found"""

    resp = get_authenticated_request(path="/v2/loyalty_cards/89/vouchers", method="GET")

    assert resp.status == falcon.HTTP_404
    assert resp.json == {"error_message": "Could not find this account or card", "error_slug": "RESOURCE_NOT_FOUND"}
