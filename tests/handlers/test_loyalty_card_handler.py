import typing
import unittest.mock

import faker
import pytest

if typing.TYPE_CHECKING:
    from unittest.mock import MagicMock

    from sqlalchemy.orm import Session

from app.hermes.models import SchemeAccountUserAssociation
from app.handlers.loyalty_card import ADD, AUTHORISE, ADD_AND_AUTHORISE, JOIN, REGISTER
from tests.factories import LoyaltyCardHandlerFactory, LoyaltyCardFactory, LoyaltyPlanFactory, LoyaltyPlanQuestionFactory, UserFactory


@pytest.fixture(scope="function", autouse=True)
def data_setup(db_session):

    db_session.commit()


def test_fetch_plan_questions(db_session: "Session"):
    """ Tests that plan questions are successfully fetched"""

    user = UserFactory()
    loyalty_plan = LoyaltyPlanFactory(category_id=3)
    db_session.flush()
    card_number_question = LoyaltyPlanQuestionFactory(scheme_id=loyalty_plan.id, type='card_number', label='Card Number',
                                                      add_field=True)
    barcode_question = LoyaltyPlanQuestionFactory(scheme_id=loyalty_plan.id, type='barcode', label='Barcode',
                                                  add_field=True)
    email_question = LoyaltyPlanQuestionFactory(scheme_id=loyalty_plan.id, type='email', label='Email')
    db_session.commit()

    journey = ADD
    all_answer_fields = {}

    loyalty_card_handler = LoyaltyCardHandlerFactory(db_session=db_session, user_id=user.id, journey=ADD, all_answer_fields={})


"""
1. Test parsing of add/auth etc. fields
2. Test creation of scheme account
3. Test that existing user is linked to account successfully
3b. Test that if not existing user, error thrown
4. Test that message is sent to Hermes (via patch)
5. Test that barcode/cardnumber are generated and entered into db
6. Test that credential 

FETCH AND HANDLE QUESTIONS
PARSE AND COMPARE ANSWERS
RETURN EXISTING OR CREATE
SEND TO HERMES

"""
