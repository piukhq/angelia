import typing
from unittest.mock import patch

import falcon
import pytest

if typing.TYPE_CHECKING:
    from unittest.mock import MagicMock

    from sqlalchemy.orm import Session

from app.api.exceptions import CredentialError, ResourceNotFoundError, ValidationError
from app.api.helpers.vault import AESKeyNames
from app.handlers.loyalty_card import ADD, ADD_AND_AUTHORISE, ADD_AND_REGISTER, CredentialClass
from app.hermes.models import (
    Scheme,
    SchemeAccount,
    SchemeAccountCredentialAnswer,
    SchemeAccountUserAssociation,
    SchemeChannelAssociation,
    SchemeCredentialQuestion,
)
from app.lib.encryption import AESCipher
from app.lib.loyalty_card import LoyaltyCardStatus
from tests.factories import (
    ChannelFactory,
    ClientApplicationFactory,
    ConsentFactory,
    LoyaltyCardFactory,
    LoyaltyCardHandlerFactory,
    LoyaltyCardUserAssociationFactory,
    LoyaltyPlanAnswerFactory,
    LoyaltyPlanFactory,
    LoyaltyPlanQuestionFactory,
    ThirdPartyConsentLinkFactory,
    UserFactory,
)


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

        questions = [
            LoyaltyPlanQuestionFactory(
                id=1,
                scheme_id=loyalty_plan.id,
                type="card_number",
                label="Card Number",
                add_field=True,
                manual_question=True,
            ),
            LoyaltyPlanQuestionFactory(
                id=2, scheme_id=loyalty_plan.id, type="barcode", label="Barcode", add_field=True, scan_question=True
            ),
            LoyaltyPlanQuestionFactory(id=3, scheme_id=loyalty_plan.id, type="email", label="Email", auth_field=True),
            LoyaltyPlanQuestionFactory(
                id=4, scheme_id=loyalty_plan.id, type="password", label="Password", auth_field=True
            ),
            LoyaltyPlanQuestionFactory(
                id=5, scheme_id=loyalty_plan.id, type="postcode", label="Postcode", register_field=True
            ),
        ]

        db_session.flush()

        return questions

    return _setup_questions


@pytest.fixture(scope="function")
def setup_consents(db_session: "Session"):
    def _setup_consents(loyalty_plan, channel):

        consents = [
            ThirdPartyConsentLinkFactory(
                scheme=loyalty_plan,
                client_application=channel.client_application,
                register_field=True,
                consent=ConsentFactory(scheme=loyalty_plan, slug="Consent_1"),
            ),
            ThirdPartyConsentLinkFactory(
                scheme=loyalty_plan,
                client_application=channel.client_application,
                enrol_field=True,
                consent=ConsentFactory(scheme=loyalty_plan, slug="Consent_2"),
            ),
            ThirdPartyConsentLinkFactory(
                scheme=loyalty_plan,
                client_application=ClientApplicationFactory(
                    name="another_client_application",
                    client_id="490823fh",
                    organisation=channel.client_application.organisation,
                ),
                enrol_field=True,
                consent=ConsentFactory(scheme=loyalty_plan, slug="Consent_3"),
            ),
        ]

        db_session.flush()

        return consents

    return _setup_consents


@pytest.fixture(scope="function")
def setup_credentials(db_session: "Session"):
    # To help set up mock validated credentials for testing in later stages of the journey.
    # Only supports ADD for now but can add ADD_AND_AUTH etc.

    def _setup_credentials(loyalty_card_handler, credential_type):
        if credential_type == ADD:
            loyalty_card_handler.key_credential = {
                "credential_question_id": 1,
                "credential_type": "card_number",
                "credential_class": CredentialClass.ADD_FIELD,
                "key_credential": True,
                "credential_answer": "9511143200133540455525",
            }

            loyalty_card_handler.valid_credentials = {
                "card_number": {
                    "credential_question_id": 1,
                    "credential_type": "card_number",
                    "credential_class": CredentialClass.ADD_FIELD,
                    "key_credential": True,
                    "credential_answer": "9511143200133540455525",
                }
            }

    return _setup_credentials


@pytest.fixture(scope="function")
def setup_loyalty_card_handler(
    db_session: "Session", setup_plan_channel_and_user, setup_questions, setup_credentials, setup_consents
):
    def _setup_loyalty_card_handler(
        channel_link: bool = True,
        consents: bool = False,
        questions: bool = True,
        credentials: str = None,
        all_answer_fields: dict = None,
        journey: str = ADD,
        loyalty_plan_id: int = None,
    ):
        if not all_answer_fields:
            all_answer_fields = {}

        loyalty_plan, channel, user = setup_plan_channel_and_user(channel_link)

        if questions:
            questions = setup_questions(loyalty_plan)
        else:
            questions = []

        if loyalty_plan_id is None:
            loyalty_plan_id = loyalty_plan.id

        if consents:
            setup_consents(loyalty_plan, channel)

        db_session.commit()

        loyalty_card_handler = LoyaltyCardHandlerFactory(
            db_session=db_session,
            user_id=user.id,
            channel_id=channel.bundle_id,
            loyalty_plan_id=loyalty_plan_id,
            all_answer_fields=all_answer_fields,
            journey=journey,
        )

        if credentials:
            setup_credentials(loyalty_card_handler, credentials)

        return loyalty_card_handler, loyalty_plan, questions, channel, user

    return _setup_loyalty_card_handler


# ------------FETCHING QUESTIONS AND ANSWERS-----------


