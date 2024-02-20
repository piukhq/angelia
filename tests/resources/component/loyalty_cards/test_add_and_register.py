import typing
from unittest.mock import MagicMock, patch

import falcon
from sqlalchemy import func, select

from angelia.handlers.loyalty_card import ADD_AND_REGISTER, LoyaltyCardHandler
from angelia.hermes.models import (
    Channel,
    Scheme,
    SchemeAccount,
    SchemeAccountUserAssociation,
    SchemeCredentialQuestion,
    ThirdPartyConsentLink,
    User,
)
from angelia.lib.loyalty_card import LoyaltyCardStatus, OriginatingJourney
from tests.factories import (
    LoyaltyCardFactory,
    LoyaltyCardUserAssociationFactory,
    LoyaltyPlanQuestionFactory,
    UserFactory,
)
from tests.helpers.authenticated_request import get_authenticated_request

if typing.TYPE_CHECKING:
    from sqlalchemy.orm import Session


@patch("angelia.handlers.loyalty_card.send_message_to_hermes")
def test_on_post_add_and_register(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    add_register_req_data: dict,
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User, list[ThirdPartyConsentLink]],
    ],
) -> None:
    """Tests that user is successfully linked to a newly created Scheme Account (ADD_AND_REGISTER)"""
    req_data = add_register_req_data.copy()
    answer_fields = req_data["account"]
    loyalty_card_handler, loyalty_plan, questions, channel, user, consents = setup_loyalty_card_handler(
        all_answer_fields=answer_fields,
        consents=True,
        journey=ADD_AND_REGISTER,
    )
    consents_id = consents[0].id

    # adding an optional credential question to check that not providing an answer for it still result in success.
    LoyaltyPlanQuestionFactory(
        type="random",
        label="Random",
        scheme_id=loyalty_plan.id,
        is_optional=True,
        register_field=True,
        enrol_field=True,
    )
    db_session.commit()

    user_id, loyalty_plan_id = (
        user.id,
        loyalty_plan.id,
    )

    req_data["loyalty_plan_id"] = loyalty_plan_id
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_and_register",
        json=req_data,
        method="POST",
        user_id=user_id,
        channel="com.test.channel",
    )
    assert resp.status == falcon.HTTP_202

    cards = (
        db_session.query(SchemeAccount)
        .filter(
            SchemeAccount.scheme_id == loyalty_plan_id,
        )
        .all()
    )
    assert len(cards) == 1
    assert cards[0].originating_journey == OriginatingJourney.REGISTER

    assert cards[0].card_number == req_data["account"]["add_fields"]["credentials"][0]["value"]
    assert (
        db_session.execute(
            select(func.count())
            .select_from(SchemeAccountUserAssociation)
            .where(
                SchemeAccountUserAssociation.scheme_account_id == cards[0].id,
                SchemeAccountUserAssociation.user_id == user_id,
            )
        ).scalar()
        == 1
    )
    mock_send_message_to_hermes.assert_called_once_with(
        "loyalty_card_add_and_register",
        {
            "loyalty_plan_id": loyalty_plan_id,
            "loyalty_card_id": cards[0].id,
            "entry_id": cards[0].scheme_account_user_associations[0].id,
            "user_id": user_id,
            "channel_slug": "com.test.channel",
            "journey": "ADD_AND_REGISTER",
            "auto_link": True,
            "add_fields": [
                {
                    "credential_slug": "card_number",
                    "value": req_data["account"]["add_fields"]["credentials"][0]["value"],
                }
            ],
            "register_fields": [
                {
                    "credential_slug": "postcode",
                    "value": req_data["account"]["register_ghost_card_fields"]["credentials"][0]["value"],
                }
            ],
            "consents": [
                {
                    "id": consents_id,
                    "value": req_data["account"]["register_ghost_card_fields"]["consents"][0]["value"],
                }
            ],
        },
    )


