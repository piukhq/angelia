import typing
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy_utils import create_database, database_exists, drop_database

from app.api.helpers.vault import AESKeyNames
from app.api.serializers import WalletLoyaltyCardSerializer, WalletLoyaltyCardVoucherSerializer, WalletSerializer
from app.handlers.loyalty_card import ADD, CredentialClass, LoyaltyCardHandler
from app.handlers.loyalty_plan import LoyaltyPlanChannelStatus, LoyaltyPlanJourney
from app.hermes.db import DB
from app.hermes.models import (
    Channel,
    Scheme,
    SchemeAccount,
    SchemeAccountUserAssociation,
    SchemeChannelAssociation,
    SchemeCredentialQuestion,
    ThirdPartyConsentLink,
    User,
)
from app.lib.encryption import AESCipher
from app.lib.loyalty_card import LoyaltyCardStatus
from tests.common import Session
from tests.factories import (
    ChannelFactory,
    ClientApplicationFactory,
    ConsentFactory,
    LoyaltyCardAnswerFactory,
    LoyaltyCardFactory,
    LoyaltyCardHandlerFactory,
    LoyaltyCardUserAssociationFactory,
    LoyaltyPlanFactory,
    LoyaltyPlanQuestionFactory,
    ThirdPartyConsentLinkFactory,
    UserFactory,
    fake,
)
from tests.helpers.local_vault import set_vault_cache


@pytest.fixture(scope="session")
def setup_db() -> typing.Generator[None, None, None]:
    if DB().engine.url.database != "hermes_test":
        raise ValueError(f"Unsafe attempt to recreate database: {DB().engine.url.database}")

    if database_exists(DB().engine.url):
        drop_database(DB().engine.url)

    create_database(DB().engine.url)
    DB().metadata.create_all(DB().engine)

    yield

    # At end of all tests, drop the test db
    drop_database(DB().engine.url)


@pytest.fixture(scope="function", autouse=True)
def db_session(setup_db: None) -> typing.Generator[None, None, Session]:
    connection = DB().engine.connect()
    connection.begin()
    Session.configure(autocommit=False, autoflush=False, bind=connection)
    session = Session()

    yield session

    session.rollback()
    Session.remove()
    connection.close()


@pytest.fixture
def loyalty_plan() -> dict:
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
                "cta_url": "https://foobar.url",
                "description": "Mean sometimes leader authority here. Memory which clear trip site less.",
                "encoding": "jpg",
                "order": 0,
            },
            {
                "id": 2,
                "type": 2,
                "url": "/Users/kaziz/project/media/Democrat.jpg",
                "cta_url": "https://bazfoo.url",
                "description": "Mean sometimes leader authority here. Memory which clear trip site less.",
                "encoding": "jpg",
                "order": 0,
            },
            {
                "id": 1,
                "type": 2,
                "url": "/Users/kaziz/project/media/Democrat.jpg",
                "cta_url": None,
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
            "forgotten_password_url": "http://i-forgot-my-password.url",
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
                        "is_optional": False,
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
                        "is_optional": False,
                        "alternative": {
                            "order": 1,
                            "display_label": "Card Number",
                            "validation": "",
                            "description": "",
                            "credential_slug": "card_number",
                            "type": "text",
                            "is_sensitive": False,
                            "is_scannable": False,
                            "is_optional": False,
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
                        "is_optional": False,
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
                        "is_optional": False,
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
                        "is_optional": False,
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
def loyalty_plan_overview() -> dict:
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
                "cta_url": "https://foobar.url",
                "description": "Mean sometimes leader authority here. Memory which clear trip site less.",
                "encoding": "jpg",
                "order": 0,
            }
        ],
        "forgotten_password_url": "http://i-forgot-my-password.url",
    }


@pytest.fixture
def loyalty_plan_details() -> dict:
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


@pytest.fixture
def merchant_fields_data() -> dict:
    return {"account_id": "12e34r3edvcsd"}


@pytest.fixture
def trusted_add_account_add_field_data(merchant_fields_data: dict) -> dict:
    return {
        "add_fields": {"credentials": [{"credential_slug": "card_number", "value": "9511143200133540455525"}]},
        "merchant_fields": merchant_fields_data,
    }


@pytest.fixture
def trusted_add_account_single_auth_field_data(merchant_fields_data: dict) -> dict:
    return {
        "authorise_fields": {"credentials": [{"credential_slug": "email", "value": "someemail@bink.com"}]},
        "merchant_fields": merchant_fields_data,
    }