def test_fetch_plan_and_questions(db_session: "Session", setup_loyalty_card_handler):
    """Tests that plan questions and scheme are successfully fetched"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    loyalty_card_handler.retrieve_plan_questions_and_answer_fields()

    assert len(loyalty_card_handler.plan_credential_questions[CredentialClass.ADD_FIELD]) == 2
    assert len(loyalty_card_handler.plan_credential_questions[CredentialClass.AUTH_FIELD]) == 2
    assert len(loyalty_card_handler.plan_credential_questions[CredentialClass.JOIN_FIELD]) == 0
    assert len(loyalty_card_handler.plan_credential_questions[CredentialClass.REGISTER_FIELD]) == 1

    assert isinstance(loyalty_card_handler.loyalty_plan, Scheme)

    for cred_class in CredentialClass:
        for question in loyalty_card_handler.plan_credential_questions[cred_class]:
            assert isinstance(
                loyalty_card_handler.plan_credential_questions[cred_class][question], SchemeCredentialQuestion
            )


def test_fetch_consents_register(db_session: "Session", setup_loyalty_card_handler):
    """Tests that plan consents are successfully fetched"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        journey=ADD_AND_REGISTER, consents=True
    )

    loyalty_card_handler.retrieve_plan_questions_and_answer_fields()

    assert loyalty_card_handler.plan_consent_questions
    assert len(loyalty_card_handler.plan_consent_questions) == 1


def test_error_if_plan_not_found(db_session: "Session", setup_loyalty_card_handler):
    """Tests that ValidationError occurs if no plan is found"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(loyalty_plan_id=3)

    with pytest.raises(ValidationError):
        loyalty_card_handler.retrieve_plan_questions_and_answer_fields()


def test_error_if_questions_not_found(db_session: "Session", setup_loyalty_card_handler):
    """Tests that ValidationError occurs if no questions are found"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(questions=False)

    with pytest.raises(ValidationError):
        loyalty_card_handler.retrieve_plan_questions_and_answer_fields()


def test_error_if_channel_link_not_found(db_session: "Session", setup_loyalty_card_handler):
    """Tests that ValidationError occurs if no linked channel is found"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(channel_link=False)

    with pytest.raises(ValidationError):
        loyalty_card_handler.retrieve_plan_questions_and_answer_fields()


def test_answer_parsing(db_session: "Session", setup_loyalty_card_handler):
    """Tests that provided credential answers are successfully parsed"""

    answer_fields = {
        "add_fields": {"credentials": [{"credential_slug": "card_number", "value": "9511143200133540455525"}]},
        "authorise_fields": {
            "credentials": [
                {"credential_slug": "email", "value": "my_email@email.com"},
                {"credential_slug": "password", "value": "iLoveTests33"},
            ]
        },
        "enrol_fields": {},
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=answer_fields
    )
    loyalty_card_handler.retrieve_plan_questions_and_answer_fields()

    assert loyalty_card_handler.add_fields == [{"credential_slug": "card_number", "value": "9511143200133540455525"}]

    assert loyalty_card_handler.auth_fields == [
        {"credential_slug": "email", "value": "my_email@email.com"},
        {"credential_slug": "password", "value": "iLoveTests33"},
    ]

    assert loyalty_card_handler.join_fields == []
    assert loyalty_card_handler.register_fields == []


def test_fetch_single_card_link(db_session: "Session", setup_loyalty_card_handler):
    """Tests that a single card link is successfully fetched"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    new_loyalty_card = LoyaltyCardFactory(
        scheme=loyalty_plan, card_number="9511143200133540455525", main_answer="9511143200133540455525"
    )

    db_session.flush()

    LoyaltyCardUserAssociationFactory(scheme_account_id=new_loyalty_card.id, user_id=user.id, auth_provided=False)

    db_session.commit()

    loyalty_card_handler.card_id = new_loyalty_card.id
    card_link = loyalty_card_handler.fetch_and_check_single_card_user_link()

    assert card_link
    assert isinstance(card_link, SchemeAccountUserAssociation)


def test_error_fetch_single_card_link_404(db_session: "Session", setup_loyalty_card_handler):
    """Tests that a single card link is successfully fetched"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    db_session.commit()

    loyalty_card_handler.card_id = 99

    with pytest.raises(ResourceNotFoundError):
        loyalty_card_handler.fetch_and_check_single_card_user_link()


def test_auth_fetch_card_link(db_session: "Session", setup_loyalty_card_handler):
    """Tests that card link is successfully fetched for auth journey"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    new_loyalty_card = LoyaltyCardFactory(
        scheme=loyalty_plan, card_number="9511143200133540455525", main_answer="9511143200133540455525"
    )

    db_session.flush()

    LoyaltyCardUserAssociationFactory(scheme_account_id=new_loyalty_card.id, user_id=user.id, auth_provided=False)

    db_session.commit()

    loyalty_card_handler.card_id = new_loyalty_card.id
    loyalty_card_handler.auth_fetch_and_check_existing_card_link()

    assert loyalty_card_handler.primary_auth is True
    assert loyalty_card_handler.card
    assert loyalty_card_handler.loyalty_plan
    assert loyalty_card_handler.loyalty_plan_id


