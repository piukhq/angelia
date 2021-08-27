import falcon
import pytest
from tests.factories import LoyaltyPlanQuestionFactory, \
    LoyaltyPlanHandlerFactory, \
    LoyaltyPlanFactory, \
    ChannelFactory, \
    UserFactory, \
    DocumentFactory
from app.hermes.models import SchemeChannelAssociation, SchemeCredentialQuestion, SchemeDocument
from app.handlers.loyalty_plan import CredentialClass, DocumentClass
import typing

if typing.TYPE_CHECKING:
    from unittest.mock import MagicMock

    from sqlalchemy.orm import Session


@pytest.fixture(scope="function")
def setup_documents(db_session: "Session"):
    def _setup_documents(loyalty_plan):

        documents = [
            DocumentFactory(scheme=loyalty_plan, display={'ADD', 'ENROL'}),
            DocumentFactory(scheme=loyalty_plan, display={'ENROL', 'REGISTRATION'}),
            DocumentFactory(scheme=loyalty_plan, display={'ENROL', 'AUTHORISE', 'REGISTRATION'}),
            DocumentFactory(scheme=loyalty_plan, display={'VOUCHER'})
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
                scheme_id=loyalty_plan.id, type="card_number", label="Card Number", add_field=True, manual_question=True
            ),
            LoyaltyPlanQuestionFactory(
                scheme_id=loyalty_plan.id, type="barcode", label="Barcode", add_field=True, scan_question=True
            ),
            LoyaltyPlanQuestionFactory(scheme_id=loyalty_plan.id, type="email", label="Email", auth_field=True),
            LoyaltyPlanQuestionFactory(scheme_id=loyalty_plan.id, type="password", label="Password", auth_field=True),
            LoyaltyPlanQuestionFactory(scheme_id=loyalty_plan.id, type="memorable_date", label="Memorable_date",
                                       auth_field=True),
            LoyaltyPlanQuestionFactory(
                scheme_id=loyalty_plan.id, type="postcode", label="Postcode", register_field=True, enrol_field=True
            ),
        ]

        db_session.flush()

        return questions

    return _setup_questions


@pytest.fixture(scope="function")
def setup_loyalty_plan_handler(db_session: "Session", setup_plan_channel_and_user, setup_questions, setup_documents):
    def _setup_loyalty_plan_handler(
        channel_link: bool = True,
        questions: bool = True,
        documents: bool = True,
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

        if loyalty_plan_id is None:
            loyalty_plan_id = loyalty_plan.id

        db_session.commit()

        loyalty_plan_handler = LoyaltyPlanHandlerFactory(
            db_session=db_session,
            user_id=user.id,
            channel_id=channel.bundle_id,
            loyalty_plan_id=loyalty_plan_id,
        )

        return loyalty_plan_handler, loyalty_plan, questions, documents, channel, user

    return _setup_loyalty_plan_handler


def test_fetch_plan(db_session: "Session", setup_loyalty_plan_handler):
    """Tests that plan scheme is successfully fetched"""

    loyalty_plan_handler, loyalty_plan, questions, documents, channel, user = setup_loyalty_plan_handler()

    loyalty_plan_handler.fetch_loyalty_plan_and_information()

    assert loyalty_plan_handler.loyalty_plan


def test_error_fetch_plan(db_session: "Session", setup_loyalty_plan_handler):
    """Tests that 404 occurs if plan is not found"""

    loyalty_plan_handler, loyalty_plan, questions, documents, channel, user = setup_loyalty_plan_handler(loyalty_plan_id=3)

    with pytest.raises(falcon.HTTPNotFound):
        loyalty_plan_handler.fetch_loyalty_plan_and_information()


def test_fetch_and_order_credential_questions(db_session: "Session", setup_loyalty_plan_handler):
    """Tests that creds are successfully found, categorised and ordered"""

    loyalty_plan_handler, loyalty_plan, questions, documents, channel, user = setup_loyalty_plan_handler()

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

    loyalty_plan_handler, loyalty_plan, questions, documents, channel, user = setup_loyalty_plan_handler()

    loyalty_plan_handler.fetch_loyalty_plan_and_information()

    docs = loyalty_plan_handler.documents

    for doc_class in docs.keys():
        for document in docs[doc_class]:
            assert isinstance(document, SchemeDocument)

    assert len(docs[DocumentClass.ADD]) == 1
    assert len(docs[DocumentClass.AUTHORISE]) == 1
    assert len(docs[DocumentClass.ENROL]) == 3
    assert len(docs[DocumentClass.REGISTER]) == 2
