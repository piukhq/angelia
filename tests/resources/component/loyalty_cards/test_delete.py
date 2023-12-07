import typing
from unittest.mock import call, patch

import falcon
import pytest
from sqlalchemy.future import select

from app.handlers.loyalty_card import REGISTER, LoyaltyCardHandler
from app.hermes.models import Channel, Scheme, SchemeAccountUserAssociation, SchemeCredentialQuestion, User
from tests.factories import (
    LoyaltyCardFactory,
    LoyaltyCardStatus,
    LoyaltyCardUserAssociationFactory,
    LoyaltyPlanQuestionFactory,
)
from tests.helpers.authenticated_request import get_authenticated_request

if typing.TYPE_CHECKING:
    from unittest.mock import MagicMock

    from sqlalchemy.orm import Session


@pytest.mark.parametrize(
    "link_status,http_status",
    [
        (
            LoyaltyCardStatus.JOIN_ASYNC_IN_PROGRESS,
            falcon.HTTP_409,
        ),
        (
            LoyaltyCardStatus.ACTIVE,
            falcon.HTTP_202,
        ),
    ],
    ids=("409", "202"),
)
@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_delete_by_id(
    mock_send_message_to_hermes: "MagicMock",
    link_status: str,
    http_status: str,
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that deletion of loyalty card is successful"""

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

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
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
    db_session.flush()

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525")
    db_session.flush()

    user_id, new_loyalty_card_id = user.id, new_loyalty_card.id

    user_asc = LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=user_id,
        link_status=link_status,
    )

    db_session.commit()

    loyalty_card_handler.link_to_user = user_asc
    loyalty_card_handler.card_id = new_loyalty_card.id

    resp = get_authenticated_request(
        path=f"/v2/loyalty_cards/{new_loyalty_card_id}",
        method="DELETE",
        user_id=user_id,
        channel="com.test.channel",
    )
    assert resp.status == http_status
    if http_status == falcon.HTTP_202:
        entry_id = db_session.execute(
            select(SchemeAccountUserAssociation.id).where(
                SchemeAccountUserAssociation.scheme_account_id == new_loyalty_card_id,
                SchemeAccountUserAssociation.user_id == user_id,
            )
        ).scalar_one()
        assert mock_send_message_to_hermes.mock_calls == [
            call(
                "delete_loyalty_card",
                {
                    "loyalty_plan_id": None,
                    "loyalty_card_id": new_loyalty_card_id,
                    "entry_id": entry_id,
                    "user_id": user_id,
                    "channel_slug": "com.test.channel",
                    "journey": "DELETE",
                    "auto_link": True,
                },
            )
        ]
    else:
        assert resp.json == {
            "error_message": "Loyalty card cannot be deleted until the Join process has completed",
            "error_slug": "JOIN_IN_PROGRESS",
        }
        assert not mock_send_message_to_hermes.mock_calls