def test_auth_fetch_card_link_not_primary_auth(db_session: "Session", setup_loyalty_card_handler):
    """Tests that card link is successfully fetched for auth journey, primary_auth is False"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    new_loyalty_card = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number="9511143200133540455525",
        main_answer="9511143200133540455525",
        status=LoyaltyCardStatus.ACTIVE,
    )

    other_user = UserFactory(client=channel.client_application)

    db_session.flush()

    LoyaltyCardUserAssociationFactory(scheme_account_id=new_loyalty_card.id, user_id=user.id, auth_provided=False)
    LoyaltyCardUserAssociationFactory(scheme_account_id=new_loyalty_card.id, user_id=other_user.id, auth_provided=True)

    db_session.commit()

    loyalty_card_handler.card_id = new_loyalty_card.id
    loyalty_card_handler.auth_fetch_and_check_existing_card_link()

    assert loyalty_card_handler.primary_auth is False
    assert loyalty_card_handler.card
    assert loyalty_card_handler.loyalty_plan
    assert loyalty_card_handler.loyalty_plan_id


def test_error_auth_fetch_card_link_not_found(db_session: "Session", setup_loyalty_card_handler):
    """Tests that fetching card link where none is present results in appropriate error for auth journey"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    new_loyalty_card = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number="9511143200133540455525",
        main_answer="9511143200133540455525",
        status=LoyaltyCardStatus.ACTIVE,
    )

    other_user = UserFactory(client=channel.client_application)

    db_session.flush()

    LoyaltyCardUserAssociationFactory(scheme_account_id=new_loyalty_card.id, user_id=other_user.id, auth_provided=True)

    db_session.commit()

    loyalty_card_handler.card_id = new_loyalty_card.id

    with pytest.raises(ResourceNotFoundError):
        loyalty_card_handler.auth_fetch_and_check_existing_card_link()


# ------------VALIDATION OF CREDENTIALS-----------


def test_credential_validation_add_fields_only(db_session: "Session", setup_loyalty_card_handler):
    """Tests that add credentials are successfully validated"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    loyalty_card_handler.add_fields = [{"credential_slug": "card_number", "value": "9511143200133540455525"}]
    loyalty_card_handler.plan_credential_questions = {
        "add_field": {"card_number": questions[0], "barcode": questions[1]},
        "auth_field": {"email": questions[2], "password": questions[3]},
        "enrol_field": {},
        "register_field": {"postcode": questions[4]},
    }

    loyalty_card_handler.validate_all_credentials()


def test_credential_validation_add_and_auth(db_session: "Session", setup_loyalty_card_handler):
    """Tests that add and auth credentials are successfully validated"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    loyalty_card_handler.add_fields = [{"credential_slug": "card_number", "value": "9511143200133540455525"}]

    loyalty_card_handler.auth_fields = [
        {"credential_slug": "email", "value": "my_email@email.com"},
        {"credential_slug": "password", "value": "iLoveTests33"},
    ]

    loyalty_card_handler.plan_credential_questions = {
        "add_field": {"card_number": questions[0], "barcode": questions[1]},
        "auth_field": {"email": questions[2], "password": questions[3]},
        "enrol_field": {},
        "register_field": {"postcode": questions[4]},
    }

    loyalty_card_handler.validate_all_credentials()


def test_credential_validation_error_missing_auth(db_session: "Session", setup_loyalty_card_handler):
    """Tests that ValidationError occurs when one or more auth credentials are missing"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    loyalty_card_handler.add_fields = [{"credential_slug": "card_number", "value": "9511143200133540455525"}]

    loyalty_card_handler.auth_fields = [
        {"credential_slug": "email", "value": "my_email@email.com"},
    ]

    loyalty_card_handler.plan_credential_questions = {
        "add_field": {"card_number": questions[0], "barcode": questions[1]},
        "auth_field": {"email": questions[2], "password": questions[3]},
        "enrol_field": {},
        "register_field": {"postcode": questions[4]},
    }

    with pytest.raises(ValidationError):
        loyalty_card_handler.validate_all_credentials()


def test_credential_validation_error_invalid_answer(db_session: "Session", setup_loyalty_card_handler):
    """Tests that ValidationError occurs when one or more credential answers do not match a plan question"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    loyalty_card_handler.add_fields = [{"credential_slug": "sombrero_size", "value": "42"}]

    loyalty_card_handler.plan_credential_questions = {
        "add_field": {"card_number": questions[0], "barcode": questions[1]},
        "auth_field": {"email": questions[2], "password": questions[3]},
        "enrol_field": {},
        "register_field": {"postcode": questions[4]},
    }

    with pytest.raises(ValidationError):
        loyalty_card_handler.validate_all_credentials()


def test_credential_validation_error_no_key_credential(db_session: "Session", setup_loyalty_card_handler):
    """Tests that ValidationError occurs when none of the provided credential are 'key credentials'"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    loyalty_card_handler.auth_fields = [
        {"credential_slug": "email", "value": "my_email@email.com"},
        {"credential_slug": "password", "value": "iLoveTests33"},
    ]

    loyalty_card_handler.plan_credential_questions = {
        "add_field": {"card_number": questions[0], "barcode": questions[1]},
        "auth_field": {"email": questions[2], "password": questions[3]},
        "enrol_field": {},
        "register_field": {"postcode": questions[4]},
    }

    with pytest.raises(ValidationError):
        loyalty_card_handler.validate_all_credentials()


def test_consent_validation(db_session: "Session", setup_loyalty_card_handler):
    """Tests that ValidationError occurs when none of the provided credential are 'key credentials'"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    loyalty_card_handler.all_answer_fields = {
        "register_ghost_card_fields": {
            "consents": [{"consent_slug": "Consent_1", "value": True}, {"consent_slug": "Consent_2", "value": True}]
        }
    }

    loyalty_card_handler.plan_consent_questions = [
        ConsentFactory(scheme=loyalty_plan, slug="Consent_1", id=1),
        ConsentFactory(scheme=loyalty_plan, slug="Consent_2", id=2),
    ]

    loyalty_card_handler.validate_and_refactor_consents()


