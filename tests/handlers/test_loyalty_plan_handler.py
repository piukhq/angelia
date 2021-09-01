import typing

import falcon
import pytest

from app.handlers.loyalty_plan import CredentialClass, DocumentClass
from app.hermes.models import Consent, SchemeChannelAssociation, SchemeCredentialQuestion, SchemeDocument
from tests.factories import (
    ChannelFactory,
    DocumentFactory,
    LoyaltyPlanFactory,
    LoyaltyPlanHandlerFactory,
    LoyaltyPlanQuestionFactory,
    ThirdPartyConsentLinkFactory,
    UserFactory,
)

if typing.TYPE_CHECKING:
    from sqlalchemy.orm import Session


@pytest.fixture(scope="function")
def setup_consents(db_session: "Session"):
    def _setup_consents(loyalty_plan, channel):

        consents = [
            ThirdPartyConsentLinkFactory(
                scheme=loyalty_plan,
                consent__scheme=loyalty_plan,
                consent__slug="consent_slug_1",
                consent__order=3,
                client_application=channel.client_application,
                add_field=True,
                enrol_field=True,
            ),
            ThirdPartyConsentLinkFactory(
                scheme=loyalty_plan,
                consent__scheme=loyalty_plan,
                consent__slug="consent_slug_2",
                consent__order=1,
                client_application=channel.client_application,
                auth_field=True,
                register_field=True,
            ),
            ThirdPartyConsentLinkFactory(
                scheme=loyalty_plan,
                consent__scheme=loyalty_plan,
                consent__slug="consent_slug_3",
                consent__order=2,
                client_application=channel.client_application,
                enrol_field=True,
                register_field=True,
            ),
            ThirdPartyConsentLinkFactory(
                scheme=loyalty_plan,
                consent__scheme=loyalty_plan,
                consent__slug="consent_slug_4",
                consent__order=0,
                client_application=channel.client_application,
                enrol_field=True,
                register_field=True,
            ),
        ]

        db_session.flush()

        return consents

    return _setup_consents


@pytest.fixture(scope="function")
def setup_documents(db_session: "Session"):
    def _setup_documents(loyalty_plan):

        documents = [
            DocumentFactory(scheme=loyalty_plan, display={"ADD", "ENROL"}),
            DocumentFactory(scheme=loyalty_plan, display={"ENROL", "REGISTRATION"}),
            DocumentFactory(scheme=loyalty_plan, display={"ENROL", "AUTHORISE", "REGISTRATION"}),
            DocumentFactory(scheme=loyalty_plan, display={"VOUCHER"}),
        ]

        db_session.flush()

        return documents

    return _setup_documents


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
                scheme_id=loyalty_plan.id,
                type="card_number",
                label="Card Number",
                add_field=True,
                manual_question=True,
                order=3,
            ),
            LoyaltyPlanQuestionFactory(
                scheme_id=loyalty_plan.id, type="barcode", label="Barcode", add_field=True, scan_question=True, order=1
            ),
            LoyaltyPlanQuestionFactory(
                scheme_id=loyalty_plan.id, type="email", label="Email", auth_field=True, order=6
            ),
            LoyaltyPlanQuestionFactory(
                scheme_id=loyalty_plan.id, type="password", label="Password", auth_field=True, order=9
            ),
            LoyaltyPlanQuestionFactory(
                scheme_id=loyalty_plan.id, type="memorable_date", label="Memorable_date", auth_field=True, order=3
            ),
            LoyaltyPlanQuestionFactory(
                scheme_id=loyalty_plan.id,
                type="postcode",
                label="Postcode",
                register_field=True,
                enrol_field=True,
                order=0,
            ),
        ]

        db_session.flush()

        return questions

    return _setup_questions


@pytest.fixture(scope="function")
def setup_loyalty_plan_handler(
    db_session: "Session", setup_plan_channel_and_user, setup_questions, setup_documents, setup_consents
):
    def _setup_loyalty_plan_handler(
        channel_link: bool = True,
        questions: bool = True,
        documents: bool = True,
        consents: bool = True,
        loyalty_plan_id: int = None,
    ):

        loyalty_plan, channel, user = setup_plan_channel_and_user(channel_link)

        if questions:
            questions = setup_questions(loyalty_plan)
        else:
            questions = []

        if documents:
            documents = setup_documents(loyalty_plan)
        else:
            documents = []

        if consents:
            consents = setup_consents(loyalty_plan, channel)
        else:
            consents = []

        if loyalty_plan_id is None:
            loyalty_plan_id = loyalty_plan.id

        db_session.commit()

        loyalty_plan_handler = LoyaltyPlanHandlerFactory(
            db_session=db_session,
            user_id=user.id,
            channel_id=channel.bundle_id,
            loyalty_plan_id=loyalty_plan_id,
        )

        return loyalty_plan_handler, loyalty_plan, questions, documents, consents, channel, user

    return _setup_loyalty_plan_handler


