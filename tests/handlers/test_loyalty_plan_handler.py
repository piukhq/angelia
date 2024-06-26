import datetime
import os
import random
import typing
from unittest.mock import MagicMock, patch

import falcon
import pytest
from faker import Faker
from sqlalchemy import select
from sqlalchemy.engine import Row

from angelia.api.exceptions import ResourceNotFoundError
from angelia.handlers.loyalty_plan import (
    CredentialClass,
    CredentialField,
    DocumentClass,
    LoyaltyPlanChannelStatus,
    LoyaltyPlanHandler,
    LoyaltyPlanJourney,
    LoyaltyPlansHandler,
)
from angelia.hermes.models import (
    Channel,
    Consent,
    Scheme,
    SchemeAccount,
    SchemeAccountUserAssociation,
    SchemeContent,
    SchemeCredentialQuestion,
    SchemeDetail,
    SchemeDocument,
    SchemeImage,
    ThirdPartyConsentLink,
    User,
)
from angelia.lib.images import ImageStatus, ImageTypes
from angelia.settings import settings
from tests.factories import (
    DocumentFactory,
    LoyaltyCardFactory,
    LoyaltyCardUserAssociationFactory,
    LoyaltyPlanHandlerFactory,
    LoyaltyPlanQuestionFactory,
    LoyaltyPlansHandlerFactory,
    SchemeContentFactory,
    SchemeDetailFactory,
    SchemeImageFactory,
    ThirdPartyConsentLinkFactory,
)

if typing.TYPE_CHECKING:
    from sqlalchemy.orm import Session


fake = Faker()


class PlanInfo(typing.NamedTuple):
    plan: Scheme
    questions: list[SchemeCredentialQuestion]
    documents: list[SchemeDocument]
    consents: list["ThirdPartyConsentLink"]
    images: list["SchemeImage"]
    details: list["SchemeDetail"]
    contents: list["SchemeContent"]


@pytest.fixture(scope="function")
def journey_fields() -> dict:
    return {
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
                    "order": 8,
                    "name": "Test Document",
                    "url": "https://testdocument.com",
                    "description": "This is a test plan document",
                    "is_acceptance_required": True,
                },
                {
                    "order": 10,
                    "name": "Test Document",
                    "url": "https://testdocument.com",
                    "description": "This is a test plan document",
                    "is_acceptance_required": True,
                },
                {
                    "order": 19,
                    "name": "Test Document",
                    "url": "https://testdocument.com",
                    "description": "This is a test plan document",
                    "is_acceptance_required": True,
                },
            ],
            "consents": [
                {
                    "order": 3,
                    "consent_slug": "consent_slug_1",
                    "is_acceptance_required": False,
                    "description": "This is some really descriptive text right here",
                },
                {
                    "order": 2,
                    "consent_slug": "consent_slug_3",
                    "is_acceptance_required": False,
                    "description": "This is some really descriptive text right here",
                },
                {
                    "order": 0,
                    "consent_slug": "consent_slug_4",
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
                    "order": 8,
                    "name": "Test Document",
                    "url": "https://testdocument.com",
                    "description": "This is a test plan document",
                    "is_acceptance_required": True,
                },
                {
                    "order": 19,
                    "name": "Test Document",
                    "url": "https://testdocument.com",
                    "description": "This is a test plan document",
                    "is_acceptance_required": True,
                },
            ],
            "consents": [
                {
                    "order": 1,
                    "consent_slug": "consent_slug_2",
                    "is_acceptance_required": False,
                    "description": "This is some really descriptive text right here",
                },
                {
                    "order": 2,
                    "consent_slug": "consent_slug_3",
                    "is_acceptance_required": False,
                    "description": "This is some really descriptive text right here",
                },
                {
                    "order": 0,
                    "consent_slug": "consent_slug_4",
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
                    "alternative": {
                        "order": 1,
                        "display_label": "Card Number",
                        "validation": "",
                        "description": "",
                        "credential_slug": "card_number",
                        "type": "text",
                        "is_sensitive": False,
                    },
                }
            ],
            "plan_documents": [
                {
                    "order": 10,
                    "name": "Test Document",
                    "url": "https://testdocument.com",
                    "description": "This is a test plan document",
                    "is_acceptance_required": True,
                }
            ],
            "consents": [
                {
                    "order": 3,
                    "consent_slug": "consent_slug_1",
                    "is_acceptance_required": False,
                    "description": "This is some really descriptive text right here",
                }
            ],
        },
        "authorise_fields": {
            "credentials": [
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
                {
                    "order": 3,
                    "display_label": "Memorable_date",
                    "validation": "",
                    "description": "",
                    "credential_slug": "memorable_date",
                    "type": "text",
                    "is_sensitive": False,
                },
            ],
            "plan_documents": [
                {
                    "order": 19,
                    "name": "Test Document",
                    "url": "https://testdocument.com",
                    "description": "This is a test plan document",
                    "is_acceptance_required": True,
                }
            ],
            "consents": [
                {
                    "order": 1,
                    "consent_slug": "consent_slug_2",
                    "is_acceptance_required": False,
                    "description": "This is some really descriptive text right here",
                }
            ],
        },
    }


@pytest.fixture(scope="function")
def setup_consents(db_session: "Session") -> typing.Callable[[Scheme, Channel], list[ThirdPartyConsentLink]]:
    def _setup_consents(loyalty_plan: Scheme, channel: Channel) -> list[ThirdPartyConsentLink]:
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
def setup_documents(db_session: "Session") -> typing.Callable[[Scheme], list[SchemeDocument]]:
    def _setup_documents(loyalty_plan: Scheme) -> list[SchemeDocument]:
        documents = [
            DocumentFactory(scheme=loyalty_plan, display={"ADD", "ENROL"}, order=fake.random_int(min=0, max=20)),
            DocumentFactory(
                scheme=loyalty_plan, display={"ENROL", "REGISTRATION"}, order=fake.random_int(min=0, max=20)
            ),
            DocumentFactory(
                scheme=loyalty_plan,
                display={"ENROL", "AUTHORISE", "REGISTRATION"},
                order=fake.random_int(min=0, max=20),
            ),
            DocumentFactory(scheme=loyalty_plan, display={"VOUCHER"}, order=fake.random_int(min=0, max=20)),
        ]

        db_session.flush()

        return documents

    return _setup_documents


@pytest.fixture(scope="function")
def setup_images(db_session: "Session") -> typing.Callable[[Scheme], list[SchemeImage]]:
    def _setup_images(loyalty_plan: Scheme) -> list[SchemeImage]:
        images = [SchemeImageFactory(scheme=loyalty_plan, url=f"some/image{index}.jpg") for index in range(3)]

        db_session.flush()
        return images

    return _setup_images


@pytest.fixture(scope="function")
def setup_details(db_session: "Session") -> typing.Callable[[Scheme], list[SchemeDetail]]:
    def _setup_details(loyalty_plan: Scheme) -> list[SchemeDetail]:
        details = [SchemeDetailFactory(scheme=loyalty_plan, name=fake.word()) for _ in range(3)]

        db_session.flush()
        return details

    return _setup_details


@pytest.fixture(scope="function")
def setup_contents(db_session: "Session") -> typing.Callable[[Scheme], list[SchemeContent]]:
    def _setup_contents(loyalty_plan: Scheme) -> list[SchemeContent]:
        contents = [SchemeContentFactory(scheme=loyalty_plan, column=fake.word()) for _ in range(3)]

        db_session.flush()
        return contents

    return _setup_contents