def test_consent_validation_no_consents(db_session: "Session", setup_loyalty_card_handler):
    """Tests that ValidationError occurs when none of the provided credential are 'key credentials'"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    loyalty_card_handler.all_answer_fields = {"register_ghost_card_fields": {"consents": []}}

    loyalty_card_handler.validate_and_refactor_consents()


def test_error_consent_validation_no_matching_consent_questions(db_session: "Session", setup_loyalty_card_handler):
    """Tests that ValidationError occurs when none of the provided credential are 'key credentials'"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    loyalty_card_handler.all_answer_fields = {
        "register_ghost_card_fields": {
            "consents": [
                {"consent_slug": "Consent_1", "value": True},
            ]
        }
    }

    loyalty_card_handler.plan_consent_questions = [
        ConsentFactory(scheme=loyalty_plan, slug="Consent_1", id=1),
        ConsentFactory(scheme=loyalty_plan, slug="Consent_2", id=2),
    ]

    with pytest.raises(ValidationError):
        loyalty_card_handler.validate_and_refactor_consents()


def test_error_consent_validation_missing_consent(db_session: "Session", setup_loyalty_card_handler):
    """Tests that ValidationError occurs when none of the provided credential are 'key credentials'"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    loyalty_card_handler.all_answer_fields = {
        "register_ghost_card_fields": {
            "consents": [{"consent_slug": "Consent_1", "value": True}, {"consent_slug": "Consent_2", "value": True}]
        }
    }

    loyalty_card_handler.plan_consent_questions = []

    with pytest.raises(ValidationError):
        loyalty_card_handler.validate_and_refactor_consents()


def test_auth_fields_match(db_session: "Session", setup_loyalty_card_handler):
    """Tests that ValidationError occurs when none of the provided credential are 'key credentials'"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    cipher = AESCipher(AESKeyNames.LOCAL_AES_KEY)

    LoyaltyPlanAnswerFactory(
        question_id=3,
        scheme_account_id=loyalty_plan.id,
        answer="fake_email_1",
    )
    LoyaltyPlanAnswerFactory(
        question_id=4,
        scheme_account_id=loyalty_plan.id,
        answer=cipher.encrypt("fake_password_1").decode("utf-8"),
    )

    new_loyalty_card = LoyaltyCardFactory(
        scheme=loyalty_plan, card_number="9511143200133540455525", main_answer="9511143200133540455525"
    )

    db_session.commit()

    loyalty_card_handler.card_id = new_loyalty_card.id

    loyalty_card_handler.auth_fields = [
        {"credential_slug": "email", "value": "fake_email_1"},
        {"credential_slug": "password", "value": "fake_password_1"},
    ]

    existing_creds, match_all = loyalty_card_handler.check_auth_credentials_against_existing()

    assert existing_creds is True
    assert match_all is True


def test_auth_fields_do_not_match(db_session: "Session", setup_loyalty_card_handler):
    """Tests that ValidationError occurs when none of the provided credential are 'key credentials'"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    cipher = AESCipher(AESKeyNames.LOCAL_AES_KEY)

    LoyaltyPlanAnswerFactory(
        question_id=3,
        scheme_account_id=loyalty_plan.id,
        answer="fake_email_1",
    )
    LoyaltyPlanAnswerFactory(
        question_id=4,
        scheme_account_id=loyalty_plan.id,
        answer=cipher.encrypt("fake_password_1").decode("utf-8"),
    )

    new_loyalty_card = LoyaltyCardFactory(
        scheme=loyalty_plan, card_number="9511143200133540455525", main_answer="9511143200133540455525"
    )

    db_session.commit()

    loyalty_card_handler.card_id = new_loyalty_card.id

    loyalty_card_handler.auth_fields = [
        {"credential_slug": "email", "value": "incorrect_email"},
        {"credential_slug": "password", "value": "incorrect_password"},
    ]

    existing_creds, match_all = loyalty_card_handler.check_auth_credentials_against_existing()

    assert existing_creds is True
    assert match_all is False


def test_no_existing_auth_fields(db_session: "Session", setup_loyalty_card_handler):
    """Tests that ValidationError occurs when none of the provided credential are 'key credentials'"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    new_loyalty_card = LoyaltyCardFactory(
        scheme=loyalty_plan, card_number="9511143200133540455525", main_answer="9511143200133540455525"
    )

    db_session.commit()

    loyalty_card_handler.card_id = new_loyalty_card.id

    loyalty_card_handler.auth_fields = [
        {"credential_slug": "email", "value": "incorrect_email"},
        {"credential_slug": "password", "value": "incorrect_password"},
    ]

    existing_creds, match_all = loyalty_card_handler.check_auth_credentials_against_existing()

    assert existing_creds is False


def test_error_auth_fields_do_not_match_non_primary_auth(db_session: "Session", setup_loyalty_card_handler):
    """Tests that ValidationError occurs when none of the provided credential are 'key credentials'"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    cipher = AESCipher(AESKeyNames.LOCAL_AES_KEY)

    LoyaltyPlanAnswerFactory(
        question_id=3,
        scheme_account_id=loyalty_plan.id,
        answer="fake_email_1",
    )
    LoyaltyPlanAnswerFactory(
        question_id=4,
        scheme_account_id=loyalty_plan.id,
        answer=cipher.encrypt("fake_password_1").decode("utf-8"),
    )

    new_loyalty_card = LoyaltyCardFactory(
        scheme=loyalty_plan, card_number="9511143200133540455525", main_answer="9511143200133540455525"
    )

    db_session.commit()

    loyalty_card_handler.card_id = new_loyalty_card.id

    loyalty_card_handler.auth_fields = [
        {"credential_slug": "email", "value": "incorrect_email"},
        {"credential_slug": "password", "value": "incorrect_password"},
    ]

    loyalty_card_handler.primary_auth = False

    with pytest.raises(CredentialError):
        loyalty_card_handler.check_auth_credentials_against_existing()


# ------------LOYALTY CARD CREATION/RETURN-----------


def test_barcode_generation_no_regex(db_session: "Session", setup_loyalty_card_handler):
    """Tests barcode is not generated from card_number where there is no barcode_regex"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    loyalty_card_handler.key_credential = {
        "credential_question_id": 1,
        "credential_type": "card_number",
        "credential_class": CredentialClass.ADD_FIELD,
        "key_credential": True,
        "credential_answer": "9511143200133540455525",
    }

    loyalty_card_handler.valid_credentials = {
        "card_number": {
            "credential_question_id": 1,
            "credential_type": "card_number",
            "credential_class": CredentialClass.ADD_FIELD,
            "key_credential": True,
            "credential_answer": "9511143200133540455525",
        }
    }

    loyalty_card_handler.loyalty_plan = loyalty_plan

    card_number, barcode = loyalty_card_handler._get_card_number_and_barcode()

    assert card_number == "9511143200133540455525"
    assert barcode is None


