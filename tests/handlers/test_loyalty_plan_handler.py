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


def test_fetch_plan(setup_loyalty_plan_handler):
    """Tests that plan scheme is successfully fetched"""

    loyalty_plan_handler, loyalty_plan, questions, documents, consents, channel, user = setup_loyalty_plan_handler(
        consents=False
    )

    schemes, creds, docs = loyalty_plan_handler.fetch_loyalty_plan_and_information()

    assert all([isinstance(item, SchemeCredentialQuestion) for item in creds])
    assert all([isinstance(item, SchemeDocument) for item in docs])
    unique_schemes = list(set(schemes))
    assert len(unique_schemes) == 1
    assert unique_schemes[0].id == loyalty_plan.id


def test_error_fetch_plan(setup_loyalty_plan_handler):
    """Tests that 404 occurs if plan is not found"""

    loyalty_plan_handler, loyalty_plan, questions, documents, consents, channel, user = setup_loyalty_plan_handler(
        loyalty_plan_id=3, consents=False
    )

    with pytest.raises(falcon.HTTPNotFound):
        loyalty_plan_handler.fetch_loyalty_plan_and_information()


def test_fetch_and_order_credential_questions(setup_loyalty_plan_handler):
    """Tests that creds are successfully found, categorised and ordered"""

    loyalty_plan_handler, loyalty_plan, questions, documents, consents, channel, user = setup_loyalty_plan_handler(
        consents=False
    )

    _, creds, docs = loyalty_plan_handler.fetch_loyalty_plan_and_information()
    creds, _ = loyalty_plan_handler._categorise_creds_and_docs(creds, docs)

    for cred_class in creds.keys():
        for i in creds[cred_class]:
            assert isinstance(i, SchemeCredentialQuestion)

    # Should return 1 ADD question not both due to scan/manual question subordination
    assert len(creds[CredentialClass.ADD_FIELD]) == 1
    assert len(creds[CredentialClass.AUTH_FIELD]) == 3
    assert len(creds[CredentialClass.JOIN_FIELD]) == 1
    assert len(creds[CredentialClass.REGISTER_FIELD]) == 1

    assert creds[CredentialClass.AUTH_FIELD][1].order >= creds[CredentialClass.AUTH_FIELD][0].order
    assert creds[CredentialClass.AUTH_FIELD][2].order >= creds[CredentialClass.AUTH_FIELD][1].order


def test_fetch_and_order_documents(setup_loyalty_plan_handler):
    """Tests that documents are successfully found and categorised"""

    loyalty_plan_handler, loyalty_plan, questions, documents, consents, channel, user = setup_loyalty_plan_handler(
        consents=False
    )

    _, creds, docs = loyalty_plan_handler.fetch_loyalty_plan_and_information()
    _, docs = loyalty_plan_handler._categorise_creds_and_docs(creds, docs)
    for doc_class in docs.keys():
        for document in docs[doc_class]:
            assert isinstance(document, SchemeDocument)

    assert len(docs[DocumentClass.ADD]) == 1
    assert len(docs[DocumentClass.AUTHORISE]) == 1
    assert len(docs[DocumentClass.ENROL]) == 3
    assert len(docs[DocumentClass.REGISTER]) == 2


def test_fetch_empty_documents(setup_loyalty_plan_handler):
    """Tests that no error occurs when no documents are found"""

    loyalty_plan_handler, loyalty_plan, questions, documents, consents, channel, user = setup_loyalty_plan_handler(
        consents=False, documents=False
    )

    _, creds, docs = loyalty_plan_handler.fetch_loyalty_plan_and_information()
    _, docs = loyalty_plan_handler._categorise_creds_and_docs(creds, docs)

    assert [docs[doc_class] == [] for doc_class in DocumentClass]


def test_fetch_and_order_consents(setup_loyalty_plan_handler):
    """Tests that consents are successfully found, ordered and categorised"""

    loyalty_plan_handler, loyalty_plan, questions, documents, consents, channel, user = setup_loyalty_plan_handler()

    consents = loyalty_plan_handler.fetch_consents()
    loyalty_plan_handler._categorise_consents(consents)

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


def test_fetch_empty_consents(setup_loyalty_plan_handler):
    """Tests that no error occurs when no consents are found"""

    loyalty_plan_handler, loyalty_plan, questions, documents, consents, channel, user = setup_loyalty_plan_handler(
        consents=False
    )

    consents = loyalty_plan_handler.fetch_consents()
    loyalty_plan_handler._categorise_consents(consents)

    assert [loyalty_plan_handler.consents[cred_class] == [] for cred_class in CredentialClass]