@pytest.fixture(scope="function")
def setup_questions(
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
) -> typing.Callable[[Scheme], list[SchemeCredentialQuestion]]:
    def _setup_questions(loyalty_plan: Scheme) -> list[SchemeCredentialQuestion]:
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
def setup_loyalty_plan(
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
    setup_documents: typing.Callable[[Scheme], list[SchemeDocument]],
    setup_consents: typing.Callable[[dict, Channel], list[ThirdPartyConsentLink]],
    setup_images: typing.Callable[[Scheme], list[SchemeImage]],
    setup_details: typing.Callable[[Scheme], list[SchemeDetail]],
    setup_contents: typing.Callable[[Scheme], list[SchemeContent]],
) -> typing.Callable[[Channel | None, bool, bool, bool, bool, bool, bool, bool], tuple[User, Channel, PlanInfo]]:
    def _setup_loyalty_plan(
        channel: Channel | None = None,
        channel_link: bool = True,
        questions: bool = True,
        documents: bool = True,
        consents: bool = True,
        details: bool = True,
        contents: bool = True,
        images: bool = True,
    ) -> tuple[User, Channel, PlanInfo]:
        loyalty_plan, channel, user = setup_plan_channel_and_user(
            slug=fake.slug(), channel=channel, channel_link=channel_link
        )

        questions_list = setup_questions(loyalty_plan) if questions else []
        documents_list = setup_documents(loyalty_plan) if documents else []
        consents_list = setup_consents(loyalty_plan, channel) if consents else []
        images_list = setup_images(loyalty_plan) if images else []
        details_list = setup_details(loyalty_plan) if details else []
        contents_list = setup_contents(loyalty_plan) if contents else []

        db_session.commit()

        return (
            user,
            channel,
            PlanInfo(
                plan=loyalty_plan,
                questions=questions_list,
                documents=documents_list,
                consents=consents_list,
                images=images_list,
                details=details_list,
                contents=contents_list,
            ),
        )

    return _setup_loyalty_plan


@pytest.fixture(scope="function")
def setup_loyalty_plan_handler(
    db_session: "Session",
    setup_loyalty_plan: typing.Callable[..., tuple[User, Channel, PlanInfo]],
) -> typing.Callable[
    [bool, bool, bool, bool, bool, bool, bool, int | None], tuple[LoyaltyPlanHandler, User, Channel, PlanInfo]
]:
    def _setup_loyalty_plan_handler(
        channel_link: bool = True,
        questions: bool = True,
        documents: bool = True,
        consents: bool = True,
        images: bool = True,
        details: bool = True,
        contents: bool = True,
        loyalty_plan_id: int | None = None,
    ) -> tuple[LoyaltyPlanHandler, User, Channel, PlanInfo]:
        user, channel, plan_info = setup_loyalty_plan(
            channel_link=channel_link,
            questions=questions,
            documents=documents,
            consents=consents,
            images=images,
            details=details,
            contents=contents,
        )

        if loyalty_plan_id is None:
            loyalty_plan_id = plan_info.plan.id

        loyalty_plan_handler = LoyaltyPlanHandlerFactory(
            db_session=db_session,
            user_id=user.id,
            channel_id=channel.bundle_id,
            loyalty_plan_id=loyalty_plan_id,
        )

        return loyalty_plan_handler, user, channel, plan_info

    return _setup_loyalty_plan_handler


@pytest.fixture(scope="function")
def setup_loyalty_plans_handler(
    db_session: "Session",
    setup_loyalty_plan: typing.Callable[..., tuple[User, Channel, PlanInfo]],
) -> typing.Callable[
    [bool, bool, bool, bool, bool, bool, bool, int], tuple[LoyaltyPlansHandler, User, Channel, list[PlanInfo]]
]:
    def _setup_loyalty_plans_handler(
        channel_link: bool = True,
        questions_setup: bool = True,
        documents_setup: bool = True,
        consents_setup: bool = True,
        images_setup: bool = True,
        details_setup: bool = True,
        contents_setup: bool = True,
        plan_count: int = 1,
    ) -> tuple[LoyaltyPlansHandler, User, Channel, list[PlanInfo]]:
        all_plan_info = []
        user: User | None = None
        channel: Channel | None = None
        for _ in range(plan_count):
            user, channel, plan_info = setup_loyalty_plan(
                channel=channel,
                channel_link=channel_link,
                questions=questions_setup,
                documents=documents_setup,
                consents=consents_setup,
                images=images_setup,
                details=details_setup,
                contents=contents_setup,
            )
            all_plan_info.append(plan_info)

        if not (user and channel):
            raise ValueError("user and channel needed")

        loyalty_plans_handler = LoyaltyPlansHandlerFactory(
            db_session=db_session,
            user_id=user.id,
            channel_id=channel.bundle_id,
            is_tester=False,
        )

        return loyalty_plans_handler, user, channel, all_plan_info

    return _setup_loyalty_plans_handler


# ##################### LoyaltyPlanHandler tests ######################


def test_fetch_plan(
    setup_loyalty_plan_handler: typing.Callable[..., tuple[LoyaltyPlanHandler, User, Channel, PlanInfo]],
) -> None:
    """Tests that plan scheme is successfully fetched"""

    loyalty_plan_handler, user, channel, plan_info = setup_loyalty_plan_handler(consents=False)

    scheme, creds, docs = loyalty_plan_handler._fetch_loyalty_plan_and_information()

    assert all(isinstance(item, SchemeCredentialQuestion) for item in creds)
    assert all(isinstance(item, SchemeDocument) for item in docs)
    assert scheme.id == plan_info.plan.id


def test_error_fetch_plan(
    setup_loyalty_plan_handler: typing.Callable[..., tuple[LoyaltyPlanHandler, User, Channel, PlanInfo]],
) -> None:
    """Tests that 404 occurs if plan is not found"""

    loyalty_plan_handler, user, channel, plan_info = setup_loyalty_plan_handler(loyalty_plan_id=3, consents=False)

    with pytest.raises(falcon.HTTPNotFound):
        loyalty_plan_handler._fetch_loyalty_plan_and_information()


@pytest.mark.parametrize("is_test_plan", [True, False])
@pytest.mark.parametrize("is_tester", [True, False])
def test_fetch_plan_test_flight(
    db_session: "Session",
    setup_loyalty_plan_handler: typing.Callable[..., tuple[LoyaltyPlanHandler, User, Channel, PlanInfo]],
    is_tester: bool,
    is_test_plan: bool,
) -> None:
    """Tests that plan scheme is successfully fetched"""

    loyalty_plan_handler, user, channel, plan_info = setup_loyalty_plan_handler(consents=False)
    loyalty_plan_handler.is_tester = is_tester

    if is_test_plan:
        plan_info.plan.channel_associations[0].test_scheme = True
        db_session.flush()

    if is_test_plan and not is_tester:
        with pytest.raises(ResourceNotFoundError):
            loyalty_plan_handler._fetch_loyalty_plan_and_information()
    else:
        scheme, creds, docs = loyalty_plan_handler._fetch_loyalty_plan_and_information()

        assert all(isinstance(item, SchemeCredentialQuestion) for item in creds)
        assert all(isinstance(item, SchemeDocument) for item in docs)
        assert scheme.id == plan_info.plan.id