def test_card_number_generation(db_session: "Session", setup_loyalty_card_handler):
    """Tests card_number generation from barcode"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    loyalty_plan_alt = LoyaltyPlanFactory(card_number_regex="^9794([0-9]+)", card_number_prefix="634004")

    loyalty_card_handler.loyalty_plan = loyalty_plan_alt

    loyalty_card_handler.key_credential = {
        "credential_question_id": 1,
        "credential_type": "barcode",
        "credential_class": CredentialClass.ADD_FIELD,
        "key_credential": True,
        "credential_answer": "9794111",
    }

    loyalty_card_handler.valid_credentials = {
        "card_number": {
            "credential_question_id": 1,
            "credential_type": "barcode",
            "credential_class": CredentialClass.ADD_FIELD,
            "key_credential": True,
            "credential_answer": "9794111",
        }
    }

    card_number, barcode = loyalty_card_handler._get_card_number_and_barcode()

    assert card_number == "634004111"
    assert barcode == "9794111"


def test_barcode_generation(db_session: "Session", setup_loyalty_card_handler):
    """Tests barcode generation from card_number"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    loyalty_plan_alt = LoyaltyPlanFactory(barcode_regex="^634004([0-9]+)", barcode_prefix="9794")

    loyalty_card_handler.loyalty_plan = loyalty_plan_alt

    loyalty_card_handler.key_credential = {
        "credential_question_id": 1,
        "credential_type": "card_number",
        "credential_class": CredentialClass.ADD_FIELD,
        "key_credential": True,
        "credential_answer": "634004111",
    }

    loyalty_card_handler.valid_credentials = {
        "card_number": {
            "credential_question_id": 1,
            "credential_type": "card_number",
            "credential_class": CredentialClass.ADD_FIELD,
            "key_credential": True,
            "credential_answer": "634004111",
        }
    }

    card_number, barcode = loyalty_card_handler._get_card_number_and_barcode()

    assert card_number == "634004111"
    assert barcode == "9794111"


@patch("app.handlers.loyalty_card.LoyaltyCardHandler.link_account_to_user")
def test_new_loyalty_card_add_routing_existing_not_linked(
    mock_link_existing_account: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler,
):
    """Tests query and routing for an existing Loyalty Card not linked to this user"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(credentials=ADD)

    new_loyalty_card = LoyaltyCardFactory(
        scheme=loyalty_plan, card_number="9511143200133540455525", main_answer="9511143200133540455525"
    )

    other_user = UserFactory(client=channel.client_application)

    db_session.flush()

    association = SchemeAccountUserAssociation(
        scheme_account_id=new_loyalty_card.id, user_id=other_user.id, auth_provided=False
    )

    db_session.add(association)
    db_session.commit()

    created = loyalty_card_handler.link_user_to_existing_or_create()

    assert mock_link_existing_account.called is True
    assert created is False


def test_new_loyalty_card_add_routing_existing_already_linked(db_session: "Session", setup_loyalty_card_handler):
    """Tests query and routing for an existing Loyalty Card already linked to this user"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(credentials=ADD)

    new_loyalty_card = LoyaltyCardFactory(
        scheme=loyalty_plan, card_number="9511143200133540455525", main_answer="9511143200133540455525"
    )

    db_session.flush()

    association = SchemeAccountUserAssociation(
        scheme_account_id=new_loyalty_card.id, user_id=user.id, auth_provided=False
    )
    db_session.add(association)

    db_session.commit()

    created = loyalty_card_handler.link_user_to_existing_or_create()

    assert loyalty_card_handler.card_id == new_loyalty_card.id
    assert created is False


@patch("app.handlers.loyalty_card.LoyaltyCardHandler.create_new_loyalty_card")
def test_new_loyalty_card_add_routing_create(
    mock_create_card: "MagicMock", db_session: "Session", setup_loyalty_card_handler
):
    """Tests query and routing for a non-existent Loyalty Card (Create journey)"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(credentials=ADD)

    created = loyalty_card_handler.link_user_to_existing_or_create()

    assert mock_create_card.called is True
    assert created is True


@patch("app.handlers.loyalty_card.LoyaltyCardHandler.link_account_to_user")
def test_new_loyalty_card_create_card_and_answers(
    mock_link_new_loyalty_card: "MagicMock", db_session: "Session", setup_loyalty_card_handler
):
    """Tests creation of a new Loyalty Card"""
    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(credentials=ADD)

    loyalty_card_handler.loyalty_plan = loyalty_plan

    loyalty_card_handler.create_new_loyalty_card()

    loyalty_cards = (
        db_session.query(SchemeAccount)
        .filter(
            SchemeAccount.id == 1,
        )
        .all()
    )

    cred_answers_count = (
        db_session.query(SchemeAccount)
        .filter(
            SchemeAccountCredentialAnswer.scheme_account_id == 1,
        )
        .count()
    )

    assert mock_link_new_loyalty_card.called is True
    assert len(loyalty_cards) == 1
    assert loyalty_cards[0].scheme == loyalty_plan
    assert cred_answers_count == 1


def test_link_existing_loyalty_card(db_session: "Session", setup_loyalty_card_handler):
    """Tests linking of an existing Loyalty Card"""
    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan)

    db_session.commit()

    loyalty_card_handler.card_id = new_loyalty_card.id

    loyalty_card_handler.link_account_to_user()

    association = (
        db_session.query(SchemeAccountUserAssociation)
        .filter(
            SchemeAccountUserAssociation.scheme_account_id == new_loyalty_card.id,
            SchemeAccountUserAssociation.user_id == user.id,
        )
        .count()
    )

    assert association == 1


def test_error_link_existing_loyalty_card_bad_user(db_session: "Session", setup_loyalty_card_handler):
    """Tests linking of an existing Loyalty Card produces an error if there is no valid user account found"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(credentials=ADD)

    loyalty_card_handler.user_id = 3

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan)

    loyalty_card_handler.card_id = new_loyalty_card.id

    with pytest.raises(ValidationError):
        loyalty_card_handler.link_account_to_user()