@pytest.fixture
def trusted_add_req_data(trusted_add_account_add_field_data: dict) -> dict:
    return {
        "loyalty_plan_id": 77,
        "account": trusted_add_account_add_field_data,
    }


@pytest.fixture
def add_account_data() -> dict:
    return {"add_fields": {"credentials": [{"credential_slug": "card_number", "value": "9511143200133540455525"}]}}


@pytest.fixture
def add_req_data(add_account_data: dict) -> dict:
    return {
        "loyalty_plan_id": 77,
        "account": add_account_data,
    }


@pytest.fixture
def add_and_auth_account_data() -> dict:
    return {
        "add_fields": {"credentials": [{"credential_slug": "card_number", "value": "663344667788"}]},
        "authorise_fields": {
            "credentials": [
                {"credential_slug": "email", "value": "some@email.com"},
                {"credential_slug": "password", "value": "password123"},
            ]
        },
    }


@pytest.fixture
def add_and_auth_req_data(add_and_auth_account_data: dict) -> dict:
    return {
        "loyalty_plan_id": 718,
        "account": add_and_auth_account_data,
    }


@pytest.fixture
def auth_req_data() -> dict:
    return {
        "account": {
            "authorise_fields": {"credentials": [{"credential_slug": "password", "value": "password123"}]},
        },
    }


@pytest.fixture
def add_register_req_data() -> dict:
    return {
        "loyalty_plan_id": 718,
        "account": {
            "add_fields": {"credentials": [{"credential_slug": "card_number", "value": "663344667788"}]},
            "register_ghost_card_fields": {
                "credentials": [{"credential_slug": "postcode", "value": "9511143200133540455525"}],
                "consents": [{"consent_slug": "Consent_1", "value": "GU554JG"}],
            },
        },
    }


@pytest.fixture
def register_req_data() -> dict:
    return {
        "account": {
            "register_ghost_card_fields": {"credentials": [{"credential_slug": "postcode", "value": "GU22TT"}]},
        },
    }


@pytest.fixture
def join_req_data() -> dict:
    return {
        "loyalty_plan_id": 718,
        "account": {
            "join_fields": {"credentials": [{"credential_slug": "postcode", "value": "GU556WH"}]},
        },
    }


@pytest.fixture(scope="function")
def setup_plan_channel_and_user(
    db_session: "Session",
) -> typing.Callable[[str | None, Scheme | None, Channel | None, bool, bool], tuple[Scheme, Channel, User]]:
    def _setup_plan_channel_and_user(
        slug: str | None = None,
        loyalty_plan: Scheme | None = None,
        channel: Channel | None = None,
        channel_link: bool = True,
        is_trusted_channel: bool = False,
    ) -> tuple[Scheme, Channel, User]:
        loyalty_plan = loyalty_plan or LoyaltyPlanFactory(slug=slug)
        channel = channel or ChannelFactory(is_trusted=is_trusted_channel)
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


@pytest.fixture(scope="function")
def setup_loyalty_card_handler(
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
    setup_credentials: typing.Callable[[LoyaltyCardHandler, str], None],
    setup_consents: typing.Callable[[dict, Channel], list[ThirdPartyConsentLink]],
) -> typing.Callable[
    [bool, bool, bool, str, dict | None, str, int | None],
    tuple[
        LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User, list[ThirdPartyConsentLink] | None
    ],
]:
    def _setup_loyalty_card_handler(
        channel_link: bool = True,
        consents: bool = False,
        questions: bool = True,
        credentials: str | None = None,
        all_answer_fields: dict | None = None,
        journey: str = ADD,
        loyalty_plan_id: int | None = None,
    ) -> tuple[
        LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User, list[ThirdPartyConsentLink] | None
    ]:
        if not all_answer_fields:
            all_answer_fields = {}

        loyalty_plan, channel, user = setup_plan_channel_and_user(slug=fake.slug(), channel_link=channel_link)

        created_questions = setup_questions(loyalty_plan)

        if loyalty_plan_id is None:
            loyalty_plan_id = loyalty_plan.id

        consents_list: list[ThirdPartyConsentLink] | None = None
        if consents:
            consents_list = setup_consents(loyalty_plan, channel)

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

        return loyalty_card_handler, loyalty_plan, created_questions, channel, user, consents_list

    return _setup_loyalty_card_handler