def test_fetch_and_order_credential_questions(
    setup_loyalty_plan_handler: typing.Callable[..., tuple[LoyaltyPlanHandler, User, Channel, PlanInfo]],
) -> None:
    """Tests that creds are successfully found, categorised and ordered"""

    loyalty_plan_handler, user, channel, plan_info = setup_loyalty_plan_handler(consents=False)

    _, creds_list, docs_list = loyalty_plan_handler._fetch_loyalty_plan_and_information()
    creds, _ = loyalty_plan_handler._categorise_creds_and_docs(creds_list, docs_list)

    for cred_class in creds:
        for i in creds[cred_class]:
            assert isinstance(i, SchemeCredentialQuestion)

    # Should return 1 ADD question not both due to scan/manual question subordination
    assert len(creds[CredentialClass.ADD_FIELD]) == 1
    assert len(creds[CredentialClass.AUTH_FIELD]) == 3
    assert len(creds[CredentialClass.JOIN_FIELD]) == 1
    assert len(creds[CredentialClass.REGISTER_FIELD]) == 1

    assert creds[CredentialClass.AUTH_FIELD][1].order >= creds[CredentialClass.AUTH_FIELD][0].order
    assert creds[CredentialClass.AUTH_FIELD][2].order >= creds[CredentialClass.AUTH_FIELD][1].order


def test_fetch_and_order_documents(
    setup_loyalty_plan_handler: typing.Callable[..., tuple[LoyaltyPlanHandler, User, Channel, PlanInfo]],
) -> None:
    """Tests that documents are successfully found and categorised"""

    loyalty_plan_handler, user, channel, plan_info = setup_loyalty_plan_handler(consents=False)

    _, creds_list, docs_list = loyalty_plan_handler._fetch_loyalty_plan_and_information()
    _, docs = loyalty_plan_handler._categorise_creds_and_docs(creds_list, docs_list)
    for doc_class in docs:
        for document in docs[doc_class]:
            assert isinstance(document, SchemeDocument)

        doc_order = [doc.order for doc in docs[doc_class]]
        assert sorted(doc_order) == doc_order

    assert len(docs[DocumentClass.ADD]) == 1
    assert len(docs[DocumentClass.AUTHORISE]) == 1
    assert len(docs[DocumentClass.ENROL]) == 3
    assert len(docs[DocumentClass.REGISTER]) == 2


def test_fetch_empty_documents(
    setup_loyalty_plan_handler: typing.Callable[..., tuple[LoyaltyPlanHandler, User, Channel, PlanInfo]],
) -> None:
    """Tests that no error occurs when no documents are found"""

    loyalty_plan_handler, user, channel, plan_info = setup_loyalty_plan_handler(consents=False, documents=False)

    _, creds_list, docs_list = loyalty_plan_handler._fetch_loyalty_plan_and_information()
    _, docs = loyalty_plan_handler._categorise_creds_and_docs(creds_list, docs_list)

    assert [docs[doc_class] == [] for doc_class in DocumentClass]


def test_fetch_and_order_consents(
    setup_loyalty_plan_handler: typing.Callable[..., tuple[LoyaltyPlanHandler, User, Channel, PlanInfo]],
) -> None:
    """Tests that consents are successfully found, ordered and categorised"""

    loyalty_plan_handler, user, channel, plan_info = setup_loyalty_plan_handler()

    consent_and_third_party = loyalty_plan_handler._fetch_consents()
    loyalty_plan_handler._categorise_consents(consent_and_third_party)

    consents = loyalty_plan_handler.consents

    for cred_class in consents:
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


def test_fetch_empty_consents(
    setup_loyalty_plan_handler: typing.Callable[..., tuple[LoyaltyPlanHandler, User, Channel, PlanInfo]],
) -> None:
    """Tests that no error occurs when no consents are found"""

    loyalty_plan_handler, user, channel, plan_info = setup_loyalty_plan_handler(consents=False)

    consents = loyalty_plan_handler._fetch_consents()
    loyalty_plan_handler._categorise_consents(consents)

    assert [loyalty_plan_handler.consents[cred_class] == [] for cred_class in CredentialClass]


def test_get_plan(
    setup_loyalty_plan_handler: typing.Callable[..., tuple[LoyaltyPlanHandler, User, Channel, PlanInfo]],
) -> None:
    loyalty_plan_handler, user, channel, plan_info = setup_loyalty_plan_handler()

    plan = loyalty_plan_handler.get_plan()

    for journey_field in plan["journey_fields"].values():
        cred_order = [credential["order"] for credential in journey_field["credentials"]]
        doc_order = [doc["order"] for doc in journey_field["plan_documents"]]
        consent_order = [consent["order"] for consent in journey_field["consents"]]

        assert sorted(cred_order) == cred_order
        assert sorted(doc_order) == doc_order
        assert sorted(consent_order) == consent_order


def test_get_plan_raises_404_for_no_plan(
    setup_loyalty_plan_handler: typing.Callable[..., tuple[LoyaltyPlanHandler, User, Channel, PlanInfo]],
) -> None:
    loyalty_plan_handler, user, channel, plan_info = setup_loyalty_plan_handler()

    with pytest.raises(falcon.HTTPNotFound):
        loyalty_plan_handler.loyalty_plan_id = 2345678765
        loyalty_plan_handler.get_plan()


def test_get_plan_details(
    setup_loyalty_plan_handler: typing.Callable[..., tuple[LoyaltyPlanHandler, User, Channel, PlanInfo]],
) -> None:
    loyalty_plan_handler, user, channel, plan_info = setup_loyalty_plan_handler()
    plan = loyalty_plan_handler.get_plan_details()

    expected_keys = [
        "company_name",
        "plan_name",
        "plan_label",
        "plan_url",
        "plan_summary",
        "plan_description",
        "redeem_instructions",
        "plan_register_info",
        "join_incentive",
        "colour",
        "text_colour",
        "category",
        "tiers",
        "images",
    ]

    for key in expected_keys:
        assert key in plan


@pytest.mark.parametrize("is_test_plan", [True, False])
@pytest.mark.parametrize("is_tester", [True, False])
def test_get_plan_details_test_flight(
    db_session: "Session",
    setup_loyalty_plan_handler: typing.Callable[..., tuple[LoyaltyPlanHandler, User, Channel, PlanInfo]],
    is_tester: bool,
    is_test_plan: bool,
) -> None:
    loyalty_plan_handler, user, channel, plan_info = setup_loyalty_plan_handler()
    loyalty_plan_handler.is_tester = is_tester

    if is_test_plan:
        plan_info.plan.channel_associations[0].test_scheme = True
        db_session.flush()

    if is_test_plan and not is_tester:
        with pytest.raises(ResourceNotFoundError):
            loyalty_plan_handler.get_plan_details()

    else:
        plan = loyalty_plan_handler.get_plan_details()

        expected_keys = [
            "company_name",
            "plan_name",
            "plan_label",
            "plan_url",
            "plan_summary",
            "plan_description",
            "redeem_instructions",
            "plan_register_info",
            "join_incentive",
            "colour",
            "text_colour",
            "category",
            "tiers",
            "images",
        ]

        for key in expected_keys:
            assert key in plan


def test_get_plan_details_filters_suspended_inactive(
    db_session: "Session",
    setup_loyalty_plan_handler: typing.Callable[..., tuple[LoyaltyPlanHandler, User, Channel, PlanInfo]],
) -> None:
    loyalty_plan_handler, user, channel, plan_info = setup_loyalty_plan_handler()

    # Test active scheme is found and does not raise an error
    channel.scheme_associations[0].status = LoyaltyPlanChannelStatus.ACTIVE.value
    db_session.flush()

    loyalty_plan_handler.get_plan_details()

    channel.scheme_associations[0].status = LoyaltyPlanChannelStatus.INACTIVE.value
    db_session.flush()

    with pytest.raises(ResourceNotFoundError):
        loyalty_plan_handler.get_plan_details()

    channel.scheme_associations[0].status = LoyaltyPlanChannelStatus.SUSPENDED.value
    db_session.flush()

    with pytest.raises(ResourceNotFoundError):
        loyalty_plan_handler.get_plan_details()