def test_fetch_plan(db_session: "Session", setup_loyalty_plan_handler):
    """Tests that plan scheme is successfully fetched"""

    loyalty_plan_handler, loyalty_plan, questions, documents, consents, channel, user = setup_loyalty_plan_handler(
        consents=False
    )

    loyalty_plan_handler.fetch_loyalty_plan_and_information()

    assert loyalty_plan_handler.loyalty_plan


def test_error_fetch_plan(db_session: "Session", setup_loyalty_plan_handler):
    """Tests that 404 occurs if plan is not found"""

    loyalty_plan_handler, loyalty_plan, questions, documents, consents, channel, user = setup_loyalty_plan_handler(
        loyalty_plan_id=3, consents=False
    )

    with pytest.raises(falcon.HTTPNotFound):
        loyalty_plan_handler.fetch_loyalty_plan_and_information()


def test_fetch_and_order_credential_questions(db_session: "Session", setup_loyalty_plan_handler):
    """Tests that creds are successfully found, categorised and ordered"""

    loyalty_plan_handler, loyalty_plan, questions, documents, consents, channel, user = setup_loyalty_plan_handler(
        consents=False
    )

    loyalty_plan_handler.fetch_loyalty_plan_and_information()

    creds = loyalty_plan_handler.loyalty_plan_credentials

    for cred_class in creds.keys():
        for i in creds[cred_class]:
            assert isinstance(i, SchemeCredentialQuestion)

    assert len(creds[CredentialClass.ADD_FIELD]) == 2
    assert len(creds[CredentialClass.AUTH_FIELD]) == 3
    assert len(creds[CredentialClass.JOIN_FIELD]) == 1
    assert len(creds[CredentialClass.REGISTER_FIELD]) == 1

    assert creds[CredentialClass.ADD_FIELD][1].order >= creds[CredentialClass.ADD_FIELD][0].order
    assert creds[CredentialClass.AUTH_FIELD][1].order >= creds[CredentialClass.AUTH_FIELD][0].order
    assert creds[CredentialClass.AUTH_FIELD][2].order >= creds[CredentialClass.AUTH_FIELD][1].order


def test_fetch_and_order_documents(db_session: "Session", setup_loyalty_plan_handler):
    """Tests that documents are successfully found and categorised"""

    loyalty_plan_handler, loyalty_plan, questions, documents, consents, channel, user = setup_loyalty_plan_handler(
        consents=False
    )

    loyalty_plan_handler.fetch_loyalty_plan_and_information()

    docs = loyalty_plan_handler.documents

    for doc_class in docs.keys():
        for document in docs[doc_class]:
            assert isinstance(document, SchemeDocument)

    assert len(docs[DocumentClass.ADD]) == 1
    assert len(docs[DocumentClass.AUTHORISE]) == 1
    assert len(docs[DocumentClass.ENROL]) == 3
    assert len(docs[DocumentClass.REGISTER]) == 2


def test_fetch_empty_documents(db_session: "Session", setup_loyalty_plan_handler):
    """Tests that no error occurs when no documents are found"""

    loyalty_plan_handler, loyalty_plan, questions, documents, consents, channel, user = setup_loyalty_plan_handler(
        consents=False, documents=False
    )

    loyalty_plan_handler.fetch_loyalty_plan_and_information()

    assert [loyalty_plan_handler.documents[doc_class] == [] for doc_class in DocumentClass]


def test_fetch_and_order_consents(db_session: "Session", setup_loyalty_plan_handler):
    """Tests that consents are successfully found, ordered and categorised"""

    loyalty_plan_handler, loyalty_plan, questions, documents, consents, channel, user = setup_loyalty_plan_handler()

    loyalty_plan_handler.fetch_consents()

    consents = loyalty_plan_handler.consents

    for cred_class in consents.keys():
        for consent in consents[cred_class]:
            assert isinstance(consent, Consent)

    assert len(consents[CredentialClass.ADD_FIELD]) == 1
    assert len(consents[CredentialClass.AUTH_FIELD]) == 1
    assert len(consents[CredentialClass.JOIN_FIELD]) == 3
    assert len(consents[CredentialClass.REGISTER_FIELD]) == 3

    assert consents[CredentialClass.REGISTER_FIELD][1].order >= consents[CredentialClass.REGISTER_FIELD][0].order
    assert consents[CredentialClass.REGISTER_FIELD][2].order >= consents[CredentialClass.REGISTER_FIELD][1].order
    assert consents[CredentialClass.JOIN_FIELD][1].order >= consents[CredentialClass.REGISTER_FIELD][0].order
    assert consents[CredentialClass.JOIN_FIELD][2].order >= consents[CredentialClass.REGISTER_FIELD][1].order


