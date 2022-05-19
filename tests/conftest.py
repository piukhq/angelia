import pytest
from sqlalchemy_utils import create_database, database_exists, drop_database

from app.handlers.loyalty_plan import LoyaltyPlanChannelStatus, LoyaltyPlanJourney
from app.hermes.db import DB
from app.hermes.models import Channel, SchemeChannelAssociation
from tests.common import Session
from tests.factories import ChannelFactory, LoyaltyPlanFactory, UserFactory


@pytest.fixture(scope="session")
def setup_db():
    if DB().engine.url.database != "hermes_test":
        raise ValueError(f"Unsafe attempt to recreate database: {DB().engine.url.database}")

    if database_exists(DB().engine.url):
        drop_database(DB().engine.url)

    create_database(DB().engine.url)
    DB().metadata.create_all(DB().engine)

    yield

    # At end of all tests, drop the test db
    drop_database(DB().engine.url)


@pytest.fixture(scope="function")
def db_session(setup_db):
    connection = DB().engine.connect()
    connection.begin()
    Session.configure(autocommit=False, autoflush=False, bind=connection)
    session = Session()

    yield session

    session.rollback()
    Session.remove()
    connection.close()


@pytest.fixture
def loyalty_plan():
    return {
        "loyalty_plan_id": 1,
        "is_in_wallet": True,
        "plan_popularity": None,
        "plan_features": {
            "has_points": True,
            "has_transactions": True,
            "plan_type": 1,
            "barcode_type": None,
            "colour": "#22e892",
            "text_colour": "#22e893",
            "journeys": [
                {"type": 0, "description": LoyaltyPlanJourney.ADD},
                {"type": 1, "description": LoyaltyPlanJourney.AUTHORISE},
                {"type": 2, "description": LoyaltyPlanJourney.REGISTER},
                {"type": 3, "description": LoyaltyPlanJourney.JOIN},
            ],
        },
        "images": [
            {
                "id": 3,
                "type": 2,
                "url": "/Users/kaziz/project/media/Democrat.jpg",
                "description": "Mean sometimes leader authority here. Memory which clear trip site less.",
                "encoding": "jpg",
                "order": 0,
            },
            {
                "id": 2,
                "type": 2,
                "url": "/Users/kaziz/project/media/Democrat.jpg",
                "description": "Mean sometimes leader authority here. Memory which clear trip site less.",
                "encoding": "jpg",
                "order": 0,
            },
            {
                "id": 1,
                "type": 2,
                "url": "/Users/kaziz/project/media/Democrat.jpg",
                "description": "Mean sometimes leader authority here. Memory which clear trip site less.",
                "encoding": "jpg",
                "order": 0,
            },
        ],
        "plan_details": {
            "company_name": "Flores, Reilly and Anderson",
            "plan_name": None,
            "plan_label": None,
            "plan_url": "https://www.testcompany244123.co.uk/testcompany",
            "plan_summary": "",
            "plan_description": "",
            "redeem_instructions": "",
            "plan_register_info": "",
            "join_incentive": "",
            "category": "Test Category",
            "tiers": [
                {
                    "name": "social",
                    "description": "Arm specific data someone his. Participant new really expert former tonight five",
                },
                {
                    "name": "market",
                    "description": "Arm specific data someone his. Participant new really expert former tonight five.",
                },
                {
                    "name": "team",
                    "description": "Arm specific data someone his. Participant new really expert former tonight five.",
                },
            ],
        },
        "journey_fields": {
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
                        "is_scannable": False,
                    }
                ],
                "plan_documents": [
                    {
                        "order": 1,
                        "name": "Test Document",
                        "url": "https://testdocument.com",
                        "description": "This is a test plan document",
                        "is_acceptance_required": True,
                    },
                    {
                        "order": 2,
                        "name": "Test Document",
                        "url": "https://testdocument.com",
                        "description": "This is a test plan document",
                        "is_acceptance_required": True,
                    },
                    {
                        "order": 3,
                        "name": "Test Document",
                        "url": "https://testdocument.com",
                        "description": "This is a test plan document",
                        "is_acceptance_required": True,
                    },
                ],
                "consents": [
                    {
                        "order": 0,
                        "consent_slug": "consent_slug_4",
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
                        "order": 3,
                        "consent_slug": "consent_slug_1",
                        "is_acceptance_required": False,
                        "description": "This is some really descriptive text right here",
                    },
                ],
            },
            "register_ghost_card_fields": {},
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
                        "is_scannable": True,
                        "alternative": {
                            "order": 1,
                            "display_label": "Card Number",
                            "validation": "",
                            "description": "",
                            "credential_slug": "card_number",
                            "type": "text",
                            "is_sensitive": False,
                            "is_scannable": False,
                        },
                    }
                ],
                "plan_documents": [
                    {
                        "order": 1,
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
                        "order": 3,
                        "display_label": "Memorable_date",
                        "validation": "",
                        "description": "",
                        "credential_slug": "memorable_date",
                        "type": "text",
                        "is_sensitive": False,
                        "is_scannable": False,
                    },
                    {
                        "order": 6,
                        "display_label": "Email",
                        "validation": "",
                        "description": "",
                        "credential_slug": "email",
                        "type": "text",
                        "is_sensitive": False,
                        "is_scannable": False,
                    },
                    {
                        "order": 9,
                        "display_label": "Password",
                        "validation": "",
                        "description": "",
                        "credential_slug": "password",
                        "type": "text",
                        "is_sensitive": False,
                        "is_scannable": False,
                    },
                ],
                "plan_documents": [
                    {
                        "order": 1,
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
        },
        "content": [
            {
                "column": "federal",
                "value": "Although with meeting gas different bag hear.  Culture result suffer mention us.",
            },
            {
                "column": "event",
                "value": "Although with meeting gas different bag hear. Culture result suffer mention us.",
            },
            {
                "column": "laugh",
                "value": "Although with meeting gas different bag hear. Culture result suffer mention us.",
            },
        ],
    }