def fetch_plan_info(
    schemes_and_questions: list[Row[Scheme, SchemeCredentialQuestion]],
    scheme_info: list[Row[SchemeDocument, SchemeImage, ThirdPartyConsentLink, SchemeDetail, SchemeContent]],
    consents: list[Consent],
) -> tuple[
    set[Scheme],
    set[SchemeCredentialQuestion],
    set[SchemeDocument],
    set[SchemeImage],
    set[SchemeDetail],
    set[SchemeContent],
    set[Consent],
]:
    plans: set[Scheme] = set()
    creds: set[SchemeCredentialQuestion] = set()
    docs: set[SchemeDocument] = set()
    images: set[SchemeImage] = set()
    details: set[SchemeDetail] = set()
    contents: set[SchemeContent] = set()
    tp_consent_links: set[Consent] = set(consents)

    for plan_info in schemes_and_questions:
        for index, info_type in enumerate([plans, creds]):  # type: ignore [list-item]
            if plan_info[index] is not None:
                info_type.add(plan_info[index])

    for plan_info in scheme_info:
        for index, info_type in enumerate([plans, docs, images, details, contents]):  # type: ignore [assignment]
            # Skip the plan ids as the plan objects have been populated already
            if index == 0:
                continue

            if plan_info[index] is not None:
                info_type.add(plan_info[index])

    return plans, creds, docs, images, details, contents, tp_consent_links


def test_fetch_plan_information(
    setup_loyalty_plan_handler: typing.Callable[..., tuple[LoyaltyPlanHandler, User, Channel, list[PlanInfo]]],
) -> None:
    loyalty_plan_handler, *_ = setup_loyalty_plan_handler()
    schemes_and_questions, scheme_info, consents, plan_ids_in_wallet = loyalty_plan_handler._fetch_plan_information()
    plans, creds, docs, images, details, contents, tp_consent_links = fetch_plan_info(
        schemes_and_questions, scheme_info, consents
    )

    assert len(plans) == 1
    assert len(creds) == 6
    assert len(docs) == 4
    assert len(images) == 3
    assert len(tp_consent_links) == 4
    assert len(details) == 3
    assert len(contents) == 3
    assert not plan_ids_in_wallet


def test_fetch_plan_information_filters_suspended_inactive(
    db_session: "Session",
    setup_loyalty_plan_handler: typing.Callable[..., tuple[LoyaltyPlanHandler, User, Channel, PlanInfo]],
) -> None:
    loyalty_plan_handler, _, channel, *_ = setup_loyalty_plan_handler()

    # Test active scheme is found and does not raise an error
    channel.scheme_associations[0].status = LoyaltyPlanChannelStatus.ACTIVE.value
    db_session.flush()
    loyalty_plan_handler._fetch_plan_information()

    channel.scheme_associations[0].status = LoyaltyPlanChannelStatus.INACTIVE.value
    db_session.flush()

    with pytest.raises(ResourceNotFoundError):
        loyalty_plan_handler._fetch_plan_information()

    channel.scheme_associations[0].status = LoyaltyPlanChannelStatus.SUSPENDED.value
    db_session.flush()

    loyalty_plan_handler._fetch_plan_information()


IMG_KWARGS = [
    ({"url": "some/image-extra.jpg"}, 1),
    ({"url": "some/image-draft.jpg", "status": ImageStatus.DRAFT}, 0),
    ({"url": "some/image-expired.jpg", "end_date": datetime.datetime.now() + datetime.timedelta(minutes=-15)}, 0),
    ({"url": "some/image-not-started.jpg", "start_date": datetime.datetime.now() + datetime.timedelta(minutes=15)}, 0),
]


@pytest.mark.parametrize("image_kwargs", IMG_KWARGS)
def test_plan_image_logic(
    db_session: "Session",
    setup_loyalty_plan_handler: typing.Callable[..., tuple[LoyaltyPlanHandler, User, Channel, PlanInfo]],
    image_kwargs: tuple,
) -> None:
    loyalty_plan_handler, *_, all_plan_info = setup_loyalty_plan_handler()

    SchemeImageFactory(scheme=all_plan_info.plan, **image_kwargs[0])
    db_session.flush()

    schemes_and_questions, scheme_info, consents, _ = loyalty_plan_handler._fetch_plan_information()
    _, _, _, images, *_ = fetch_plan_info(schemes_and_questions, scheme_info, consents)

    assert len(images) == 3 + image_kwargs[1]


# ##################### LoyaltyPlansHandler tests ######################


def setup_existing_loyalty_card(db_session: "Session", plan: Scheme, user: "User") -> None:
    plan_in_wallet = plan
    loyalty_card = LoyaltyCardFactory(scheme=plan_in_wallet)
    db_session.flush()
    LoyaltyCardUserAssociationFactory(scheme_account_id=loyalty_card.id, user_id=user.id)
    db_session.flush()


def test_fetch_all_plan_information(
    db_session: "Session",
    setup_loyalty_plans_handler: typing.Callable[..., tuple[LoyaltyPlansHandler, User, Channel, list[PlanInfo]]],
) -> None:
    plan_count = 3
    loyalty_plans_handler, user, channel, all_plan_info = setup_loyalty_plans_handler(plan_count=plan_count)

    plan_in_wallet = all_plan_info[0].plan
    setup_existing_loyalty_card(db_session, plan_in_wallet, user)

    (
        schemes_and_questions,
        scheme_info,
        consents,
        plan_ids_in_wallet,
        _,
    ) = loyalty_plans_handler._fetch_all_plan_information()

    plans, creds, docs, images, details, contents, tp_consent_links = fetch_plan_info(
        schemes_and_questions, scheme_info, consents
    )

    assert len(plans) == plan_count
    assert len(creds) == plan_count * 6
    assert len(docs) == plan_count * 4
    assert len(images) == plan_count * 3
    assert len(tp_consent_links) == plan_count * 4
    assert len(details) == plan_count * 3
    assert len(contents) == plan_count * 3
    assert len(plan_ids_in_wallet) == 1
    assert plan_ids_in_wallet[0][0] == plan_in_wallet.id


def test_fetch_all_plan_information_filters_suspended_inactive(
    db_session: "Session",
    setup_loyalty_plans_handler: typing.Callable[..., tuple[LoyaltyPlansHandler, User, Channel, list[PlanInfo]]],
) -> None:
    plan_count = 3
    active_plan_count = 1
    loyalty_plans_handler, user, channel, all_plan_info = setup_loyalty_plans_handler(plan_count=plan_count)

    channel.scheme_associations[0].status = LoyaltyPlanChannelStatus.INACTIVE.value
    channel.scheme_associations[1].status = LoyaltyPlanChannelStatus.SUSPENDED.value
    db_session.flush()

    (
        schemes_and_questions,
        scheme_info,
        consents,
        plan_ids_in_wallet,
        _,
    ) = loyalty_plans_handler._fetch_all_plan_information()

    plans, creds, docs, images, details, contents, tp_consent_links = fetch_plan_info(
        schemes_and_questions, scheme_info, consents
    )

    assert len(plans) == active_plan_count
    assert len(creds) == active_plan_count * 6
    assert len(docs) == active_plan_count * 4
    assert len(images) == active_plan_count * 3
    assert len(tp_consent_links) == active_plan_count * 4
    assert len(details) == active_plan_count * 3
    assert len(contents) == active_plan_count * 3

    for association in channel.scheme_associations:
        if association.id == next(iter(plans)).id:
            assert association.status == LoyaltyPlanChannelStatus.ACTIVE