@pytest.fixture()
def setup_loyalty_card(
    db_session: "Session",
) -> typing.Callable[
    [Scheme | int, User, SchemeAccount | None, bool], tuple[SchemeAccount, SchemeAccountUserAssociation | None]
]:
    def _loyalty_card(
        loyalty_plan: Scheme | int,
        user: "User",
        loyalty_card: "SchemeAccount | None" = None,
        answers: bool = True,
        **kwargs: typing.Any,
    ) -> tuple[SchemeAccount, SchemeAccountUserAssociation | None]:
        set_vault_cache(to_load=["aes-keys"])
        cipher = AESCipher(AESKeyNames.LOCAL_AES_KEY)

        loyalty_card = loyalty_card or typing.cast(SchemeAccount, LoyaltyCardFactory(scheme=loyalty_plan, **kwargs))
        db_session.flush()

        entry: SchemeAccountUserAssociation | None = None
        if answers:
            entry = LoyaltyCardUserAssociationFactory(
                scheme_account_id=loyalty_card.id,
                user_id=user.id,
                link_status=LoyaltyCardStatus.PENDING,
            )
            db_session.flush()

            LoyaltyCardAnswerFactory(
                question_id=3,
                scheme_account_entry_id=entry.id,
                answer="fake_email_1",
            )
            LoyaltyCardAnswerFactory(
                question_id=4,
                scheme_account_entry_id=entry.id,
                answer=cipher.encrypt("fake_password_1").decode("utf-8"),
            )
            db_session.commit()

        return loyalty_card, entry

    return _loyalty_card


@pytest.fixture(scope="session", autouse=True)
def wallet_serializer() -> typing.Generator[MagicMock, None, None]:
    with patch("app.resources.wallet.get_voucher_serializers") as mock_wallet_serializer:
        mock_wallet_serializer.return_value = [
            WalletLoyaltyCardSerializer,
            WalletSerializer,
            WalletLoyaltyCardVoucherSerializer,
        ]
        yield mock_wallet_serializer


@pytest.fixture(scope="function")
def setup_questions(
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
) -> typing.Callable[[Scheme], list[SchemeCredentialQuestion]]:
    def _setup_questions(loyalty_plan: Scheme) -> list[SchemeCredentialQuestion]:
        # Should reset sequence for setup_questions call. If we don't do this, all tests are going
        # to share a global sequence counter. This ensure the id field always starts at 1 for each test
        LoyaltyPlanQuestionFactory.reset_sequence()
        questions = [
            LoyaltyPlanQuestionFactory(
                scheme_id=loyalty_plan.id,
                type="card_number",
                label="Card Number",
                add_field=True,
                manual_question=True,
            ),
            LoyaltyPlanQuestionFactory(
                scheme_id=loyalty_plan.id,
                type="barcode",
                label="Barcode",
                add_field=True,
                scan_question=True,
            ),
            LoyaltyPlanQuestionFactory(
                scheme_id=loyalty_plan.id,
                type="email",
                label="Email",
                auth_field=True,
            ),
            LoyaltyPlanQuestionFactory(
                scheme_id=loyalty_plan.id,
                type="password",
                label="Password",
                auth_field=True,
            ),
            LoyaltyPlanQuestionFactory(
                scheme_id=loyalty_plan.id,
                type="postcode",
                label="Postcode",
                register_field=True,
                enrol_field=True,
            ),
            LoyaltyPlanQuestionFactory(
                scheme_id=loyalty_plan.id,
                type="last_name",
                label="Last Name",
                enrol_field=True,
            ),
            LoyaltyPlanQuestionFactory(
                scheme_id=loyalty_plan.id,
                type="merchant_identifier",
                label="Merchant Identifier",
                third_party_identifier=True,
                options=7,
            ),
        ]

        return questions

    return _setup_questions


@pytest.fixture(scope="function")
def setup_consents(db_session: "Session") -> typing.Callable[[Scheme, Channel], list[ThirdPartyConsentLink]]:
    def _setup_consents(loyalty_plan: Scheme, channel: Channel) -> list[ThirdPartyConsentLink]:
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

        db_session.commit()

        return consents

    return _setup_consents


@pytest.fixture(scope="function")
def setup_credentials(db_session: "Session") -> typing.Callable[[LoyaltyCardHandler, str], None]:
    # To help set up mock validated credentials for testing in later stages of the journey.
    # Only supports ADD for now but can add ADD_AND_AUTH etc.

    def _setup_credentials(loyalty_card_handler: LoyaltyCardHandler, credential_type: str) -> None:
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