# ----------------COMPLETE ADD JOURNEY------------------


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_new_loyalty_card_add_journey_created_and_linked(
    mock_hermes_msg: "MagicMock", db_session: "Session", setup_loyalty_card_handler
):
    """Tests that user is successfully linked to a newly created Scheme Account"""

    answer_fields = {
        "add_fields": {"credentials": [{"credential_slug": "card_number", "value": "9511143200133540455525"}]},
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=answer_fields
    )

    loyalty_card_handler.handle_add_only_card()

    cards = (
        db_session.query(SchemeAccount)
        .filter(
            SchemeAccount.id == 1,
        )
        .count()
    )

    links = (
        db_session.query(SchemeAccountUserAssociation)
        .filter(
            SchemeAccountUserAssociation.scheme_account_id == 1,
            SchemeAccountUserAssociation.scheme_account_id == user.id,
        )
        .count()
    )

    answers = (
        db_session.query(SchemeAccountCredentialAnswer)
        .filter(
            SchemeAccountCredentialAnswer.scheme_account_id == 1,
        )
        .count()
    )

    assert answers == 1
    assert links == 1
    assert cards == 1
    assert mock_hermes_msg.called is False


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_loyalty_card_add_journey_return_existing(
    mock_hermes_msg: "MagicMock", db_session: "Session", setup_loyalty_card_handler
):
    """Tests that existing loyalty card is returned when there is an existing LoyaltyCard and link to this user"""

    answer_fields = {
        "add_fields": {"credentials": [{"credential_slug": "card_number", "value": "9511143200133540455525"}]},
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=answer_fields
    )

    new_loyalty_card = LoyaltyCardFactory(
        scheme=loyalty_plan, card_number="9511143200133540455525", main_answer="9511143200133540455525"
    )

    db_session.flush()

    association = SchemeAccountUserAssociation(
        scheme_account_id=new_loyalty_card.id, user_id=user.id, auth_provided=False
    )
    db_session.add(association)
    db_session.commit()

    created = loyalty_card_handler.handle_add_only_card()

    assert created is False
    assert loyalty_card_handler.card_id == new_loyalty_card.id
    assert mock_hermes_msg.called is False


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_loyalty_card_add_journey_link_to_existing(
    mock_hermes_msg: "MagicMock", db_session: "Session", setup_loyalty_card_handler
):
    """Tests that user is successfully linked to existing loyalty card when there is an existing LoyaltyCard and
    no link to this user"""

    answer_fields = {
        "add_fields": {"credentials": [{"credential_slug": "card_number", "value": "9511143200133540455525"}]},
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=answer_fields
    )

    new_loyalty_card = LoyaltyCardFactory(
        scheme=loyalty_plan, card_number="9511143200133540455525", main_answer="9511143200133540455525"
    )

    other_user = UserFactory(client=channel.client_application)

    db_session.flush()

    association = SchemeAccountUserAssociation(
        scheme_account_id=new_loyalty_card.id, user_id=other_user.id, auth_provided=False
    )
    db_session.add(association)

    db_session.commit()

    created = loyalty_card_handler.handle_add_only_card()

    links = (
        db_session.query(SchemeAccountUserAssociation)
        .filter(SchemeAccountUserAssociation.scheme_account_id == 1, SchemeAccountUserAssociation.user_id == user.id)
        .count()
    )

    assert links == 1
    assert mock_hermes_msg.called is False
    assert loyalty_card_handler.card_id == new_loyalty_card.id
    assert created is False


