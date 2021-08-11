import typing
import unittest.mock

import faker
import pytest

if typing.TYPE_CHECKING:
    from unittest.mock import MagicMock

    from sqlalchemy.orm import Session

from app.api.exceptions import ValidationError
from app.hermes.models import SchemeAccountUserAssociation, SchemeChannelAssociation, SchemeCredentialQuestion, Scheme
from app.handlers.loyalty_card import ADD, AUTHORISE, ADD_AND_AUTHORISE, JOIN, REGISTER, CredentialClass, LoyaltyCardHandler
from tests.factories import LoyaltyCardHandlerFactory, LoyaltyCardFactory, LoyaltyPlanFactory, \
                            LoyaltyPlanQuestionFactory, UserFactory, ChannelFactory


@pytest.fixture(scope="function")
def setup_plan_channel_and_user(db_session: "Session"):

    def _setup_plan_channel_and_user(channel_link: bool = True):
        loyalty_plan = LoyaltyPlanFactory()
        channel = ChannelFactory()
        user = UserFactory(client=channel.client_application)

        db_session.flush()

        if channel_link:
            sca = SchemeChannelAssociation(status=0, bundle_id=channel.id, scheme_id=loyalty_plan.id, test_scheme=False)
            db_session.add(sca)

        db_session.flush()

        return loyalty_plan, channel, user

    return _setup_plan_channel_and_user


@pytest.fixture(scope="function")
def setup_questions(db_session: "Session", setup_plan_channel_and_user):

    def _setup_questions(loyalty_plan):

        questions = [LoyaltyPlanQuestionFactory(scheme_id=loyalty_plan.id, type='card_number', label='Card Number',
                                                add_field=True,
                                                manual_question=True),
                     LoyaltyPlanQuestionFactory(scheme_id=loyalty_plan.id, type='barcode', label='Barcode',
                                                add_field=True),
                     LoyaltyPlanQuestionFactory(scheme_id=loyalty_plan.id, type='email', label='Email',
                                                auth_field=True),
                     LoyaltyPlanQuestionFactory(scheme_id=loyalty_plan.id, type='password', label='Password',
                                                auth_field=True),
                     LoyaltyPlanQuestionFactory(scheme_id=loyalty_plan.id, type='postcode', label='Postcode',
                                                register_field=True)]

        db_session.flush()

        return questions

    return _setup_questions


@pytest.fixture(scope="function")
def setup_loyalty_card_handler(db_session: "Session", setup_plan_channel_and_user, setup_questions):

    def _setup_loyalty_card_handler(channel_link: bool = True, questions: bool = True, all_answer_fields = {},
                                    journey=ADD, loyalty_plan_id=None):
        loyalty_plan, channel, user = setup_plan_channel_and_user(channel_link)

        if questions:
            questions = setup_questions(loyalty_plan)
        else:
            questions = []

        loyalty_plan_id = loyalty_plan.id if None else loyalty_plan_id

        db_session.commit()

        loyalty_card_handler = LoyaltyCardHandlerFactory(db_session=db_session,
                                                         user_id=user.id,
                                                         loyalty_plan_id=loyalty_plan_id,
                                                         all_answer_fields=all_answer_fields,
                                                         journey=journey)

        return loyalty_card_handler, loyalty_plan, questions, channel, user

    return _setup_loyalty_card_handler


def test_fetch_plan_and_questions(db_session: "Session", setup_loyalty_card_handler):
    """ Tests that plan questions and scheme are successfully fetched"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    loyalty_card_handler.retrieve_plan_questions_and_answer_fields()

    assert len(loyalty_card_handler.plan_credential_questions[CredentialClass.ADD_FIELD]) == 2
    assert len(loyalty_card_handler.plan_credential_questions[CredentialClass.AUTH_FIELD]) == 2
    assert len(loyalty_card_handler.plan_credential_questions[CredentialClass.JOIN_FIELD]) == 0
    assert len(loyalty_card_handler.plan_credential_questions[CredentialClass.REGISTER_FIELD]) == 1

    assert isinstance(loyalty_card_handler.loyalty_plan, Scheme)

    for cred_class in CredentialClass:
        for question in loyalty_card_handler.plan_credential_questions[cred_class]:
            assert isinstance(loyalty_card_handler.plan_credential_questions[cred_class][question],
                              SchemeCredentialQuestion)


def test_error_if_plan_not_found(db_session: "Session", setup_loyalty_card_handler):
    """ Tests that ValidationError occurs if no plan is found"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
                                                                                loyalty_plan_id=3)

    with pytest.raises(ValidationError):
        loyalty_card_handler.retrieve_plan_questions_and_answer_fields()


def test_error_if_questions_not_found(db_session: "Session", setup_loyalty_card_handler):
    """ Tests that ValidationError occurs if no questions are found"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(questions=False)

    with pytest.raises(ValidationError):
        loyalty_card_handler.retrieve_plan_questions_and_answer_fields()


def test_error_if_channel_link_not_found(db_session: "Session", setup_loyalty_card_handler):
    """ Tests that ValidationError occurs if no linked channel is found"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(channel_link=False)

    with pytest.raises(ValidationError):
        loyalty_card_handler.retrieve_plan_questions_and_answer_fields()


def test_answer_parsing(db_session: "Session", setup_loyalty_card_handler):
    """ Tests that provided credential answers are successfully parsed"""

    answer_fields = {
        "add_fields": [
            {
                "credential_slug": "card_number",
                "value": "9511143200133540455525"
            }
        ],
        "authorise_fields": [
            {
                "credential_slug": "email",
                "value": "my_email@email.com"
            },
            {
                "credential_slug": "password",
                "value": "iLoveTests33"
            }
        ],
        "enrol_fields": [
            {
            }
        ]
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=answer_fields
    )
    loyalty_card_handler.retrieve_plan_questions_and_answer_fields()

    assert loyalty_card_handler.add_fields == [
            {
                "credential_slug": "card_number",
                "value": "9511143200133540455525"
            }
        ]

    assert loyalty_card_handler.auth_fields == [
            {
                "credential_slug": "email",
                "value": "my_email@email.com"
            },
            {
                "credential_slug": "password",
                "value": "iLoveTests33"
            }
        ]

    assert loyalty_card_handler.join_fields == [{}]
    assert loyalty_card_handler.register_fields == []


def test_credential_validation_add_fields_only(db_session: "Session", setup_loyalty_card_handler):

    answer_fields = {
        "add_fields": [
            {
                "credential_slug": "card_number",
                "value": "9511143200133540455525"
            }
        ],
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(all_answer_fields=answer_fields)

    assert True


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