@pytest.mark.parametrize("has_test_plans", [True, False])
@pytest.mark.parametrize("is_tester", [True, False])
def test_fetch_all_plan_information_test_flight(
    db_session: "Session",
    setup_loyalty_plans_handler: typing.Callable[..., tuple[LoyaltyPlansHandler, User, Channel, list[PlanInfo]]],
    is_tester: bool,
    has_test_plans: bool,
) -> None:
    plan_count = 3
    loyalty_plans_handler, user, channel, all_plan_info = setup_loyalty_plans_handler(plan_count=plan_count)
    loyalty_plans_handler.is_tester = is_tester

    if has_test_plans:
        for plan_info in all_plan_info[0:2]:
            # only one association is created during setup, so we can use the first item
            plan_info.plan.channel_associations[0].test_scheme = True

        db_session.flush()

    plan_in_wallet = all_plan_info[0].plan
    setup_existing_loyalty_card(db_session, plan_in_wallet, user)

    (
        schemes_and_questions,
        scheme_info,
        consents,
        plan_ids_in_wallet,
        _,
    ) = loyalty_plans_handler._fetch_all_plan_information()

    plans, creds, docs, images, details, contents, tp_consent_links = fetch_plan_info(
        schemes_and_questions, scheme_info, consents
    )

    visible_plan_count = plan_count - 2 if has_test_plans and not is_tester else plan_count

    assert len(plans) == visible_plan_count
    assert len(creds) == visible_plan_count * 6
    assert len(docs) == visible_plan_count * 4
    assert len(images) == visible_plan_count * 3
    assert len(tp_consent_links) == visible_plan_count * 4
    assert len(details) == visible_plan_count * 3
    assert len(contents) == visible_plan_count * 3
    assert len(plan_ids_in_wallet) == 1
    assert plan_ids_in_wallet[0][0] == plan_in_wallet.id


@pytest.mark.parametrize("image_kwargs", IMG_KWARGS)
def test_all_plan_image_logic(
    db_session: "Session",
    setup_loyalty_plans_handler: typing.Callable[..., tuple[LoyaltyPlansHandler, User, Channel, list[PlanInfo]]],
    image_kwargs: tuple,
) -> None:
    plan_count = 3
    loyalty_plans_handler, user, channel, all_plan_info = setup_loyalty_plans_handler(plan_count=plan_count)

    SchemeImageFactory(scheme=all_plan_info[0].plan, **image_kwargs[0])
    db_session.flush()

    schemes_and_questions, scheme_info, consents, _, _ = loyalty_plans_handler._fetch_all_plan_information()
    _, _, _, images, *_ = fetch_plan_info(schemes_and_questions, scheme_info, consents)

    assert len(images) == (plan_count * 3) + image_kwargs[1]


def test_fetch_all_plan_information_overview(
    db_session: "Session",
    setup_loyalty_plans_handler: typing.Callable[..., tuple[LoyaltyPlansHandler, User, Channel, list[PlanInfo]]],
) -> None:
    plan_count = 3
    loyalty_plans_handler, user, channel, all_plan_info = setup_loyalty_plans_handler(plan_count=plan_count)

    plan_in_wallet = all_plan_info[0].plan
    setup_existing_loyalty_card(db_session, plan_in_wallet, user)

    schemes_and_images, plan_ids_in_wallet, _ = loyalty_plans_handler._fetch_all_plan_information_overview()

    plans = set()
    images = set()

    for plan_info in schemes_and_images:
        if plan_info[0] is not None:
            plans.add(plan_info[0])
            images.add(plan_info[1])

    images.remove(None)

    assert len(plans) == plan_count
    assert not images  # No ICON images
    assert len(plan_ids_in_wallet) == 1
    assert plan_ids_in_wallet[0][0] == plan_in_wallet.id


@pytest.mark.parametrize("has_test_plans", [True, False])
@pytest.mark.parametrize("is_tester", [True, False])
def test_fetch_all_plan_information_overview_test_flight(
    db_session: "Session",
    setup_loyalty_plans_handler: typing.Callable[..., tuple[LoyaltyPlansHandler, User, Channel, list[PlanInfo]]],
    is_tester: bool,
    has_test_plans: bool,
) -> None:
    plan_count = 3
    loyalty_plans_handler, user, channel, all_plan_info = setup_loyalty_plans_handler(plan_count=plan_count)
    loyalty_plans_handler.is_tester = is_tester

    if has_test_plans:
        for plan_info in all_plan_info[0:2]:
            # only one association is created during setup, so we can use the first item
            plan_info.plan.channel_associations[0].test_scheme = True

        db_session.flush()

    plan_in_wallet = all_plan_info[0].plan
    setup_existing_loyalty_card(db_session, plan_in_wallet, user)
    schemes_and_images, plan_ids_in_wallet, _ = loyalty_plans_handler._fetch_all_plan_information_overview()

    plans = set()
    images = set()

    for plan_info in schemes_and_images:
        if plan_info[0] is not None:
            plans.add(plan_info[0])
            images.add(plan_info[1])

    images.remove(None)  # type: ignore [arg-type]

    visible_plan_count = plan_count - 2 if has_test_plans and not is_tester else plan_count

    assert visible_plan_count == len(plans)
    assert not images  # No ICON images
    assert len(plan_ids_in_wallet) == 1
    assert plan_ids_in_wallet[0][0] == plan_in_wallet.id


def test_fetch_all_plan_information_overview_filters_suspended_inactive(
    db_session: "Session",
    setup_loyalty_plans_handler: typing.Callable[..., tuple[LoyaltyPlansHandler, User, Channel, list[PlanInfo]]],
) -> None:
    plan_count = 3
    loyalty_plans_handler, user, channel, all_plan_info = setup_loyalty_plans_handler(plan_count=plan_count)

    channel.scheme_associations[0].status = LoyaltyPlanChannelStatus.INACTIVE.value
    channel.scheme_associations[1].status = LoyaltyPlanChannelStatus.SUSPENDED.value
    db_session.flush()

    schemes_and_images, plan_ids_in_wallet, _ = loyalty_plans_handler._fetch_all_plan_information_overview()

    plans = set()
    images = set()

    for plan_info in schemes_and_images:
        if plan_info[0] is not None:
            plans.add(plan_info[0])
            images.add(plan_info[1])

    images.remove(None)

    assert len(plans) == 1
    assert not images  # No ICON images

    for association in channel.scheme_associations:
        if association.id == next(iter(plans)).id:
            assert association.status == LoyaltyPlanChannelStatus.ACTIVE


ICON_IMG_KWARGS = ({"url": "some/image-icon.jpg", "image_type_code": ImageTypes.ICON}, 1)
PLAN_OVERVIEW_IMG_KWARGS = IMG_KWARGS[1:]
PLAN_OVERVIEW_IMG_KWARGS += [ICON_IMG_KWARGS]