# ----------------COMPLETE ADD and AUTH JOURNEY------------------


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_new_loyalty_card_add_and_auth_journey_created_and_linked(
    mock_hermes_msg: "MagicMock", db_session: "Session", setup_loyalty_card_handler
):
    """Tests that user is successfully linked to a newly created Scheme Account"""

    answer_fields = {
        "add_fields": {"credentials": [{"credential_slug": "card_number", "value": "9511143200133540455525"}]},
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, journey=ADD_AND_AUTHORISE
    )

    loyalty_card_handler.handle_add_auth_card()

    cards = (
        db_session.query(SchemeAccount)
        .filter(
            SchemeAccount.id == 1,
        )
        .count()
    )

    links = (
        db_session.query(SchemeAccountUserAssociation)
        .filter(
            SchemeAccountUserAssociation.scheme_account_id == 1,
            SchemeAccountUserAssociation.scheme_account_id == user.id,
        )
        .count()
    )

    answers = (
        db_session.query(SchemeAccountCredentialAnswer)
        .filter(
            SchemeAccountCredentialAnswer.scheme_account_id == 1,
        )
        .count()
    )

    assert answers == 1
    assert links == 1
    assert cards == 1
    assert mock_hermes_msg.called is True
    assert mock_hermes_msg.call_args[0][0] == "loyalty_card_authorise"
    sent_dict = mock_hermes_msg.call_args[0][1]
    assert sent_dict["loyalty_card_id"] == 1
    assert sent_dict["user_id"] == 1
    assert sent_dict["primary_auth"] is True
    assert sent_dict["channel"] == "com.test.channel"


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_loyalty_card_add_and_auth_journey_return_existing(
    mock_hermes_msg: "MagicMock", db_session: "Session", setup_loyalty_card_handler
):
    """Tests that existing loyalty card is returned when there is an existing LoyaltyCard and link to this user"""

    answer_fields = {
        "add_fields": {"credentials": [{"credential_slug": "card_number", "value": "9511143200133540455525"}]},
        "authorise_fields": {
            "credentials": [
                {"credential_slug": "email", "value": "my_email@email.com"},
                {"credential_slug": "password", "value": "iLoveTests33"},
            ]
        },
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, journey=ADD_AND_AUTHORISE
    )

    new_loyalty_card = LoyaltyCardFactory(
        scheme=loyalty_plan, card_number="9511143200133540455525", main_answer="9511143200133540455525"
    )

    db_session.flush()

    association = SchemeAccountUserAssociation(
        scheme_account_id=new_loyalty_card.id, user_id=user.id, auth_provided=False
    )
    db_session.add(association)
    db_session.commit()

    created = loyalty_card_handler.handle_add_auth_card()

    assert created is False
    assert loyalty_card_handler.card_id == new_loyalty_card.id
    assert mock_hermes_msg.called is False


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_loyalty_card_add_and_auth_journey_link_to_existing_wallet_only(
    mock_hermes_msg: "MagicMock", db_session: "Session", setup_loyalty_card_handler
):
    """Tests that user is successfully linked to existing loyalty card when there is an existing LoyaltyCard and
    no link to this user"""

    answer_fields = {
        "add_fields": {"credentials": [{"credential_slug": "card_number", "value": "9511143200133540455525"}]},
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, journey=ADD_AND_AUTHORISE
    )

    new_loyalty_card = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number="9511143200133540455525",
        main_answer="9511143200133540455525",
        status=LoyaltyCardStatus.WALLET_ONLY,
    )

    other_user = UserFactory(client=channel.client_application)

    db_session.flush()

    association = SchemeAccountUserAssociation(
        scheme_account_id=new_loyalty_card.id, user_id=other_user.id, auth_provided=False
    )
    db_session.add(association)

    db_session.commit()

    created = loyalty_card_handler.handle_add_auth_card()

    links = (
        db_session.query(SchemeAccountUserAssociation)
        .filter(SchemeAccountUserAssociation.scheme_account_id == 1, SchemeAccountUserAssociation.user_id == user.id)
        .count()
    )

    assert links == 1
    assert mock_hermes_msg.called is True
    assert loyalty_card_handler.card_id == new_loyalty_card.id
    assert created is True
    assert mock_hermes_msg.call_args[0][0] == "loyalty_card_authorise"
    sent_dict = mock_hermes_msg.call_args[0][1]
    assert sent_dict["loyalty_card_id"] == 1
    assert sent_dict["user_id"] == 1
    assert sent_dict["primary_auth"] is True


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_loyalty_card_add_and_auth_journey_link_to_existing_active(
    mock_hermes_msg: "MagicMock", db_session: "Session", setup_loyalty_card_handler
):
    """Tests that user is successfully linked to existing loyalty card when there is an existing LoyaltyCard and
    no link to this user"""

    answer_fields = {
        "add_fields": {"credentials": [{"credential_slug": "card_number", "value": "9511143200133540455525"}]},
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, journey=ADD_AND_AUTHORISE
    )

    new_loyalty_card = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number="9511143200133540455525",
        main_answer="9511143200133540455525",
        status=LoyaltyCardStatus.ACTIVE,
    )

    other_user = UserFactory(client=channel.client_application)

    db_session.flush()

    association = SchemeAccountUserAssociation(
        scheme_account_id=new_loyalty_card.id, user_id=other_user.id, auth_provided=False
    )
    db_session.add(association)

    db_session.commit()

    created = loyalty_card_handler.handle_add_auth_card()

    links = (
        db_session.query(SchemeAccountUserAssociation)
        .filter(SchemeAccountUserAssociation.scheme_account_id == 1, SchemeAccountUserAssociation.user_id == user.id)
        .count()
    )

    assert links == 1
    assert mock_hermes_msg.called is True
    assert loyalty_card_handler.card_id == new_loyalty_card.id
    assert created is True
    assert loyalty_card_handler.primary_auth is False
    assert mock_hermes_msg.call_args[0][0] == "loyalty_card_authorise"
    sent_dict = mock_hermes_msg.call_args[0][1]
    assert sent_dict["loyalty_card_id"] == 1
    assert sent_dict["user_id"] == 1
    assert sent_dict["primary_auth"] is False


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_loyalty_card_add_and_auth_journey_auth_in_progress(
    mock_hermes_msg: "MagicMock", db_session: "Session", setup_loyalty_card_handler
):
    """Tests that user is successfully linked to existing loyalty card when there is an existing LoyaltyCard and
    no link to this user"""

    answer_fields = {
        "add_fields": {"credentials": [{"credential_slug": "card_number", "value": "9511143200133540455525"}]},
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, journey=LoyaltyCardStatus.PENDING
    )

    new_loyalty_card = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number="9511143200133540455525",
        main_answer="9511143200133540455525",
        status=LoyaltyCardStatus.ACTIVE,
    )

    other_user = UserFactory(client=channel.client_application)

    db_session.flush()

    association = SchemeAccountUserAssociation(
        scheme_account_id=new_loyalty_card.id, user_id=other_user.id, auth_provided=False
    )
    db_session.add(association)

    db_session.commit()

    created = loyalty_card_handler.handle_add_auth_card()

    links = (
        db_session.query(SchemeAccountUserAssociation)
        .filter(SchemeAccountUserAssociation.scheme_account_id == 1, SchemeAccountUserAssociation.user_id == user.id)
        .count()
    )

    assert links == 1
    assert mock_hermes_msg.called is False
    assert loyalty_card_handler.card_id == new_loyalty_card.id
    assert created is False


