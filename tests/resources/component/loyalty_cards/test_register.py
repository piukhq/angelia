import typing
from unittest.mock import call, patch

import falcon
import pytest
from sqlalchemy.future import select

from app.handlers.loyalty_card import REGISTER, LoyaltyCardHandler
from app.hermes.models import (
    Channel,
    Consent,
    Scheme,
    SchemeAccountUserAssociation,
    SchemeCredentialQuestion,
    ThirdPartyConsentLink,
    User,
)
from tests.factories import (
    LoyaltyCardFactory,
    LoyaltyCardStatus,
    LoyaltyCardUserAssociationFactory,
    LoyaltyPlanQuestionFactory,
    UserFactory,
)
from tests.helpers.authenticated_request import get_authenticated_request

if typing.TYPE_CHECKING:
    from unittest.mock import MagicMock

    from sqlalchemy.orm import Session


@pytest.mark.parametrize(
    "lc_status,http_status",
    [
        (
            LoyaltyCardStatus.REGISTRATION_ASYNC_IN_PROGRESS,
            falcon.HTTP_200,
        ),
        (
            LoyaltyCardStatus.WALLET_ONLY,
            falcon.HTTP_202,
        ),
    ],
    ids=("200", "202"),
)
@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_on_put_register(
    mock_send_message_to_hermes: "MagicMock",
    lc_status: str,
    http_status: str,
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User, list[ThirdPartyConsentLink]],
    ],
) -> None:
    """Tests happy path for register journey"""

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

    loyalty_card_handler, loyalty_plan, questions, channel, user, consents = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, consents=True, journey=REGISTER
    )
    db_session.flush()

    # adding an optional credential question to check that not providing an answer for it still result in success.
    LoyaltyPlanQuestionFactory(
        type="random",
        label="Random",
        scheme_id=loyalty_plan.id,
        is_optional=True,
        register_field=True,
        enrol_field=True,
    )

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525")
    db_session.flush()

    user_id, new_loyalty_card_id = user.id, new_loyalty_card.id

    user_asc = LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=user.id,
        link_status=lc_status,
    )

    db_session.commit()

    loyalty_card_handler.link_to_user = user_asc
    loyalty_card_handler.card_id = new_loyalty_card.id
    payload = {
        "account": {
            "register_ghost_card_fields": {
                "credentials": answer_fields["register_ghost_card_fields"]["credentials"],
                "consents": answer_fields["register_ghost_card_fields"]["consents"],
            },
        },
    }

    resp = get_authenticated_request(
        path=f"/v2/loyalty_cards/{new_loyalty_card_id}/register",
        json=payload,
        method="PUT",
        user_id=user_id,
        channel="com.test.channel",
    )

    assert resp.status == http_status
    assert resp.json == {"id": new_loyalty_card_id}
    if http_status == falcon.HTTP_202:
        link = db_session.execute(
            select(SchemeAccountUserAssociation).where(
                SchemeAccountUserAssociation.scheme_account_id == new_loyalty_card_id,
                SchemeAccountUserAssociation.user_id == user_id,
            )
        ).scalar_one_or_none()
        consent_id = db_session.execute(select(Consent.id).where(Consent.slug == "Consent_1")).scalar_one_or_none()
        assert mock_send_message_to_hermes.mock_calls == [
            call(
                "loyalty_card_register",
                {
                    "loyalty_plan_id": loyalty_plan.id,
                    "loyalty_card_id": new_loyalty_card_id,
                    "entry_id": link.id,
                    "user_id": user_id,
                    "channel_slug": "com.test.channel",
                    "journey": "REGISTER",
                    "auto_link": True,
                    "register_fields": [
                        {"credential_slug": "postcode", "value": "007"},
                    ],
                    "consents": [{"id": consent_id, "value": "consent_value"}],
                },
            )
        ]
    else:
        assert not mock_send_message_to_hermes.called


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_on_put_register_already_registered(
    mock_send_message_to_hermes: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User, list[ThirdPartyConsentLink]],
    ],
) -> None:
    """Tests that registration journey errors when found card is already active or pre-registered"""

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

    loyalty_card_handler, loyalty_plan, questions, channel, user, consents = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, consents=True, journey=REGISTER
    )
    db_session.flush()

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525")
    db_session.flush()
    new_loyalty_card_id = new_loyalty_card.id

    other_user = UserFactory(client=channel.client_application)

    db_session.flush()

    user_asc = LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=other_user.id,
        link_status=LoyaltyCardStatus.PRE_REGISTERED_CARD,
    )

    loyalty_card_handler.link_to_user = user_asc
    loyalty_card_handler.card_id = new_loyalty_card.id
    loyalty_card_handler.card = new_loyalty_card

    db_session.commit()

    payload = {
        "account": {
            "register_ghost_card_fields": {
                "credentials": answer_fields["register_ghost_card_fields"]["credentials"],
                "consents": answer_fields["register_ghost_card_fields"]["consents"],
            },
        },
    }

    resp = get_authenticated_request(
        path=f"/v2/loyalty_cards/{new_loyalty_card.id}/register",
        json=payload,
        method="PUT",
        user_id=other_user.id,
        channel="com.test.channel",
    )

    assert resp.status == falcon.HTTP_409
    assert resp.json == {
        "error_message": f"Card is already registered. Use PUT /loyalty_cards/{new_loyalty_card_id}/authorise"
        " to authorise this card in your wallet, or to update authorisation credentials.",
        "error_slug": "ALREADY_REGISTERED",
    }
    assert not mock_send_message_to_hermes.called


def test_on_put_register_incorrect_payload_422() -> None:
    resp = get_authenticated_request(
        path="/v2/loyalty_cards/1/register", json={"dead": "beef"}, method="PUT", user_id=1, channel="com.test.channel"
    )
    assert resp.status == falcon.HTTP_422
    assert resp.json["error_message"] == "Could not validate fields"
    assert resp.json["error_slug"] == "FIELD_VALIDATION_ERROR"
    assert "extra keys not allowed @ data['dead']" in resp.json["fields"]
    assert "required key not provided @ data['account']" in resp.json["fields"]