@pytest.fixture
def loyalty_plan_overview():
    return {
        "loyalty_plan_id": 1,
        "is_in_wallet": True,
        "plan_name": "Skynet Rewards",
        "company_name": "Skynet",
        "plan_popularity": None,
        "plan_type": 2,
        "colour": "#f80000",
        "text_colour": "#22e893",
        "category": "Robots",
        "images": [
            {
                "id": 3,
                "type": 3,
                "url": "/Users/kaziz/project/media/Democrat.jpg",
                "description": "Mean sometimes leader authority here. Memory which clear trip site less.",
                "encoding": "jpg",
                "order": 0,
            }
        ],
    }


@pytest.fixture
def loyalty_plan_details():
    return {
        "company_name": "Flores, Reilly and Anderson",
        "plan_name": None,
        "plan_label": None,
        "plan_url": "https://www.testcompany244123.co.uk/testcompany",
        "plan_summary": "",
        "plan_description": "",
        "redeem_instructions": "",
        "plan_register_info": "",
        "join_incentive": "",
        "category": "Test Category",
        "tiers": [
            {
                "name": "social",
                "description": "Arm specific data someone his. Participant new really expert former tonight five",
            },
            {
                "name": "market",
                "description": "Arm specific data someone his. Participant new really expert former tonight five.",
            },
            {
                "name": "team",
                "description": "Arm specific data someone his. Participant new really expert former tonight five.",
            },
        ],
        "images": [
            {
                "id": 3,
                "type": 2,
                "url": "/Users/kaziz/project/media/Democrat.jpg",
                "description": "Mean sometimes leader authority here. Memory which clear trip site less.",
                "encoding": "jpg",
                "order": 0,
            },
            {
                "id": 2,
                "type": 2,
                "url": "/Users/kaziz/project/media/Democrat.jpg",
                "description": "Mean sometimes leader authority here. Memory which clear trip site less.",
                "encoding": "jpg",
                "order": 0,
            },
            {
                "id": 1,
                "type": 2,
                "url": "/Users/kaziz/project/media/Democrat.jpg",
                "description": "Mean sometimes leader authority here. Memory which clear trip site less.",
                "encoding": "jpg",
                "order": 0,
            },
        ],
    }


@pytest.fixture(scope="function")
def setup_plan_channel_and_user(db_session: "Session"):
    def _setup_plan_channel_and_user(slug: str = None, channel: Channel = None, channel_link: bool = True):
        loyalty_plan = LoyaltyPlanFactory(slug=slug)
        channel = channel or ChannelFactory()
        user = UserFactory(client=channel.client_application)
        db_session.flush()

        if channel_link:
            sca = SchemeChannelAssociation(
                status=LoyaltyPlanChannelStatus.ACTIVE.value,
                bundle_id=channel.id,
                scheme_id=loyalty_plan.id,
                test_scheme=False,
            )
            db_session.add(sca)

        db_session.flush()

        return loyalty_plan, channel, user

    return _setup_plan_channel_and_user