# ----------------COMPLETE ADD and REGISTER JOURNEY------------------


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_new_loyalty_card_add_and_register_journey_created_and_linked(
    mock_hermes_msg: "MagicMock", db_session: "Session", setup_loyalty_card_handler
):
    """Tests that user is successfully linked to a newly created Scheme Account"""

    answer_fields = {
        "add_fields": {"credentials": [{"credential_slug": "card_number", "value": "9511143200133540455525"}]},
        "register_ghost_card_fields": {
            "credentials": [{"credential_slug": "postcode", "value": "9511143200133540455525"}],
            "consents": [{"consent_slug": "Consent_1", "value": "GU554JG"}],
        },
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, consents=True, journey=ADD_AND_REGISTER
    )

    loyalty_card_handler.handle_add_register_card()

    cards = (
        db_session.query(SchemeAccount)
        .filter(
            SchemeAccount.id == 1,
        )
        .count()
    )

    links = (
        db_session.query(SchemeAccountUserAssociation)
        .filter(
            SchemeAccountUserAssociation.scheme_account_id == 1,
            SchemeAccountUserAssociation.scheme_account_id == user.id,
        )
        .count()
    )

    answers = (
        db_session.query(SchemeAccountCredentialAnswer)
        .filter(
            SchemeAccountCredentialAnswer.scheme_account_id == 1,
        )
        .count()
    )

    assert answers == 1
    assert links == 1
    assert cards == 1
    assert mock_hermes_msg.called is True
    assert mock_hermes_msg.call_args[0][0] == "loyalty_card_register"
    sent_dict = mock_hermes_msg.call_args[0][1]
    assert sent_dict["loyalty_card_id"] == 1
    assert sent_dict["user_id"] == 1
    assert sent_dict["channel"] == "com.test.channel"
    assert sent_dict["register_fields"]


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_loyalty_card_add_and_register_journey_return_existing(
    mock_hermes_msg: "MagicMock", db_session: "Session", setup_loyalty_card_handler
):
    """Tests that user is successfully linked to existing loyalty card when there is an existing LoyaltyCard and
    no link to this user"""

    answer_fields = {
        "add_fields": {"credentials": [{"credential_slug": "card_number", "value": "9511143200133540455525"}]},
        "register_ghost_card_fields": {
            "credentials": [{"credential_slug": "postcode", "value": "9511143200133540455525"}],
            "consents": [{"consent_slug": "Consent_1", "value": "GU554JG"}],
        },
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, consents=True, journey=ADD_AND_REGISTER
    )

    new_loyalty_card = LoyaltyCardFactory(
        scheme=loyalty_plan, card_number="9511143200133540455525", main_answer="9511143200133540455525", status=0
    )

    other_user = UserFactory(client=channel.client_application)

    db_session.flush()

    association = SchemeAccountUserAssociation(
        scheme_account_id=new_loyalty_card.id, user_id=other_user.id, auth_provided=False
    )
    db_session.add(association)

    db_session.commit()

    created = loyalty_card_handler.handle_add_register_card()

    assert mock_hermes_msg.called is False
    assert loyalty_card_handler.card_id == new_loyalty_card.id
    assert created is False


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_delete(mock_hermes_msg: "MagicMock", db_session: "Session", setup_loyalty_card_handler):
    """Tests that a delete card journey is successfully concluded in Angelia"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    new_loyalty_card = LoyaltyCardFactory(
        scheme=loyalty_plan, card_number="9511143200133540455525", main_answer="9511143200133540455525"
    )

    db_session.flush()

    LoyaltyCardUserAssociationFactory(scheme_account_id=new_loyalty_card.id, user_id=user.id, auth_provided=False)

    db_session.commit()

    loyalty_card_handler.card_id = new_loyalty_card.id
    loyalty_card_handler.handle_delete_card()

    assert mock_hermes_msg.called is True
    assert mock_hermes_msg.call_args[0][0] == "delete_loyalty_card"
    sent_dict = mock_hermes_msg.call_args[0][1]
    assert sent_dict["loyalty_card_id"] == 1
    assert sent_dict["user_id"] == 1
    assert sent_dict["channel"] == "com.test.channel"


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_delete_error_join_in_progress(mock_hermes_msg: "MagicMock", db_session: "Session", setup_loyalty_card_handler):
    """Tests that a delete card journey raises an error if the requested scheme_account is async_join_in_progress"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    new_loyalty_card = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number="9511143200133540455525",
        main_answer="9511143200133540455525",
        status=LoyaltyCardStatus.JOIN_ASYNC_IN_PROGRESS,
    )

    db_session.flush()

    LoyaltyCardUserAssociationFactory(scheme_account_id=new_loyalty_card.id, user_id=user.id, auth_provided=False)

    db_session.commit()

    loyalty_card_handler.card_id = new_loyalty_card.id

    with pytest.raises(falcon.HTTPConflict):
        loyalty_card_handler.handle_delete_card()