@patch("angelia.handlers.loyalty_card.send_message_to_hermes")
def test_on_post_add_and_register_card_existing_registration_in_other_wallet(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    add_register_req_data: dict,
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User, list[ThirdPartyConsentLink]],
    ],
) -> None:
    """
    Tests that user is successfully linked to existing loyalty card when there is an existing LoyaltyCard in another
    wallet (ADD_AND_REGISTER)
    """
    req_data = add_register_req_data.copy()
    answer_fields = req_data["account"]
    loyalty_card_handler, loyalty_plan, questions, channel, user, consents = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, consents=True, journey=ADD_AND_REGISTER
    )

    new_loyalty_card = LoyaltyCardFactory(
        scheme=loyalty_plan, card_number=req_data["account"]["add_fields"]["credentials"][0]["value"]
    )

    other_user = UserFactory(client=channel.client_application)

    db_session.flush()

    LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=other_user.id,
        link_status=LoyaltyCardStatus.REGISTRATION_ASYNC_IN_PROGRESS,
    )

    db_session.commit()

    user_id, loyalty_plan_id = (
        user.id,
        loyalty_plan.id,
    )

    req_data["loyalty_plan_id"] = loyalty_plan_id
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_and_register",
        json=req_data,
        method="POST",
        user_id=user_id,
        channel="com.test.channel",
    )
    assert resp.status == falcon.HTTP_202

    assert (
        len(
            db_session.query(SchemeAccount)
            .filter(
                SchemeAccount.scheme_id == loyalty_plan_id,
            )
            .all()
        )
        == 1
    )
    mock_send_message_to_hermes.assert_called()


@patch("angelia.handlers.loyalty_card.send_message_to_hermes")
def test_on_post_add_and_register_card_already_added_and_not_active(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    add_register_req_data: dict,
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User, list[ThirdPartyConsentLink]],
    ],
) -> None:
    """
    Tests that when a card is already added, an error is raised.
    """
    req_data = add_register_req_data.copy()
    answer_fields = req_data["account"]
    loyalty_card_handler, loyalty_plan, questions, channel, user, consents = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, consents=True, journey=ADD_AND_REGISTER
    )

    new_loyalty_card = LoyaltyCardFactory(
        scheme=loyalty_plan, card_number=req_data["account"]["add_fields"]["credentials"][0]["value"]
    )

    db_session.flush()

    LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.PENDING,
    )
    db_session.commit()

    user_id, loyalty_plan_id = (
        user.id,
        loyalty_plan.id,
    )

    req_data["loyalty_plan_id"] = loyalty_plan_id
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_and_register",
        json=req_data,
        method="POST",
        user_id=user_id,
        channel="com.test.channel",
    )
    assert resp.status == falcon.HTTP_409
    assert resp.json == {
        "error_message": "Card already added. Use PUT /loyalty_cards/{loyalty_card_id}/register to register this card.",
        "error_slug": "ALREADY_ADDED",
    }

    mock_send_message_to_hermes.assert_not_called()


@patch("angelia.handlers.loyalty_card.send_message_to_hermes")
def test_on_post_add_and_register_card_already_registered(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    add_register_req_data: dict,
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User, list[ThirdPartyConsentLink]],
    ],
) -> None:
    """
    Tests that when a card is already registered, an error is raised.
    """
    req_data = add_register_req_data.copy()
    answer_fields = req_data["account"]
    loyalty_card_handler, loyalty_plan, questions, channel, user, consents = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, consents=True, journey=ADD_AND_REGISTER
    )

    new_loyalty_card = LoyaltyCardFactory(
        scheme=loyalty_plan, card_number=req_data["account"]["add_fields"]["credentials"][0]["value"]
    )

    db_session.flush()

    LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    db_session.commit()

    user_id, loyalty_plan_id = (
        user.id,
        loyalty_plan.id,
    )

    req_data["loyalty_plan_id"] = loyalty_plan_id
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/add_and_register",
        json=req_data,
        method="POST",
        user_id=user_id,
        channel="com.test.channel",
    )
    assert resp.status == falcon.HTTP_409
    error_msg = "Card is already registered. Use POST /loyalty_cards/add_and_authorise to add this card to your wallet."
    assert resp.json == {
        "error_message": error_msg,
        "error_slug": "ALREADY_REGISTERED",
    }

    mock_send_message_to_hermes.assert_not_called()