def test_fetch_empty_consents(db_session: "Session", setup_loyalty_plan_handler):
    """Tests that no error occurs when no consents are found"""

    loyalty_plan_handler, loyalty_plan, questions, documents, consents, channel, user = setup_loyalty_plan_handler(
        consents=False
    )

    loyalty_plan_handler.fetch_consents()

    assert [loyalty_plan_handler.consents[cred_class] == [] for cred_class in CredentialClass]


def test_response(db_session: "Session", setup_loyalty_plan_handler):
    """Tests overall response pattern"""

    loyalty_plan_handler, loyalty_plan, questions, documents, consents, channel, user = setup_loyalty_plan_handler()

    response = loyalty_plan_handler.get_journey_fields()

    assert response == {
        "id": 1,
        "join_fields": {
            "credentials": [
                {
                    "order": 0,
                    "display_label": "Postcode",
                    "validation": "",
                    "description": "",
                    "credential_slug": "postcode",
                    "type": "text",
                    "is_sensitive": False,
                }
            ],
            "plan_documents": [
                {
                    "name": "Test Document",
                    "url": "https://testdocument.com",
                    "description": "This is a test plan document",
                },
                {
                    "name": "Test Document",
                    "url": "https://testdocument.com",
                    "description": "This is a test plan document",
                },
                {
                    "name": "Test Document",
                    "url": "https://testdocument.com",
                    "description": "This is a test plan document",
                },
            ],
            "consents": [
                {
                    "order": 0,
                    "name": "consent_slug_4",
                    "is_acceptance_required": False,
                    "description": "This is some really descriptive text right here",
                },
                {
                    "order": 2,
                    "name": "consent_slug_3",
                    "is_acceptance_required": False,
                    "description": "This is some really descriptive text right here",
                },
                {
                    "order": 3,
                    "name": "consent_slug_1",
                    "is_acceptance_required": False,
                    "description": "This is some really descriptive text right here",
                },
            ],
        },
        "register_ghost_card_fields": {
            "credentials": [
                {
                    "order": 0,
                    "display_label": "Postcode",
                    "validation": "",
                    "description": "",
                    "credential_slug": "postcode",
                    "type": "text",
                    "is_sensitive": False,
                }
            ],
            "plan_documents": [
                {
                    "name": "Test Document",
                    "url": "https://testdocument.com",
                    "description": "This is a test plan document",
                },
                {
                    "name": "Test Document",
                    "url": "https://testdocument.com",
                    "description": "This is a test plan document",
                },
            ],
            "consents": [
                {
                    "order": 0,
                    "name": "consent_slug_4",
                    "is_acceptance_required": False,
                    "description": "This is some really descriptive text right here",
                },
                {
                    "order": 1,
                    "name": "consent_slug_2",
                    "is_acceptance_required": False,
                    "description": "This is some really descriptive text right here",
                },
                {
                    "order": 2,
                    "name": "consent_slug_3",
                    "is_acceptance_required": False,
                    "description": "This is some really descriptive text right here",
                },
            ],
        },
        "add_fields": {
            "credentials": [
                {
                    "order": 1,
                    "display_label": "Barcode",
                    "validation": "",
                    "description": "",
                    "credential_slug": "barcode",
                    "type": "text",
                    "is_sensitive": False,
                },
                {
                    "order": 3,
                    "display_label": "Card Number",
                    "validation": "",
                    "description": "",
                    "credential_slug": "card_number",
                    "type": "text",
                    "is_sensitive": False,
                },
            ],
            "plan_documents": [
                {
                    "name": "Test Document",
                    "url": "https://testdocument.com",
                    "description": "This is a test plan document",
                }
            ],
            "consents": [
                {
                    "order": 3,
                    "name": "consent_slug_1",
                    "is_acceptance_required": False,
                    "description": "This is some really descriptive text right here",
                }
            ],
        },
        "authorise_fields": {
            "credentials": [
                {
                    "order": 3,
                    "display_label": "Memorable_date",
                    "validation": "",
                    "description": "",
                    "credential_slug": "memorable_date",
                    "type": "text",
                    "is_sensitive": False,
                },
                {
                    "order": 6,
                    "display_label": "Email",
                    "validation": "",
                    "description": "",
                    "credential_slug": "email",
                    "type": "text",
                    "is_sensitive": False,
                },
                {
                    "order": 9,
                    "display_label": "Password",
                    "validation": "",
                    "description": "",
                    "credential_slug": "password",
                    "type": "text",
                    "is_sensitive": False,
                },
            ],
            "plan_documents": [
                {
                    "name": "Test Document",
                    "url": "https://testdocument.com",
                    "description": "This is a test plan document",
                }
            ],
            "consents": [
                {
                    "order": 1,
                    "name": "consent_slug_2",
                    "is_acceptance_required": False,
                    "description": "This is some really descriptive text right here",
                }
            ],
        },
    }
