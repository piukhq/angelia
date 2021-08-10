import typing
import unittest.mock

import faker
import pytest

if typing.TYPE_CHECKING:
    from unittest.mock import MagicMock

    from sqlalchemy.orm import Session

from app.api.exceptions import ValidationError
from app.hermes.models import SchemeAccountUserAssociation, SchemeChannelAssociation, SchemeCredentialQuestion, Scheme
from app.handlers.loyalty_card import ADD, AUTHORISE, ADD_AND_AUTHORISE, JOIN, REGISTER, CredentialClass
from tests.factories import LoyaltyCardHandlerFactory, LoyaltyCardFactory, LoyaltyPlanFactory, \
                            LoyaltyPlanQuestionFactory, UserFactory, ChannelFactory


@pytest.fixture(scope="function", autouse=True)
def data_setup(db_session):
    db_session.commit()


def test_fetch_plan_and_questions(db_session: "Session"):
    """ Tests that plan questions and scheme are successfully fetched"""

    loyalty_plan = LoyaltyPlanFactory()
    channel = ChannelFactory()
    user = UserFactory(client=channel.client_application)
    db_session.flush()

    LoyaltyPlanQuestionFactory(scheme_id=loyalty_plan.id, type='card_number', label='Card Number', add_field=True)
    LoyaltyPlanQuestionFactory(scheme_id=loyalty_plan.id, type='barcode', label='Barcode', add_field=True)
    LoyaltyPlanQuestionFactory(scheme_id=loyalty_plan.id, type='email', label='Email', enrol_field=True)

    sca = SchemeChannelAssociation(status=0, bundle_id=channel.id, scheme_id=loyalty_plan.id, test_scheme=False)
    db_session.add(sca)
    db_session.commit()

    loyalty_card_handler = LoyaltyCardHandlerFactory(db_session=db_session, user_id=user.id, journey=ADD,
                                                     all_answer_fields={})

    loyalty_card_handler.retrieve_plan_questions_and_answer_fields()

    assert len(loyalty_card_handler.plan_credential_questions[CredentialClass.ADD_FIELD]) == 2
    assert len(loyalty_card_handler.plan_credential_questions[CredentialClass.ENROL_FIELD]) == 1
    assert isinstance(loyalty_card_handler.loyalty_plan, Scheme)

    for cred_class in CredentialClass:
        for question in loyalty_card_handler.plan_credential_questions[cred_class]:
            assert isinstance(loyalty_card_handler.plan_credential_questions[cred_class][question],
                              SchemeCredentialQuestion)


def test_error_if_plan_not_found(db_session: "Session"):

    loyalty_plan = LoyaltyPlanFactory()
    channel = ChannelFactory()
    user = UserFactory(client=channel.client_application)
    db_session.flush()

    LoyaltyPlanQuestionFactory(scheme_id=loyalty_plan.id, type='card_number', label='Card Number', add_field=True)

    sca = SchemeChannelAssociation(status=0, bundle_id=channel.id, scheme_id=loyalty_plan.id, test_scheme=False)
    db_session.add(sca)
    db_session.commit()

    loyalty_card_handler = LoyaltyCardHandlerFactory(db_session=db_session, user_id=user.id, journey=ADD,
                                                     all_answer_fields={}, loyalty_plan_id=3)

    with pytest.raises(ValidationError):
        loyalty_card_handler.retrieve_plan_questions_and_answer_fields()


"""
1. Test parsing of add/auth etc. fields
2. Test creation of scheme account
3. Test that existing user is linked to account successfully
3b. Test that if not existing user, error thrown
4. Test that message is sent to Hermes (via patch)
5. Test that barcode/card_number are generated and entered into db
6. Test that credential 

FETCH AND HANDLE QUESTIONS
PARSE AND COMPARE ANSWERS
RETURN EXISTING OR CREATE
SEND TO HERMES

"""