@pytest.mark.parametrize("image_kwargs", PLAN_OVERVIEW_IMG_KWARGS)
def test_all_plan_overview_image_logic(
    db_session: "Session",
    setup_loyalty_plans_handler: typing.Callable[..., tuple[LoyaltyPlansHandler, User, Channel, list[PlanInfo]]],
    image_kwargs: tuple,
) -> None:
    plan_count = 3
    loyalty_plans_handler, user, channel, all_plan_info = setup_loyalty_plans_handler(
        plan_count=plan_count, images_setup=False
    )

    for plan_info in all_plan_info:
        for _ in range(plan_count):
            SchemeImageFactory(
                scheme=plan_info.plan, image_type_code=random.choice([ImageTypes.HERO, ImageTypes.ALT_HERO])
            )

    SchemeImageFactory(scheme=all_plan_info[0].plan, **image_kwargs[0])
    db_session.flush()

    schemes_and_images, _, _ = loyalty_plans_handler._fetch_all_plan_information_overview()

    images = set()

    for plan_info in schemes_and_images:
        if plan_info[0] is not None:
            images.add(plan_info[1])

    images.remove(None)  # type: ignore [arg-type]

    assert len(images) == 0 + image_kwargs[1]


def test_plan_detail_image_logic(
    db_session: "Session",
    setup_loyalty_plan_handler: typing.Callable[..., tuple[LoyaltyPlanHandler, User, Channel, PlanInfo]],
) -> None:
    loyalty_plan_handler, user, channel, plan_info = setup_loyalty_plan_handler()
    SchemeImageFactory(scheme=plan_info.plan, image_type_code=random.choice([ImageTypes.HERO, ImageTypes.ALT_HERO]))
    SchemeImageFactory(scheme=plan_info.plan, **ICON_IMG_KWARGS[0])
    db_session.flush()

    plan_details = loyalty_plan_handler.get_plan_details()

    for detail in plan_details["images"]:
        assert detail["type"] == ImageTypes.ICON


def test_sort_info_by_plan(
    setup_loyalty_plans_handler: typing.Callable[..., tuple[LoyaltyPlansHandler, User, Channel, list[PlanInfo]]],
) -> None:
    plan_info_fields = ("credentials", "documents", "images", "consents", "tiers", "contents")
    plan_count = 3
    loyalty_plans_handler, user, channel, all_plan_info = setup_loyalty_plans_handler(plan_count=plan_count)

    (
        schemes_and_questions,
        scheme_info,
        consents,
        plan_ids_in_wallet,
        _,
    ) = loyalty_plans_handler._fetch_all_plan_information()
    sorted_plan_information = loyalty_plans_handler._sort_info_by_plan(
        schemes_and_questions, scheme_info, consents, plan_ids_in_wallet
    )

    plans = {plan_info[0] for plan_info in schemes_and_questions if plan_info[0] is not None}

    assert len(plans) == plan_count

    for plan in plans:
        assert plan.id in sorted_plan_information
        assert all(info_field in sorted_plan_information[plan.id] for info_field in plan_info_fields)

        for info_field in plan_info_fields:
            if info_field == "tiers":
                assert all(obj.scheme_id_id == plan.id for obj in sorted_plan_information[plan.id][info_field])
            else:
                assert all(obj.scheme_id == plan.id for obj in sorted_plan_information[plan.id][info_field])


def test_create_plan_and_images_dict_for_overview(
    db_session: "Session",
    setup_loyalty_plans_handler: typing.Callable[..., tuple[LoyaltyPlansHandler, User, Channel, list[PlanInfo]]],
) -> None:
    plan_count = 3
    loyalty_plans_handler, user, channel, all_plan_info = setup_loyalty_plans_handler(plan_count=plan_count)

    for plan in all_plan_info:
        SchemeImageFactory(scheme=plan.plan, url="some/image-icon.jpg", image_type_code=ImageTypes.ICON)

    db_session.flush()

    schemes_and_images, _, _ = loyalty_plans_handler._fetch_all_plan_information_overview()

    sorted_plan_information = loyalty_plans_handler._create_plan_and_images_dict_for_overview(schemes_and_images)

    assert len(sorted_plan_information) == plan_count

    for v in sorted_plan_information.values():
        assert isinstance(v["plan"], Scheme)
        assert len(v["images"]) == 1


def test_create_plan_and_images_dict_for_overview_no_images(
    setup_loyalty_plans_handler: typing.Callable[..., tuple[LoyaltyPlansHandler, User, Channel, list[PlanInfo]]],
) -> None:
    plan_count = 3
    loyalty_plans_handler, user, channel, all_plan_info = setup_loyalty_plans_handler(
        plan_count=plan_count, images_setup=False
    )

    schemes_and_images, _, _ = loyalty_plans_handler._fetch_all_plan_information_overview()

    sorted_plan_information = loyalty_plans_handler._create_plan_and_images_dict_for_overview(schemes_and_images)

    assert len(sorted_plan_information) == plan_count

    for v in sorted_plan_information.values():
        assert isinstance(v["plan"], Scheme)
        assert len(v["images"]) == 0


def test_format_images(
    db_session: "Session",
    setup_loyalty_plans_handler: typing.Callable[..., tuple[LoyaltyPlansHandler, User, Channel, list[PlanInfo]]],
) -> None:
    loyalty_plans_handler, _, _, all_plan_info = setup_loyalty_plans_handler()

    image_data = {
        "image1": {
            "id": 10,
            "image_type_code": ImageTypes.HERO.value,
            "image": "hello.png",
            "call_to_action": "https://foobar.url",
            "description": "some picture 1",
            "encoding": "wtvr",
            "expected_encoding": "wtvr",
            "order": 0,
        },
        "image2": {
            "id": 11,
            "image_type_code": ImageTypes.TIER.value,
            "image": "hello.png",
            "call_to_action": "https://bazfoo.url",
            "description": "some picture 2",
            "encoding": None,
            "expected_encoding": "png",
            "order": 0,
        },
        "image3": {
            "id": 12,
            "image_type_code": ImageTypes.ALT_HERO.value,
            "image": "hello",
            "call_to_action": "https://barbaz.url",
            "description": "some picture 3",
            "encoding": None,
            # Encoding method was copied from hermes. Not sure if this is expected behaviour
            "expected_encoding": "hello",
            "order": 0,
        },
    }

    images = [
        SchemeImageFactory(
            scheme=all_plan_info[0].plan,
            id=image["id"],
            image_type_code=image["image_type_code"],
            image=image["image"],
            call_to_action=image["call_to_action"],
            description=image["description"],
            encoding=image["encoding"],
            order=image["order"],
        )
        for image in image_data.values()
    ]

    db_session.commit()

    formatted_images = loyalty_plans_handler._format_images(images)

    all_images = zip(image_data.values(), formatted_images)
    for image, formatted_image in all_images:
        assert {
            "id": image["id"],
            "type": image["image_type_code"],
            "url": os.path.join(settings.CUSTOM_DOMAIN, typing.cast(str, image["image"])),
            "cta_url": image["call_to_action"],
            "description": image["description"],
            "encoding": image["expected_encoding"],
            "order": 0,
        } == formatted_image


def test_format_images_for_overview(
    db_session: "Session",
    setup_loyalty_plans_handler: typing.Callable[..., tuple[LoyaltyPlansHandler, User, Channel, list[PlanInfo]]],
) -> None:
    loyalty_plans_handler, _, _, all_plan_info = setup_loyalty_plans_handler()

    image_data: dict[str, dict] = {
        "image1": {
            "id": 10,
            "image_type_code": ImageTypes.ICON.value,
            "image": "hello.png",
            "call_to_action": "https://foobar.url",
            "description": "some picture 1",
            "encoding": "wtvr",
            "expected_encoding": "wtvr",
            "order": 0,
        },
        "image2": {
            "id": 11,
            "image_type_code": ImageTypes.TIER.value,
            "image": "hello.png",
            "call_to_action": "https://bazfoo.url",
            "description": "some picture 2",
            "encoding": None,
            "expected_encoding": "png",
            "order": 0,
        },
        "image3": {
            "id": 12,
            "image_type_code": ImageTypes.ALT_HERO.value,
            "image": "hello",
            "call_to_action": "https://barbaz.url",
            "description": "some picture 3",
            "encoding": None,
            # Encoding method was copied from hermes. Not sure if this is expected behaviour
            "expected_encoding": "hello",
            "order": 0,
        },
    }

    images = [
        SchemeImageFactory(
            scheme=all_plan_info[0].plan,
            id=image["id"],
            image_type_code=image["image_type_code"],
            image=image["image"],
            call_to_action=image["call_to_action"],
            description=image["description"],
            encoding=image["encoding"],
            order=image["order"],
        )
        for image in image_data.values()
    ]

    db_session.commit()

    formatted_images: list[dict] = loyalty_plans_handler._format_images(images, overview=True)

    all_images = zip(image_data.values(), formatted_images)
    # Zip only iterates over smallest list, so this will only compare the 1 filtered image.
    for image, formatted_image in all_images:
        assert {
            "id": image["id"],
            "type": image["image_type_code"],
            "url": os.path.join(settings.CUSTOM_DOMAIN, typing.cast(str, image["image"])),
            "cta_url": image["call_to_action"],
            "description": image["description"],
            "encoding": image["expected_encoding"],
            "order": 0,
        } == formatted_image

    assert len(formatted_images) == 1


def test_format_tiers(
    db_session: "Session",
    setup_loyalty_plans_handler: typing.Callable[..., tuple[LoyaltyPlansHandler, User, Channel, list[PlanInfo]]],
) -> None:
    """SchemeDetails are referred to as tiers for some reason"""
    loyalty_plans_handler, _, _, all_plan_info = setup_loyalty_plans_handler()

    detail_data = [
        {"name": "detail1", "description": "some description 1"},
        {"name": "detail2", "description": "some description 2"},
    ]

    details = [
        SchemeDetailFactory(
            scheme=all_plan_info[0].plan,
            name=detail["name"],
            description=detail["description"],
        )
        for detail in detail_data
    ]

    db_session.commit()

    formatted_details = loyalty_plans_handler._format_tiers(details)
    all_details = zip(detail_data, formatted_details)

    for detail, formatted_detail in all_details:
        assert {
            "name": detail["name"],
            "description": detail["description"],
        } == formatted_detail


def test_format_contents(
    db_session: "Session",
    setup_loyalty_plans_handler: typing.Callable[..., tuple[LoyaltyPlansHandler, User, Channel, list[PlanInfo]]],
) -> None:
    loyalty_plans_handler, _, _, all_plan_info = setup_loyalty_plans_handler()

    content_data = [{"column": "content1", "value": "some value 1"}, {"column": "content2", "value": "some value 2"}]

    contents = [
        SchemeContentFactory(
            scheme=all_plan_info[0].plan,
            column=content["column"],
            value=content["value"],
        )
        for content in content_data
    ]

    db_session.commit()

    formatted_contents = loyalty_plans_handler._format_contents(contents)
    all_contents = zip(content_data, formatted_contents)

    for content, formatted_content in all_contents:
        assert {
            "column": content["column"],
            "value": content["value"],
        } == formatted_content


def test__get_journeys_single(
    journey_fields: dict,
    setup_loyalty_plans_handler: typing.Callable[..., tuple[LoyaltyPlansHandler, User, Channel, list[PlanInfo]]],
) -> None:
    loyalty_plans_handler, _, _, _ = setup_loyalty_plans_handler()

    add = {"type": 0, "description": LoyaltyPlanJourney.ADD}, CredentialField.ADD_FIELD
    auth = {"type": 1, "description": LoyaltyPlanJourney.AUTHORISE}, CredentialField.AUTH_FIELD
    register = {"type": 2, "description": LoyaltyPlanJourney.REGISTER}, CredentialField.REGISTER_FIELD
    join = {"type": 3, "description": LoyaltyPlanJourney.JOIN}, CredentialField.JOIN_FIELD

    for expected, field_type in (add, auth, register, join):
        fields: dict = {cred_field: {} for cred_field in CredentialField}
        fields.update({field_type: journey_fields[field_type]})
        journeys = loyalty_plans_handler._get_journeys(fields, True)

        assert [expected] == journeys


def test__get_journeys_single_single_field_auth(
    journey_fields: dict,
    setup_loyalty_plans_handler: typing.Callable[..., tuple[LoyaltyPlansHandler, User, Channel, list[PlanInfo]]],
) -> None:
    loyalty_plans_handler, _, _, _ = setup_loyalty_plans_handler()

    # no add or auth fields and authorisation is not required: no add or auth journeys
    fields: dict = {cred_field: {} for cred_field in CredentialField}
    assert [] == loyalty_plans_handler._get_journeys(fields, authorisation_required=False)

    # no auth fields and authorisation is required: only add journey
    fields.update({CredentialField.ADD_FIELD: journey_fields[CredentialField.ADD_FIELD]})
    assert [{"type": 0, "description": LoyaltyPlanJourney.ADD}] == loyalty_plans_handler._get_journeys(
        fields, authorisation_required=True
    )

    # no auth fields and authorisation is not required: add and auth jouneys
    assert [
        {"type": 0, "description": LoyaltyPlanJourney.ADD},
        {"type": 1, "description": LoyaltyPlanJourney.AUTHORISE},
    ] == loyalty_plans_handler._get_journeys(fields, authorisation_required=False)


def test__get_journeys_multi(
    journey_fields: dict,
    setup_loyalty_plans_handler: typing.Callable[..., tuple[LoyaltyPlansHandler, User, Channel, list[PlanInfo]]],
) -> None:
    loyalty_plans_handler, _, _, _ = setup_loyalty_plans_handler()
    expected = [
        {"type": 0, "description": LoyaltyPlanJourney.ADD},
        {"type": 1, "description": LoyaltyPlanJourney.AUTHORISE},
        {"type": 2, "description": LoyaltyPlanJourney.REGISTER},
        {"type": 3, "description": LoyaltyPlanJourney.JOIN},
    ]

    journeys = loyalty_plans_handler._get_journeys(journey_fields, True)

    assert expected == journeys

    journey_fields_no_add = journey_fields.copy()
    journey_fields_no_add[CredentialField.ADD_FIELD] = {}

    expected = [
        {"type": 1, "description": LoyaltyPlanJourney.AUTHORISE},
        {"type": 2, "description": LoyaltyPlanJourney.REGISTER},
        {"type": 3, "description": LoyaltyPlanJourney.JOIN},
    ]

    journeys = loyalty_plans_handler._get_journeys(journey_fields_no_add, True)

    assert expected == journeys


@patch.object(LoyaltyPlansHandler, "_format_contents")
@patch.object(LoyaltyPlansHandler, "_format_tiers")
@patch.object(LoyaltyPlansHandler, "_format_images")
def test_format_plan_data(
    mock_format_contents: MagicMock,
    mock_format_tiers: MagicMock,
    mock_format_images: MagicMock,
    db_session: "Session",
    setup_loyalty_plans_handler: typing.Callable[..., tuple[LoyaltyPlansHandler, User, Channel, list[PlanInfo]]],
) -> None:
    mock_format_contents.return_value = {}
    mock_format_tiers.return_value = {}
    mock_format_images.return_value = {}
    loyalty_plans_handler, user, channel, all_plan_info = setup_loyalty_plans_handler()
    plan_info = all_plan_info[0]
    is_in_wallet = True

    journey_fields = LoyaltyPlanHandlerFactory(
        user_id=user.id,
        channel_id=channel.id,
        db_session=db_session,
        loyalty_plan_id=plan_info.plan.id,
    ).get_journey_fields(
        plan=plan_info.plan,
        creds=plan_info.questions,
        docs=plan_info.documents,
        consents=plan_info.consents,
    )

    formatted_data = loyalty_plans_handler._format_plan_data(
        plan=plan_info.plan,
        images=plan_info.images,
        tiers=plan_info.details,
        journey_fields=journey_fields,
        contents=plan_info.contents,
        is_in_wallet=is_in_wallet,
    )

    plan = plan_info.plan

    journeys = [
        {"type": 0, "description": LoyaltyPlanJourney.ADD},
        {"type": 1, "description": LoyaltyPlanJourney.AUTHORISE},
        {"type": 2, "description": LoyaltyPlanJourney.REGISTER},
        {"type": 3, "description": LoyaltyPlanJourney.JOIN},
    ]

    assert {
        "loyalty_plan_id": plan.id,
        "is_in_wallet": is_in_wallet,
        "plan_popularity": plan.plan_popularity,
        "plan_features": {
            "has_points": plan.has_points,
            "has_transactions": plan.has_transactions,
            "plan_type": 1,
            "barcode_type": plan.barcode_type,
            "colour": plan.colour,
            "text_colour": plan.text_colour,
            "journeys": journeys,
        },
        "images": mock_format_images.return_value,
        "plan_details": {
            "company_name": plan.company,
            "plan_name": plan.name,
            "plan_label": plan.plan_name_card,
            "plan_url": plan.url,
            "plan_summary": plan.plan_summary,
            "plan_description": plan.plan_description,
            "redeem_instructions": plan.barcode_redeem_instructions,
            "plan_register_info": plan.plan_register_info,
            "join_incentive": plan.enrol_incentive,
            "category": plan.category.name,
            "tiers": mock_format_tiers.return_value,
            "forgotten_password_url": plan.forgotten_password_url,
        },
        "journey_fields": journey_fields,
        "content": mock_format_contents.return_value,
    } == formatted_data


@patch.object(LoyaltyPlansHandler, "_format_images")
def test_format_plan_data_overview(
    mock_format_images: MagicMock,
    db_session: "Session",
    setup_loyalty_plans_handler: typing.Callable[..., tuple[LoyaltyPlansHandler, User, Channel, list[PlanInfo]]],
) -> None:
    mock_format_images.return_value = {}
    loyalty_plans_handler, user, channel, all_plan_info = setup_loyalty_plans_handler()
    plan_info = all_plan_info[0]

    formatted_data = loyalty_plans_handler._format_plan_data_overview(
        plan=plan_info.plan,
        images=plan_info.images,
        is_in_wallet=True,
    )

    plan = plan_info.plan

    assert {
        "loyalty_plan_id": plan.id,
        "is_in_wallet": True,
        "plan_name": plan.name,
        "company_name": plan.company,
        "plan_popularity": plan.plan_popularity,
        "plan_type": 1,
        "colour": plan.colour,
        "text_colour": plan.text_colour,
        "category": plan.category.name,
        "images": mock_format_images.return_value,
        "forgotten_password_url": plan.forgotten_password_url,
    } == formatted_data


def test_get_all_plans(
    setup_loyalty_plans_handler: typing.Callable[..., tuple[LoyaltyPlansHandler, User, Channel, list[PlanInfo]]],
) -> None:
    plan_count = 3
    loyalty_plans_handler, user, channel, all_plan_info = setup_loyalty_plans_handler(plan_count=plan_count)

    all_plans = loyalty_plans_handler.get_all_plans()

    for plan in all_plans:
        for journey_field in plan["journey_fields"].values():
            cred_order = [credential["order"] for credential in journey_field["credentials"]]
            doc_order = [doc["order"] for doc in journey_field["plan_documents"]]
            consent_order = [consent["order"] for consent in journey_field["consents"]]

            assert sorted(cred_order) == cred_order
            assert sorted(doc_order) == doc_order
            assert sorted(consent_order) == consent_order

    assert plan_count == len(all_plans)


def test_get_all_plans_overview(
    db_session: "Session",
    setup_loyalty_plans_handler: typing.Callable[..., tuple[LoyaltyPlansHandler, User, Channel, list[PlanInfo]]],
) -> None:
    plan_count = 3
    loyalty_plans_handler, user, channel, all_plan_info = setup_loyalty_plans_handler(plan_count=plan_count)
    setup_existing_loyalty_card(db_session, all_plan_info[0].plan, user)

    all_plans = loyalty_plans_handler.get_all_plans_overview()

    plan_ids_in_wallet = db_session.execute(
        select(SchemeAccount.scheme_id)
        .join(SchemeAccountUserAssociation, SchemeAccountUserAssociation.scheme_account_id == SchemeAccount.id)
        .where(SchemeAccountUserAssociation.user_id == user.id)
    )

    plan_ids_in_wallet = {row[0] for row in plan_ids_in_wallet}

    assert plan_count == len(all_plans)

    for plan in all_plans:
        assert plan["is_in_wallet"] == (plan["loyalty_plan_id"] in plan_ids_in_wallet)


@pytest.mark.parametrize(
    ("popularities", "expected_order"),
    (
        (
            [1, 1, 2, 3, 4, None, None],
            [1, 2, 3, 4, 5, 6, 7],
        ),
        (
            [7, 6, 5, 4, 3, 2, 1],
            [7, 6, 5, 4, 3, 2, 1],
        ),
        (
            [2, 1, 1, None, 2, None, 1],
            [4, 1, 2, 6, 5, 7, 3],
        ),
    ),
)
def test_get_all_plans_and_overview_ordering(
    popularities: list[int | None],
    expected_order: list[int],
    db_session: "Session",
    setup_loyalty_plans_handler: typing.Callable[..., tuple[LoyaltyPlansHandler, User, Channel, list[PlanInfo]]],
) -> None:
    plan_names = ["AAA", "AAB", "AAC", "AAD", "AAE", "AAF", "AAG"]
    assert len(plan_names) == len(popularities) == len(expected_order)

    plan_count = len(plan_names)
    loyalty_plans_handler, _, _, all_plan_info = setup_loyalty_plans_handler(plan_count=plan_count)

    expected_order_dict = {}
    for i, plan_name in enumerate(plan_names):
        all_plan_info[i].plan.name = plan_name
        all_plan_info[i].plan.channel_associations[0].plan_popularity = popularities[i]
        expected_order_dict[expected_order[i]] = all_plan_info[i].plan.id

    db_session.flush()

    all_plans = loyalty_plans_handler.get_all_plans(order_by_popularity=True)
    all_plans_overview = loyalty_plans_handler.get_all_plans_overview()

    for res in (all_plans, all_plans_overview):
        assert len(res) == plan_count
        for i, plan in enumerate(res, start=1):
            assert plan["loyalty_plan_id"] == expected_order_dict[i]
