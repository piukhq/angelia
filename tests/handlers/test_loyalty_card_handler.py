import typing
from unittest.mock import patch

import arrow
import falcon
import pytest
from sqlalchemy import func, select

from tests.helpers.local_vault import set_vault_cache

if typing.TYPE_CHECKING:
    from unittest.mock import MagicMock

    from sqlalchemy.orm import Session

from app.api.exceptions import ResourceNotFoundError, ValidationError
from app.api.helpers.vault import AESKeyNames
from app.handlers.loyalty_card import (
    ADD,
    ADD_AND_AUTHORISE,
    ADD_AND_REGISTER,
    DELETE,
    JOIN,
    REGISTER,
    TRUSTED_ADD,
    CredentialClass,
    LoyaltyCardHandler,
)
from app.hermes.models import (
    Channel,
    Scheme,
    SchemeAccount,
    SchemeAccountUserAssociation,
    SchemeCredentialQuestion,
    ThirdPartyConsentLink,
    User,
)
from app.lib.encryption import AESCipher
from app.lib.loyalty_card import LoyaltyCardStatus, OriginatingJourney
from tests.factories import (
    ConsentFactory,
    LoyaltyCardAnswerFactory,
    LoyaltyCardFactory,
    LoyaltyCardHandlerFactory,
    LoyaltyCardUserAssociationFactory,
    LoyaltyPlanFactory,
    LoyaltyPlanQuestionFactory,
    UserFactory,
    fake,
)


@pytest.fixture(scope="function")
def setup_loyalty_card_handler(
    db_session: "Session",
    setup_plan_channel_and_user: typing.Callable[..., tuple[Scheme, Channel, User]],
    setup_questions: typing.Callable[[Scheme], list[SchemeCredentialQuestion]],
    setup_credentials: typing.Callable[[LoyaltyCardHandler, str], None],
    setup_consents: typing.Callable[[dict, Channel], list[ThirdPartyConsentLink]],
) -> typing.Callable[
    [bool, bool, bool, str, dict | None, str, int | None],
    tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
]:
    def _setup_loyalty_card_handler(
        channel_link: bool = True,
        consents: bool = False,
        questions: bool = True,
        credentials: str | None = None,
        all_answer_fields: dict | None = None,
        journey: str = ADD,
        loyalty_plan_id: int | None = None,
    ) -> tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User]:
        if not all_answer_fields:
            all_answer_fields = {}

        loyalty_plan, channel, user = setup_plan_channel_and_user(slug=fake.slug(), channel_link=channel_link)

        created_questions = setup_questions(loyalty_plan) if questions else []

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

        return loyalty_card_handler, loyalty_plan, created_questions, channel, user

    return _setup_loyalty_card_handler


# ------------FETCHING QUESTIONS, ANSWERS and EXISTING SCHEMES (in the case of PUT endpoints)-----------


def test_fetch_plan_and_questions(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that plan questions and scheme are successfully fetched"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    loyalty_card_handler.retrieve_plan_questions_and_answer_fields()

    assert len(loyalty_card_handler.plan_credential_questions[CredentialClass.ADD_FIELD]) == 2
    assert len(loyalty_card_handler.plan_credential_questions[CredentialClass.AUTH_FIELD]) == 2
    assert len(loyalty_card_handler.plan_credential_questions[CredentialClass.JOIN_FIELD]) == 2
    assert len(loyalty_card_handler.plan_credential_questions[CredentialClass.REGISTER_FIELD]) == 1

    assert isinstance(loyalty_card_handler.loyalty_plan, Scheme)

    for cred_class in CredentialClass:
        for question in loyalty_card_handler.plan_credential_questions[cred_class]:
            assert isinstance(
                loyalty_card_handler.plan_credential_questions[cred_class][question], SchemeCredentialQuestion
            )


def test_fetch_consents_register(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that plan consents are successfully fetched"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        journey=ADD_AND_REGISTER, consents=True
    )

    loyalty_card_handler.retrieve_plan_questions_and_answer_fields()

    assert loyalty_card_handler.plan_consent_questions
    assert len(loyalty_card_handler.plan_consent_questions) == 1


def test_error_if_plan_not_found(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that ValidationError occurs if no plan is found"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(loyalty_plan_id=763423)

    with pytest.raises(ValidationError):
        loyalty_card_handler.retrieve_plan_questions_and_answer_fields()


def test_error_if_questions_not_found(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that ValidationError occurs if no questions are found"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(questions=False)

    with pytest.raises(ValidationError):
        loyalty_card_handler.retrieve_plan_questions_and_answer_fields()


def test_error_if_channel_link_not_found(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that ValidationError occurs if no linked channel is found"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(channel_link=False)

    with pytest.raises(ValidationError):
        loyalty_card_handler.retrieve_plan_questions_and_answer_fields()


def test_answer_parsing(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
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


def test_fetch_single_card_link(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that a single card link is successfully fetched"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525")

    db_session.commit()

    LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.WALLET_ONLY,
    )

    db_session.commit()

    loyalty_card_handler.card_id = new_loyalty_card.id
    card_link = loyalty_card_handler.fetch_and_check_single_card_user_link()

    assert card_link
    assert isinstance(card_link, SchemeAccountUserAssociation)


def test_error_fetch_single_card_link_404(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that an error occurs if the local card id isn't found"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    db_session.commit()

    loyalty_card_handler.card_id = 99

    with pytest.raises(ResourceNotFoundError):
        loyalty_card_handler.fetch_and_check_single_card_user_link()


def test_fetch_card_links(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that card link is successfully fetched for auth/register journey"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525")

    db_session.commit()

    LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.WALLET_ONLY,
    )

    db_session.commit()

    loyalty_card_handler.card_id = new_loyalty_card.id
    loyalty_card_handler.fetch_and_check_existing_card_links()

    assert loyalty_card_handler.card
    assert loyalty_card_handler.loyalty_plan
    assert loyalty_card_handler.loyalty_plan_id


def test_error_fetch_card_links_not_found(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that fetching card link where none is present results in appropriate error for auth/register journey"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    new_loyalty_card = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number="9511143200133540455525",
    )

    other_user = UserFactory(client=channel.client_application)

    db_session.commit()

    LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=other_user.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )

    db_session.commit()

    loyalty_card_handler.card_id = new_loyalty_card.id

    with pytest.raises(ResourceNotFoundError):
        loyalty_card_handler.fetch_and_check_existing_card_links()


@pytest.mark.parametrize(
    "link_status, send_to_hermes",
    [
        (LoyaltyCardStatus.WALLET_ONLY, True),
        (LoyaltyCardStatus.UNKNOWN_ERROR, True),
        (LoyaltyCardStatus.REGISTRATION_FAILED, True),
        (LoyaltyCardStatus.PENDING, False),
        (LoyaltyCardStatus.REGISTRATION_ASYNC_IN_PROGRESS, False),
    ],
)
def test_register_checks_all_clear(
    link_status: str,
    send_to_hermes: bool,
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests happy path for extra registration checks"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    new_loyalty_card = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number="9511143200133540455525",
    )

    other_user = UserFactory(client=channel.client_application)

    db_session.commit()

    user_asc = LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=other_user.id,
        link_status=link_status,
    )

    db_session.commit()

    loyalty_card_handler.link_to_user = user_asc
    loyalty_card_handler.card_id = new_loyalty_card.id
    loyalty_card_handler.card = new_loyalty_card

    sent = loyalty_card_handler.register_journey_additional_checks()

    assert send_to_hermes == sent


@pytest.mark.parametrize("link_status", [LoyaltyCardStatus.ACTIVE, LoyaltyCardStatus.PRE_REGISTERED_CARD])
def test_error_register_checks_card_raises_conflict(
    link_status: str,
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that registration journey errors when found card is already active or pre-registered"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525")

    other_user = UserFactory(client=channel.client_application)

    db_session.commit()

    user_asc = LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=other_user.id,
        link_status=link_status,
    )

    db_session.commit()

    loyalty_card_handler.link_to_user = user_asc
    loyalty_card_handler.card_id = new_loyalty_card.id
    loyalty_card_handler.card = new_loyalty_card

    with pytest.raises(falcon.HTTPConflict) as e:
        loyalty_card_handler.register_journey_additional_checks()
    assert str(e.value.code) == "ALREADY_REGISTERED"


ALL_STATUSES = LoyaltyCardStatus.STATUS_MAPPING.keys()
REGISTER_STATUSES = LoyaltyCardStatus.REGISTRATION_IN_PROGRESS + LoyaltyCardStatus.REGISTRATION_FAILED_STATES


@pytest.mark.parametrize(
    "link_status",
    ALL_STATUSES
    - REGISTER_STATUSES
    - {LoyaltyCardStatus.ACTIVE, LoyaltyCardStatus.WALLET_ONLY, LoyaltyCardStatus.PRE_REGISTERED_CARD},
)
def test_error_register_checks_card_other_status(
    link_status: str,
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that registration journey errors when found card is in any non-register related error state"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525")

    other_user = UserFactory(client=channel.client_application)

    db_session.commit()

    user_asc = LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=other_user.id,
        link_status=link_status,
    )

    db_session.commit()

    loyalty_card_handler.link_to_user = user_asc
    loyalty_card_handler.card_id = new_loyalty_card.id
    loyalty_card_handler.card = new_loyalty_card

    with pytest.raises(falcon.HTTPConflict) as e:
        loyalty_card_handler.register_journey_additional_checks()
    assert str(e.value.code) == "REGISTRATION_ERROR"


# ------------VALIDATION OF CREDENTIALS-----------


def test_credential_validation_add_fields_only(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
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


def test_credential_validation_add_and_auth(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
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


def test_credential_validation_error_missing_auth(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
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


def test_credential_validation_error_invalid_answer(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
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


def test_credential_validation_error_no_key_credential(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
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


def test_consent_validation(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that consents are successfully validated"""

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


def test_consent_validation_no_consents(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that no validation error occurs when no consents are provided, and none supplied'"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    loyalty_card_handler.all_answer_fields = {"register_ghost_card_fields": {"consents": []}}

    loyalty_card_handler.validate_and_refactor_consents()


def test_error_consent_validation_no_matching_consent_questions(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that ValidationError occurs when consents are provided but not matching"""

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


def test_error_consent_validation_unnecessary_consent(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that ValidationError occurs when consents are provided but not required'"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    loyalty_card_handler.all_answer_fields = {
        "register_ghost_card_fields": {
            "consents": [{"consent_slug": "Consent_1", "value": True}, {"consent_slug": "Consent_2", "value": True}]
        }
    }

    loyalty_card_handler.plan_consent_questions = []

    with pytest.raises(ValidationError):
        loyalty_card_handler.validate_and_refactor_consents()


def test_error_consent_validation_insufficient_consent(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that ValidationError occurs when adequate consents are required but not provided'"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    loyalty_card_handler.all_answer_fields = {"register_ghost_card_fields": {"consents": []}}

    loyalty_card_handler.plan_consent_questions = [ConsentFactory()]

    with pytest.raises(ValidationError):
        loyalty_card_handler.validate_and_refactor_consents()


def test_auth_fields_match(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    setup_loyalty_card: typing.Callable[..., tuple[SchemeAccount, SchemeAccountUserAssociation]],
) -> None:
    """Tests successful matching of auth credentials"""
    set_vault_cache(to_load=["aes-keys"])
    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    new_loyalty_card, entry = setup_loyalty_card(
        loyalty_plan,
        user,
        card_number="9511143200133540455525",
    )
    loyalty_card_handler.card_id = new_loyalty_card.id

    loyalty_card_handler.auth_fields = [
        {"credential_slug": "email", "value": "fake_email_1"},
        {"credential_slug": "password", "value": "fake_password_1"},
    ]

    loyalty_card_handler.link_to_user = entry

    existing_creds, match_all = loyalty_card_handler.check_auth_credentials_against_existing()

    assert existing_creds
    assert match_all


def test_auth_fields_do_not_match(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    setup_loyalty_card: typing.Callable[..., tuple[SchemeAccount, SchemeAccountUserAssociation]],
) -> None:
    """Tests expected path where auth credentials do not match"""
    set_vault_cache(to_load=["aes-keys"])
    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()
    new_loyalty_card, entry = setup_loyalty_card(
        loyalty_plan,
        user,
        answers=True,
        card_number="9511143200133540455525",
    )

    loyalty_card_handler.card_id = new_loyalty_card.id

    loyalty_card_handler.link_to_user = entry

    loyalty_card_handler.auth_fields = [
        {"credential_slug": "email", "value": "incorrect_email"},
        {"credential_slug": "password", "value": "incorrect_password"},
    ]

    existing, all_match = loyalty_card_handler.check_auth_credentials_against_existing()

    assert existing
    assert not all_match


def test_no_existing_auth_fields(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    setup_loyalty_card: typing.Callable[..., tuple[SchemeAccount, SchemeAccountUserAssociation]],
) -> None:
    """Tests expected path when no existing auth credentials are found"""
    set_vault_cache(to_load=["aes-keys"])
    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    new_loyalty_card, entry = setup_loyalty_card(
        loyalty_plan,
        user,
        answers=False,
        card_number="9511143200133540455525",
    )
    loyalty_card_handler.card_id = new_loyalty_card.id

    entry = LoyaltyCardUserAssociationFactory(scheme_account_id=new_loyalty_card.id, user_id=user.id)

    loyalty_card_handler.link_to_user = entry

    loyalty_card_handler.auth_fields = [
        {"credential_slug": "email", "value": "incorrect_email"},
        {"credential_slug": "password", "value": "incorrect_password"},
    ]

    existing_creds, match_all = loyalty_card_handler.check_auth_credentials_against_existing()

    assert not existing_creds


# ------------LOYALTY CARD CREATION/RETURN-----------


def test_barcode_generation_no_regex(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
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


def test_card_number_generation(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
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


def test_barcode_generation(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
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
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests query and routing for an existing Loyalty Card not linked to this user (ADD journey)"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(credentials=ADD)

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525")

    other_user = UserFactory(client=channel.client_application)

    db_session.commit()

    LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=other_user.id,
        link_status=LoyaltyCardStatus.WALLET_ONLY,
    )

    db_session.commit()

    created = loyalty_card_handler.link_user_to_existing_or_create()

    assert mock_link_existing_account.called is True
    assert not created


def test_new_loyalty_card_add_routing_existing_already_linked(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests query and routing for an existing Loyalty Card already linked to this user (ADD)"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(credentials=ADD)

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525")

    db_session.commit()

    LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.WALLET_ONLY,
    )

    db_session.commit()

    with pytest.raises(falcon.HTTPConflict):
        loyalty_card_handler.link_user_to_existing_or_create()


@patch("app.handlers.loyalty_card.LoyaltyCardHandler.create_new_loyalty_card")
def test_new_loyalty_card_add_routing_create(
    mock_create_card: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests query and routing for a non-existent Loyalty Card (ADD journey)"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(credentials=ADD)

    created = loyalty_card_handler.link_user_to_existing_or_create()

    assert mock_create_card.called
    assert created


@patch("app.handlers.loyalty_card.LoyaltyCardHandler.link_account_to_user")
def test_new_loyalty_card_create_card(
    mock_link_new_loyalty_card: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests creation of a new Loyalty Card"""
    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(credentials=ADD)

    loyalty_card_handler.loyalty_plan = loyalty_plan

    loyalty_card_handler.create_new_loyalty_card()

    loyalty_cards = (
        db_session.query(SchemeAccount)
        .filter(
            SchemeAccount.id == loyalty_card_handler.card_id,
        )
        .all()
    )

    assert mock_link_new_loyalty_card.called is True
    assert len(loyalty_cards) == 1
    assert loyalty_cards[0].scheme == loyalty_plan
    assert loyalty_cards[0].card_number == "9511143200133540455525"
    assert loyalty_cards[0].barcode == ""
    assert loyalty_cards[0].alt_main_answer == ""


@patch("app.handlers.loyalty_card.LoyaltyCardHandler.link_account_to_user")
def test_new_loyalty_card_create_card_alt_main_answer(
    mock_link_new_loyalty_card: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests creation of a new Loyalty Card where the add credentials is an alternative_main_answer (e.g. email)"""
    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(questions=False)

    LoyaltyPlanQuestionFactory(
        id=1,
        scheme_id=loyalty_plan.id,
        type="email",
        label="Email",
        add_field=True,
        manual_question=True,
    )

    db_session.commit()

    loyalty_card_handler.key_credential = {
        "credential_question_id": 1,
        "credential_type": "email",
        "credential_class": CredentialClass.ADD_FIELD,
        "key_credential": True,
        "credential_answer": "testemail@bink.com",
    }

    loyalty_card_handler.valid_credentials = {
        "email": {
            "credential_question_id": 1,
            "credential_type": "email",
            "credential_class": CredentialClass.ADD_FIELD,
            "key_credential": True,
            "credential_answer": "testemail@bink.com",
        }
    }

    loyalty_card_handler.loyalty_plan = loyalty_plan

    loyalty_card_handler.create_new_loyalty_card()

    loyalty_cards = (
        db_session.query(SchemeAccount)
        .filter(
            SchemeAccount.id == loyalty_card_handler.card_id,
        )
        .all()
    )

    assert mock_link_new_loyalty_card.called is True
    assert len(loyalty_cards) == 1
    assert loyalty_cards[0].scheme == loyalty_plan
    assert loyalty_cards[0].alt_main_answer == "testemail@bink.com"
    assert loyalty_cards[0].card_number == ""
    assert loyalty_cards[0].barcode == ""


@patch("app.handlers.loyalty_card.LoyaltyCardHandler.link_account_to_user")
def test_new_loyalty_card_originating_journey_add(
    mock_link_new_loyalty_card: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests creation of a new Loyalty Card"""
    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(credentials=ADD)

    loyalty_card_handler.loyalty_plan = loyalty_plan

    loyalty_card_handler.create_new_loyalty_card()

    loyalty_cards = (
        db_session.query(SchemeAccount)
        .filter(
            SchemeAccount.id == loyalty_card_handler.card_id,
        )
        .all()
    )

    assert mock_link_new_loyalty_card.called is True
    assert len(loyalty_cards) == 1
    assert loyalty_cards[0].originating_journey == OriginatingJourney.ADD


def test_link_existing_loyalty_card(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
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


def test_error_link_existing_loyalty_card_bad_user(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
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
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    add_account_data: dict,
) -> None:
    """Tests that user is successfully linked to a newly created Scheme Account"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=add_account_data
    )

    loyalty_card_handler.handle_add_only_card()

    cards = (
        db_session.query(SchemeAccount)
        .filter(
            SchemeAccount.id == loyalty_card_handler.card_id,
        )
        .count()
    )

    links = (
        db_session.query(SchemeAccountUserAssociation)
        .filter(
            SchemeAccountUserAssociation.scheme_account_id == loyalty_card_handler.card_id,
            SchemeAccountUserAssociation.user_id == user.id,
        )
        .count()
    )

    assert links == 1
    assert cards == 1
    assert mock_hermes_msg.called is True


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_loyalty_card_add_journey_return_existing(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that existing loyalty card is returned when there is an existing LoyaltyCard and link to this user (ADD)"""

    answer_fields = {
        "add_fields": {"credentials": [{"credential_slug": "card_number", "value": "9511143200133540455525"}]},
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=answer_fields
    )

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525")

    db_session.commit()

    LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.WALLET_ONLY,
    )

    db_session.commit()

    with pytest.raises(falcon.HTTPConflict):
        loyalty_card_handler.handle_add_only_card()


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_loyalty_card_add_journey_link_to_existing(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that user is successfully linked to existing loyalty card when there is an existing LoyaltyCard and
    no link to this user (ADD)"""

    answer_fields = {
        "add_fields": {"credentials": [{"credential_slug": "card_number", "value": "9511143200133540455525"}]},
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=answer_fields
    )

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525")

    other_user = UserFactory(client=channel.client_application)

    db_session.commit()

    LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=other_user.id,
        link_status=LoyaltyCardStatus.WALLET_ONLY,
    )

    db_session.commit()

    created = loyalty_card_handler.handle_add_only_card()

    links = (
        db_session.query(SchemeAccountUserAssociation)
        .filter(
            SchemeAccountUserAssociation.scheme_account_id == loyalty_card_handler.card_id,
            SchemeAccountUserAssociation.user_id == user.id,
        )
        .count()
    )

    assert links == 1
    assert mock_hermes_msg.called  # must be called anyway
    assert loyalty_card_handler.card_id == new_loyalty_card.id
    assert not created


# ----------------COMPLETE ADD and AUTH JOURNEY------------------


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_new_loyalty_card_add_and_auth_journey_created_and_linked(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    add_and_auth_account_data: dict,
) -> None:
    """Tests that user is successfully linked to a newly created Scheme Account (ADD_AND_AUTH)"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=add_and_auth_account_data, journey=ADD_AND_AUTHORISE
    )

    loyalty_card_handler.handle_add_auth_card()

    cards = (
        db_session.query(SchemeAccount)
        .filter(
            SchemeAccount.id == loyalty_card_handler.card_id,
        )
        .all()
    )

    links = (
        db_session.query(SchemeAccountUserAssociation)
        .filter(
            SchemeAccountUserAssociation.scheme_account_id == loyalty_card_handler.card_id,
            SchemeAccountUserAssociation.user_id == user.id,
        )
        .count()
    )

    assert links == 1
    assert len(cards) == 1
    assert cards[0].originating_journey == OriginatingJourney.ADD
    assert mock_hermes_msg.called is True
    assert mock_hermes_msg.call_args[0][0] == "loyalty_card_add_auth"
    sent_dict = mock_hermes_msg.call_args[0][1]
    assert sent_dict["loyalty_card_id"] == loyalty_card_handler.card_id
    assert sent_dict["user_id"] == user.id
    assert sent_dict["channel_slug"] == "com.test.channel"


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_add_field_only_authorise(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    add_account_data: dict,
) -> None:
    """
    Tests that add_auth allows a single add field to authorise a card based on the loyalty plan
    authorisation_required flag.
    """
    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=add_account_data, journey=ADD_AND_AUTHORISE
    )

    loyalty_plan.authorisation_required = False
    db_session.add(loyalty_plan)
    db_session.commit()

    loyalty_card_handler.handle_add_auth_card()

    cards = (
        db_session.query(SchemeAccount)
        .filter(
            SchemeAccount.id == loyalty_card_handler.card_id,
        )
        .all()
    )

    links = (
        db_session.query(SchemeAccountUserAssociation)
        .filter(
            SchemeAccountUserAssociation.scheme_account_id == loyalty_card_handler.card_id,
            SchemeAccountUserAssociation.user_id == user.id,
        )
        .count()
    )

    assert links == 1
    assert len(cards) == 1
    assert cards[0].originating_journey == OriginatingJourney.ADD
    assert mock_hermes_msg.called is True
    assert mock_hermes_msg.call_args[0][0] == "loyalty_card_add_auth"
    sent_dict = mock_hermes_msg.call_args[0][1]
    assert sent_dict["loyalty_card_id"] == loyalty_card_handler.card_id
    assert sent_dict["user_id"] == user.id
    assert sent_dict["channel_slug"] == "com.test.channel"
    assert sent_dict["authorise_fields"] == []
    assert sent_dict["add_fields"] == [{"credential_slug": "card_number", "value": "9511143200133540455525"}]


def test_add_field_only_authorise_raises_error_when_authorisation_required(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    add_account_data: dict,
) -> None:
    """
    Tests that add_auth raises an error when a single add field is provided for authorisation for a loyalty
    plan that requires authorisation.
    """
    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=add_account_data, journey=ADD_AND_AUTHORISE
    )

    loyalty_plan.authorisation_required = True
    db_session.add(loyalty_plan)
    db_session.commit()

    with pytest.raises(ValidationError) as e:
        loyalty_card_handler.handle_add_auth_card()

    assert e.value.status == falcon.HTTP_422
    assert e.value.description == "This loyalty plan requires authorise fields to use this endpoint"


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_loyalty_card_add_and_auth_journey_return_existing_and_in_auth_in_progress(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    setup_loyalty_card: typing.Callable[..., tuple[SchemeAccount, SchemeAccountUserAssociation]],
    add_and_auth_account_data: dict,
) -> None:
    """Tests that existing loyalty card is returned when there is an existing (add and auth'ed) LoyaltyCard and link to
    this user (ADD_AND_AUTH)"""

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

    new_loyalty_card, _ = setup_loyalty_card(loyalty_plan, user, answers=True, card_number="9511143200133540455525")

    db_session.commit()

    created = loyalty_card_handler.handle_add_auth_card()

    assert not created
    assert loyalty_card_handler.card_id == new_loyalty_card.id
    assert mock_hermes_msg.called


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_loyalty_card_add_and_auth_auth_field_key_credential(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests an auth field that is also a key credential is not sent to hermes as an authorise_field
    (Harvey Nichols email). This is because the key credential should have already been saved and so
    hermes doesn't raise an error for providing the main answer in a link request. (ADD_AND_AUTH)"""

    answer_fields = {
        "authorise_fields": {
            "credentials": [
                {"credential_slug": "email", "value": "my_email@email.com"},
                {"credential_slug": "password", "value": "iLoveTests33"},
            ]
        },
    }

    loyalty_card_handler, loyalty_plan, _, channel, user = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, journey=ADD_AND_AUTHORISE, questions=False
    )
    LoyaltyPlanQuestionFactory(
        scheme_id=loyalty_plan.id,
        type="card_number",
        label="Card Number",
        add_field=True,
        third_party_identifier=True,
        order=0,
    )
    LoyaltyPlanQuestionFactory(
        scheme_id=loyalty_plan.id, type="email", label="Email", auth_field=True, manual_question=True, order=1
    )
    LoyaltyPlanQuestionFactory(scheme_id=loyalty_plan.id, type="password", label="Password", auth_field=True, order=2)

    db_session.commit()

    created = loyalty_card_handler.handle_add_auth_card()

    assert created
    assert mock_hermes_msg.called
    assert mock_hermes_msg.call_args.args[1]["authorise_fields"] == [
        {"credential_slug": "password", "value": "iLoveTests33"}
    ]


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_loyalty_card_add_and_auth_journey_link_to_existing_wallet_only(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    add_and_auth_account_data: dict,
) -> None:
    """Tests that user is successfully linked to existing loyalty card when there is an existing LoyaltyCard and
    no link to this user (ADD_AND_AUTH)"""
    set_vault_cache(to_load=["aes-keys"])

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=add_and_auth_account_data, journey=ADD_AND_AUTHORISE
    )

    card_number = add_and_auth_account_data["add_fields"]["credentials"][0]["value"]
    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number=card_number)

    other_user = UserFactory(client=channel.client_application)

    db_session.commit()

    LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=other_user.id,
        link_status=LoyaltyCardStatus.WALLET_ONLY,
    )

    db_session.commit()

    created = loyalty_card_handler.handle_add_auth_card()

    links = (
        db_session.query(SchemeAccountUserAssociation)
        .filter(
            SchemeAccountUserAssociation.scheme_account_id == new_loyalty_card.id,
            SchemeAccountUserAssociation.user_id == user.id,
        )
        .count()
    )

    assert links == 1
    assert mock_hermes_msg.called
    assert loyalty_card_handler.card_id == new_loyalty_card.id
    assert created
    assert mock_hermes_msg.call_args[0][0] == "loyalty_card_add_auth"
    sent_dict = mock_hermes_msg.call_args[0][1]
    assert sent_dict["loyalty_card_id"] == new_loyalty_card.id
    assert sent_dict["user_id"] == user.id


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_loyalty_card_add_and_auth_journey_link_to_existing_active(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    add_and_auth_account_data: dict,
) -> None:
    """Tests expected route when a user tries to add a card which already exists in another wallet and is ACTIVE
    (ADD_AND_AUTH)"""

    card_number = add_and_auth_account_data["add_fields"]["credentials"][0]["value"]

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=add_and_auth_account_data, journey=ADD_AND_AUTHORISE
    )

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number=card_number)

    other_user = UserFactory(client=channel.client_application)

    db_session.commit()

    LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=other_user.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )

    db_session.commit()

    created = loyalty_card_handler.handle_add_auth_card()

    links = (
        db_session.query(SchemeAccountUserAssociation)
        .filter(
            SchemeAccountUserAssociation.scheme_account_id == new_loyalty_card.id,
            SchemeAccountUserAssociation.user_id == user.id,
        )
        .count()
    )

    assert links == 1
    assert mock_hermes_msg.called
    assert loyalty_card_handler.card_id == new_loyalty_card.id
    assert created
    assert mock_hermes_msg.call_args[0][0] == "loyalty_card_add_auth"
    sent_dict = mock_hermes_msg.call_args[0][1]
    assert sent_dict["loyalty_card_id"] == new_loyalty_card.id
    assert sent_dict["user_id"] == user.id


# TODO: Verify if this is a good test case
# journey is ADD_AND_AUTHORISE but calls ADD handler function
@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_loyalty_card_add_and_auth_journey_auth_in_progress(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests expected route when a user tries to ADD a card which already exists in another wallet and is auth in
    progress"""

    answer_fields = {
        "add_fields": {"credentials": [{"credential_slug": "card_number", "value": "9511143200133540455525"}]},
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, journey=ADD_AND_AUTHORISE
    )

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525")

    other_user = UserFactory(client=channel.client_application)

    db_session.commit()

    LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=other_user.id,
        link_status=LoyaltyCardStatus.PENDING,
    )

    db_session.commit()

    created = loyalty_card_handler.handle_add_only_card()

    links = (
        db_session.query(SchemeAccountUserAssociation)
        .filter(
            SchemeAccountUserAssociation.scheme_account_id == new_loyalty_card.id,
            SchemeAccountUserAssociation.user_id == user.id,
        )
        .count()
    )

    assert links == 1
    assert mock_hermes_msg.called
    assert loyalty_card_handler.card_id == new_loyalty_card.id
    assert created


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_loyalty_card_add_and_auth_journey_auth_return_internal_error(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    add_and_auth_account_data: dict,
) -> None:
    """Tests expected route when a user tries to ADD a card which already exists in wallet and is auth is
    ACTIVE"""
    set_vault_cache(to_load=["aes-keys"])
    card_number = add_and_auth_account_data["add_fields"]["credentials"][0]["value"]

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=add_and_auth_account_data, journey=ADD_AND_AUTHORISE
    )

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number=card_number)

    db_session.commit()

    LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )

    db_session.commit()

    with pytest.raises(falcon.HTTPInternalServerError):
        loyalty_card_handler.handle_add_auth_card()


@patch("app.handlers.loyalty_card.LoyaltyCardHandler.check_auth_credentials_against_existing")
@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_loyalty_card_add_and_auth_auth_conflict(
    mock_hermes_msg: "MagicMock",
    mock_check_auth_cred: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    add_and_auth_account_data: dict,
) -> None:
    """Tests an auth field that is also a key credential is not sent to hermes as an authorise_field
    (Harvey Nichols email). This is because the key credential should have already been saved and so
    hermes doesn't raise an error for providing the main answer in a link request. (ADD_AND_AUTH)"""

    mock_check_auth_cred.return_value = (True, True)

    """Tests expected route when a user tries to ADD a card which already exists in wallet and is auth is
        ACTIVE"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=add_and_auth_account_data,
        journey=ADD_AND_AUTHORISE,
    )

    card_number = add_and_auth_account_data["add_fields"]["credentials"][0]["value"]
    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number=card_number)

    db_session.commit()

    LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )

    db_session.commit()

    with pytest.raises(falcon.HTTPConflict) as e:
        loyalty_card_handler.handle_add_auth_card()

    expected_title = (
        "Card already authorised. Use PUT /loyalty_cards/{loyalty_card_id}/authorise to modify "
        "authorisation credentials."
    )
    expected_code = "ALREADY_AUTHORISED"

    assert e.value.title == expected_title
    assert e.value.code == expected_code
    assert mock_hermes_msg.called is False


@pytest.mark.parametrize("password", ["password123", "non_matching_password"])
def test_loyalty_card_add_and_auth_auth_already_authorised(
    password: str,
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    add_and_auth_account_data: dict,
) -> None:
    """
    Tests add_and_auth raises an error when attempting to add_and_auth an already added card.
    This will raise an error if a card with the given key credential already exists in the wallet,
    regardless of whether the existing auth credentials match or not.
    """
    set_vault_cache(to_load=["aes-keys"])
    card_number = "663344667788"
    email = "some@email.com"
    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=add_and_auth_account_data,
        journey=ADD_AND_AUTHORISE,
        questions=False,
    )

    # Question setup
    card_number_q = LoyaltyPlanQuestionFactory(
        scheme_id=loyalty_plan.id,
        type="card_number",
        label="Card Number",
        add_field=True,
        manual_question=True,
        order=3,
    )
    password_q = LoyaltyPlanQuestionFactory(
        scheme_id=loyalty_plan.id, type="password", label="Password", auth_field=True, order=9
    )

    email_q = LoyaltyPlanQuestionFactory(
        scheme_id=loyalty_plan.id, type="email", label="Email", auth_field=True, order=6
    )

    # Card and answer setup
    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number=card_number)
    db_session.flush()

    association = LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    db_session.flush()

    encrypted_pass = AESCipher(AESKeyNames.LOCAL_AES_KEY).encrypt(password).decode("utf-8")
    LoyaltyCardAnswerFactory(scheme_account_entry_id=association.id, question_id=card_number_q.id, answer=card_number)
    LoyaltyCardAnswerFactory(scheme_account_entry_id=association.id, question_id=password_q.id, answer=encrypted_pass)
    LoyaltyCardAnswerFactory(scheme_account_entry_id=association.id, question_id=email_q.id, answer=email)

    db_session.commit()

    # Test
    with pytest.raises(falcon.HTTPConflict) as e:
        loyalty_card_handler.handle_add_auth_card()

    expected_title = (
        "Card already authorised. Use PUT /loyalty_cards/{loyalty_card_id}/authorise to modify "
        "authorisation credentials."
    )
    expected_code = "ALREADY_AUTHORISED"

    assert e.value.title == expected_title
    assert e.value.code == expected_code


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_loyalty_card_add_and_auth_auth_already_authorised_via_trusted_add(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    auth_req_data: dict,
    trusted_add_account_single_auth_field_data: dict,
) -> None:
    """
    Tests add_and_auth raises an error when attempting to add_and_auth a card which was already
    add via POST /trusted_add
    """

    email = "some@email.com"
    password = "Password01"

    # Trusted add
    trusted_add_account_single_auth_field_data["merchant_fields"] = {
        "merchant_identifier": trusted_add_account_single_auth_field_data["merchant_fields"]["account_id"]
    }
    loyalty_card_handler, _, questions, _, user = setup_loyalty_card_handler(
        journey=TRUSTED_ADD, all_answer_fields=trusted_add_account_single_auth_field_data
    )
    auth_questions = {question.type: question.id for question in questions if question.auth_field}
    loyalty_card_handler.key_credential = {
        "credential_question_id": auth_questions["email"],
        "credential_type": "email",
        "credential_class": CredentialClass.AUTH_FIELD,
        "key_credential": True,
        "credential_answer": email,
    }

    user_link_q = select(SchemeAccountUserAssociation).where(SchemeAccountUserAssociation.user_id == user.id)

    user_links_before = db_session.execute(user_link_q).all()

    loyalty_card_handler.handle_trusted_add_card()

    assert mock_hermes_msg.called is True
    assert mock_hermes_msg.call_count == 2
    assert mock_hermes_msg.call_args_list[0][0][0] == "loyalty_card_trusted_add"
    assert mock_hermes_msg.call_args_list[1][0][0] == "loyalty_card_trusted_add_success_event"

    user_links_after = db_session.execute(user_link_q).all()
    assert len(user_links_before) == 0
    assert len(user_links_after) == 1

    link = user_links_after[0].SchemeAccountUserAssociation
    assert link.link_status == LoyaltyCardStatus.ACTIVE
    assert link.authorised is True

    # add_and_auth
    set_vault_cache(to_load=["aes-keys"])
    loyalty_card_handler.journey = ADD_AND_AUTHORISE
    loyalty_card_handler.all_answer_fields = auth_req_data

    db_session.flush()

    encrypted_pass = AESCipher(AESKeyNames.LOCAL_AES_KEY).encrypt(password).decode("utf-8")
    LoyaltyCardAnswerFactory(
        scheme_account_entry_id=link.id,
        question_id=auth_questions["password"],
        answer=encrypted_pass,
    )
    LoyaltyCardAnswerFactory(
        scheme_account_entry_id=link.id,
        question_id=auth_questions["email"],
        answer=email,
    )

    db_session.commit()

    # Test
    with pytest.raises(falcon.HTTPConflict) as e:
        loyalty_card_handler.handle_add_auth_card()

    assert mock_hermes_msg.call_count == 2
    expected_title = (
        "Card already authorised. Use PUT /loyalty_cards/{loyalty_card_id}/authorise to modify "
        "authorisation credentials."
    )
    expected_code = "ALREADY_AUTHORISED"

    assert e.value.title == expected_title
    assert e.value.code == expected_code


# ----------------COMPLETE AUTHORISE JOURNEY------------------


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_handle_authorise_card(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """
    Tests happy path for authorise journey.
    Existing card is in WALLET_ONLY state and is only linked to current user. No saved auth creds.
    """
    set_vault_cache(to_load=["aes-keys"])
    card_number = "9511143200133540455525"
    answer_fields = {
        "add_fields": {
            "credentials": [
                {"credential_slug": "card_number", "value": card_number},
            ]
        },
        "authorise_fields": {
            "credentials": [
                {"credential_slug": "email", "value": "my_email@email.com"},
                {"credential_slug": "password", "value": "iLoveTests33"},
            ]
        },
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, consents=True, journey=ADD_AND_AUTHORISE
    )

    db_session.commit()

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number=card_number)

    db_session.commit()

    LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.WALLET_ONLY,
    )

    db_session.commit()

    loyalty_card_handler.card_id = new_loyalty_card.id

    loyalty_card_handler.handle_authorise_card()

    assert mock_hermes_msg.called is True
    assert mock_hermes_msg.call_args[0][0] == "loyalty_card_add_auth"
    sent_dict = mock_hermes_msg.call_args[0][1]
    assert sent_dict["loyalty_card_id"] == new_loyalty_card.id
    assert sent_dict["user_id"] == user.id
    assert sent_dict["channel_slug"] == "com.test.channel"
    assert sent_dict["authorise_fields"]


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_handle_authorise_card_unchanged_add_field_matching_creds_wallet_only(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """
    Tests authorising a card that is in WALLET_ONLY state and linked to another user.
    """
    set_vault_cache(to_load=["aes-keys"])
    card_number1 = "9511143200133540455525"
    email = "my_email@email.com"
    password = "iLoveTests33"
    answer_fields = {
        "add_fields": {
            "credentials": [
                {"credential_slug": "card_number", "value": card_number1},
            ]
        },
        "authorise_fields": {
            "credentials": [
                {"credential_slug": "email", "value": email},
                {"credential_slug": "password", "value": password},
            ]
        },
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, consents=True, journey=ADD_AND_AUTHORISE
    )
    db_session.commit()

    loyalty_card_to_update = LoyaltyCardFactory(scheme=loyalty_plan, card_number=card_number1)
    existing_user = UserFactory(client=channel.client_application)

    db_session.commit()

    LoyaltyCardUserAssociationFactory(
        scheme_account_id=loyalty_card_to_update.id,
        user_id=existing_user.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )

    LoyaltyCardUserAssociationFactory(
        scheme_account_id=loyalty_card_to_update.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.WALLET_ONLY,
    )

    db_session.commit()

    loyalty_card_handler.card_id = loyalty_card_to_update.id

    loyalty_card_handler.handle_authorise_card()

    assert mock_hermes_msg.called is True
    assert mock_hermes_msg.call_args[0][0] == "loyalty_card_add_auth"
    sent_dict = mock_hermes_msg.call_args[0][1]
    assert sent_dict["loyalty_card_id"] == loyalty_card_to_update.id
    assert sent_dict["user_id"] == user.id
    assert sent_dict["channel_slug"] == "com.test.channel"
    assert sent_dict["journey"] == ADD_AND_AUTHORISE
    assert sent_dict["authorise_fields"]


@patch.object(LoyaltyCardHandler, "_dispatch_outcome_event")
@patch.object(LoyaltyCardHandler, "_dispatch_request_event")
@patch("app.handlers.loyalty_card.LoyaltyCardHandler.check_auth_credentials_against_existing")
def test_handle_authorise_card_matching_existing_credentials_not_call_hermes_with_failed_outcome_evenet(
    mock_check_auth: "MagicMock",
    mock_request_event: "MagicMock",
    mock_outcome_event: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """
    Tests authorising a card has the same credentials as existing credentials.
    Also test failed outcome event
    """
    mock_check_auth.return_value = (True, True)

    set_vault_cache(to_load=["aes-keys"])
    card_number1 = "9511143200133540455525"
    email = "my_email@email.com"
    password = "iLoveTests33"
    answer_fields = {
        "add_fields": {
            "credentials": [
                {"credential_slug": "card_number", "value": card_number1},
            ]
        },
        "authorise_fields": {
            "credentials": [
                {"credential_slug": "email", "value": "wrong@email.com"},
                {"credential_slug": "password", "value": "DifferentPass1"},
            ]
        },
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, consents=True, journey=ADD_AND_AUTHORISE
    )
    db_session.commit()

    loyalty_card_to_update = LoyaltyCardFactory(scheme=loyalty_plan, card_number=card_number1)

    db_session.commit()

    association = LoyaltyCardUserAssociationFactory(
        scheme_account_id=loyalty_card_to_update.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.INVALID_CREDENTIALS,
    )

    auth_questions = {q.type: q.id for q in questions if q.auth_field}
    cipher = AESCipher(AESKeyNames.LOCAL_AES_KEY)

    LoyaltyCardAnswerFactory(
        question_id=auth_questions["email"],
        scheme_account_entry_id=association.id,
        answer=email,
    )
    LoyaltyCardAnswerFactory(
        question_id=auth_questions["password"],
        scheme_account_entry_id=association.id,
        answer=cipher.encrypt(password).decode(),
    )

    db_session.commit()

    loyalty_card_handler.card_id = loyalty_card_to_update.id

    sent_to_hermes = loyalty_card_handler.handle_authorise_card()

    assert mock_request_event.called
    assert mock_outcome_event.called
    # Call failed outcome_event because card is not in authorised state
    assert not mock_outcome_event.call_args_list[0][1]["success"]
    assert not sent_to_hermes


@patch.object(LoyaltyCardHandler, "_dispatch_outcome_event")
@patch.object(LoyaltyCardHandler, "_dispatch_request_event")
@patch("app.handlers.loyalty_card.LoyaltyCardHandler.check_auth_credentials_against_existing")
def test_handle_authorise_card_matching_existing_credentials_not_call_hermes_with_success_outcome_evenet(
    mock_check_auth: "MagicMock",
    mock_request_event: "MagicMock",
    mock_outcome_event: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """
    Tests authorising a card has the same credentials as existing credentials.
    Also test success outcome event
    """
    mock_check_auth.return_value = (True, True)

    set_vault_cache(to_load=["aes-keys"])
    card_number1 = "9511143200133540455525"
    email = "my_email@email.com"
    password = "iLoveTests33"
    answer_fields = {
        "add_fields": {
            "credentials": [
                {"credential_slug": "card_number", "value": card_number1},
            ]
        },
        "authorise_fields": {
            "credentials": [
                {"credential_slug": "email", "value": "wrong@email.com"},
                {"credential_slug": "password", "value": "DifferentPass1"},
            ]
        },
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, consents=True, journey=ADD_AND_AUTHORISE
    )
    db_session.commit()

    loyalty_card_to_update = LoyaltyCardFactory(scheme=loyalty_plan, card_number=card_number1)

    db_session.commit()

    association = LoyaltyCardUserAssociationFactory(
        scheme_account_id=loyalty_card_to_update.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )

    auth_questions = {q.type: q.id for q in questions if q.auth_field}
    cipher = AESCipher(AESKeyNames.LOCAL_AES_KEY)

    LoyaltyCardAnswerFactory(
        question_id=auth_questions["email"],
        scheme_account_entry_id=association.id,
        answer=email,
    )
    LoyaltyCardAnswerFactory(
        question_id=auth_questions["password"],
        scheme_account_entry_id=association.id,
        answer=cipher.encrypt(password).decode(),
    )

    db_session.commit()

    loyalty_card_handler.card_id = loyalty_card_to_update.id

    sent_to_hermes = loyalty_card_handler.handle_authorise_card()

    assert mock_request_event.called
    assert mock_outcome_event.called
    # Call success outcome_event because card is not in authorised state
    assert mock_outcome_event.call_args_list[0][1]["success"]
    assert not sent_to_hermes


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_handle_authorise_card_unchanged_add_field_different_creds(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """
    Tests authorising a card that is not in WALLET_ONLY state where the given credentials do not match those existing.
    """
    set_vault_cache(to_load=["aes-keys"])
    card_number1 = "9511143200133540455525"
    email = "my_email@email.com"
    password = "iLoveTests33"
    answer_fields = {
        "add_fields": {
            "credentials": [
                {"credential_slug": "card_number", "value": card_number1},
            ]
        },
        "authorise_fields": {
            "credentials": [
                {"credential_slug": "email", "value": "wrong@email.com"},
                {"credential_slug": "password", "value": "DifferentPass1"},
            ]
        },
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, consents=True, journey=ADD_AND_AUTHORISE
    )
    db_session.commit()

    loyalty_card_to_update = LoyaltyCardFactory(scheme=loyalty_plan, card_number=card_number1)

    existing_user = UserFactory(client=channel.client_application)

    db_session.commit()

    association1 = LoyaltyCardUserAssociationFactory(
        scheme_account_id=loyalty_card_to_update.id,
        user_id=existing_user.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    association2 = LoyaltyCardUserAssociationFactory(
        scheme_account_id=loyalty_card_to_update.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.WALLET_ONLY,
    )

    auth_questions = {q.type: q.id for q in questions if q.auth_field}
    cipher = AESCipher(AESKeyNames.LOCAL_AES_KEY)

    LoyaltyCardAnswerFactory(
        question_id=auth_questions["email"],
        scheme_account_entry_id=association1.id,
        answer=email,
    )
    LoyaltyCardAnswerFactory(
        question_id=auth_questions["password"],
        scheme_account_entry_id=association1.id,
        answer=cipher.encrypt(password).decode(),
    )

    LoyaltyCardAnswerFactory(
        question_id=auth_questions["email"],
        scheme_account_entry_id=association2.id,
        answer=email,
    )
    LoyaltyCardAnswerFactory(
        question_id=auth_questions["password"],
        scheme_account_entry_id=association2.id,
        answer=cipher.encrypt(password).decode(),
    )

    db_session.commit()

    loyalty_card_handler.card_id = loyalty_card_to_update.id

    sent_to_hermes = loyalty_card_handler.handle_authorise_card()

    assert sent_to_hermes
    assert mock_hermes_msg.called is True
    assert mock_hermes_msg.call_args[0][0] == "loyalty_card_add_auth"
    sent_dict = mock_hermes_msg.call_args[0][1]
    assert sent_dict["loyalty_card_id"] == loyalty_card_to_update.id
    assert sent_dict["user_id"] == user.id
    assert sent_dict["channel_slug"] == "com.test.channel"
    assert sent_dict["authorise_fields"]


##########################################


@patch.object(LoyaltyCardHandler, "_dispatch_request_event")
@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_handle_authorise_card_updated_add_field_creates_new_acc(
    mock_hermes_msg: "MagicMock",
    mock_request_event: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """
    Tests authorise where the add field provided is different to that of the account in the URI.
    This should create a new account.
    """
    set_vault_cache(to_load=["aes-keys"])
    card_number1 = "9511143200133540455525"
    card_number2 = "9511143200133540466666"
    answer_fields = {
        "add_fields": {
            "credentials": [
                {"credential_slug": "card_number", "value": card_number2},
            ]
        },
        "authorise_fields": {
            "credentials": [
                {"credential_slug": "email", "value": "my_email@email.com"},
                {"credential_slug": "password", "value": "iLoveTests33"},
            ]
        },
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, consents=True, journey=ADD_AND_AUTHORISE
    )
    db_session.commit()

    loyalty_card_to_update = LoyaltyCardFactory(scheme=loyalty_plan, card_number=card_number1)
    db_session.commit()

    LoyaltyCardUserAssociationFactory(
        scheme_account_id=loyalty_card_to_update.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.WALLET_ONLY,
    )
    db_session.commit()

    loyalty_card_handler.card_id = loyalty_card_to_update.id

    loyalty_card_handler.handle_authorise_card()

    user_associations = db_session.execute(
        select(SchemeAccountUserAssociation).where(SchemeAccountUserAssociation.user_id == user.id)
    ).all()
    assert len(user_associations) == 2
    new_acc_id = next(
        row.SchemeAccountUserAssociation.scheme_account_id
        for row in user_associations
        if row.SchemeAccountUserAssociation.scheme_account_id != loyalty_card_to_update.id
    )
    assert mock_hermes_msg.called is True
    assert mock_hermes_msg.call_count == 2
    assert mock_request_event.called
    delete_call = mock_hermes_msg.call_args_list[0]
    add_auth_call = mock_hermes_msg.call_args_list[1]

    assert delete_call.args[0] == "delete_loyalty_card"
    assert loyalty_plan.id == delete_call.args[1]["loyalty_plan_id"]
    assert loyalty_card_to_update.id == delete_call.args[1]["loyalty_card_id"]
    assert user.id == delete_call.args[1]["user_id"]
    assert delete_call.args[1]["channel_slug"] == "com.test.channel"
    assert delete_call.args[1]["journey"] == DELETE

    assert add_auth_call.args[0] == "loyalty_card_add_auth"
    assert new_acc_id == add_auth_call.args[1]["loyalty_card_id"]
    assert user.id == add_auth_call.args[1]["user_id"]
    assert add_auth_call.args[1]["channel_slug"] == "com.test.channel"
    assert add_auth_call.args[1]["authorise_fields"]
    assert add_auth_call.args[1]["journey"] == ADD_AND_AUTHORISE


# ----------------COMPLETE ADD and REGISTER JOURNEY------------------


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_handle_add_and_register_card_created_and_linked(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that user is successfully linked to a newly created Scheme Account (ADD_AND_REGISTER)"""

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

    # adding an optional credential question to check that not providing an answer for it still result in success.
    LoyaltyPlanQuestionFactory(
        type="random",
        label="Random",
        scheme_id=loyalty_plan.id,
        is_optional=True,
        register_field=True,
        enrol_field=True,
    )
    db_session.commit()

    loyalty_card_handler.handle_add_register_card()

    cards = (
        db_session.query(SchemeAccount)
        .filter(
            SchemeAccount.id == loyalty_card_handler.card_id,
        )
        .all()
    )

    links = (
        db_session.query(SchemeAccountUserAssociation)
        .filter(
            SchemeAccountUserAssociation.scheme_account_id == loyalty_card_handler.card_id,
            SchemeAccountUserAssociation.user_id == user.id,
        )
        .count()
    )

    assert links == 1
    assert len(cards) == 1
    assert cards[0].originating_journey == OriginatingJourney.REGISTER
    assert mock_hermes_msg.called is True
    assert mock_hermes_msg.call_args[0][0] == "loyalty_card_add_and_register"
    sent_dict = mock_hermes_msg.call_args[0][1]
    assert sent_dict["loyalty_card_id"] == loyalty_card_handler.card_id
    assert sent_dict["user_id"] == user.id
    assert sent_dict["channel_slug"] == "com.test.channel"
    assert sent_dict["register_fields"]


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_handle_add_and_register_card_already_added_and_not_active(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that user is successfully linked to existing loyalty card when there is an existing LoyaltyCard in another
    wallet (ADD_AND_REGISTER)"""

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

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525")

    db_session.commit()

    LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.PENDING,
    )

    db_session.commit()

    with pytest.raises(falcon.HTTPConflict) as e:
        loyalty_card_handler.handle_add_register_card()

    expected_title = "Card already added. Use PUT /loyalty_cards/{loyalty_card_id}/register to register this card."
    expected_code = "ALREADY_ADDED"

    assert e.value.title == expected_title
    assert e.value.code == expected_code
    assert not mock_hermes_msg.called


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_handle_add_and_register_when_already_added_and_active(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that user is successfully linked to existing loyalty card when there is an existing LoyaltyCard in another
    wallet (ADD_AND_REGISTER)"""

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

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525")

    db_session.commit()

    LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )

    db_session.commit()

    with pytest.raises(falcon.HTTPConflict) as e:
        loyalty_card_handler.handle_add_register_card()

    expected_code = "ALREADY_REGISTERED"
    expected_title = (
        "Card is already registered. " "Use POST /loyalty_cards/add_and_authorise to add this card to your wallet."
    )

    assert e.value.title == expected_title
    assert e.value.code == expected_code
    assert not mock_hermes_msg.called


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_handle_add_and_register_card_existing_registration_in_other_wallet(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that user is successfully linked to existing loyalty card when there is an existing LoyaltyCard in another
    wallet (ADD_AND_REGISTER)"""

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

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525")

    other_user = UserFactory(client=channel.client_application)

    db_session.commit()

    LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=other_user.id,
        link_status=LoyaltyCardStatus.REGISTRATION_ASYNC_IN_PROGRESS,
    )

    db_session.commit()

    created = loyalty_card_handler.handle_add_register_card()

    assert mock_hermes_msg.called
    assert created


# ----------------COMPLETE REGISTER JOURNEY------------------


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_handle_register_card(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests happy path for register journey"""

    answer_fields = {
        "register_ghost_card_fields": {
            "credentials": [
                {"credential_slug": "postcode", "value": "007"},
            ],
            "consents": [
                {"consent_slug": "Consent_1", "value": "consent_value"},
            ],
        },
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, consents=True, journey=REGISTER
    )

    db_session.commit()

    # adding an optional credential question to check that not providing an answer for it still result in success.
    LoyaltyPlanQuestionFactory(
        type="random",
        label="Random",
        scheme_id=loyalty_plan.id,
        is_optional=True,
        register_field=True,
        enrol_field=True,
    )

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525")

    db_session.commit()

    user_asc = LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.WALLET_ONLY,
    )

    db_session.commit()

    loyalty_card_handler.link_to_user = user_asc
    loyalty_card_handler.card_id = new_loyalty_card.id

    loyalty_card_handler.handle_update_register_card()

    assert mock_hermes_msg.called is True
    assert mock_hermes_msg.call_args[0][0] == "loyalty_card_register"
    sent_dict = mock_hermes_msg.call_args[0][1]
    assert sent_dict["loyalty_card_id"] == new_loyalty_card.id
    assert sent_dict["user_id"] == user.id
    assert sent_dict["channel_slug"] == "com.test.channel"
    assert sent_dict["register_fields"]


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_handle_register_card_return_existing_process(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests happy path for register journey"""

    answer_fields = {
        "register_ghost_card_fields": {
            "credentials": [
                {"credential_slug": "postcode", "value": "007"},
            ],
            "consents": [
                {"consent_slug": "Consent_1", "value": "consent_value"},
            ],
        },
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, consents=True, journey=REGISTER
    )

    db_session.commit()

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525")

    db_session.commit()

    user_asc = LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.REGISTRATION_ASYNC_IN_PROGRESS,
    )

    db_session.commit()

    loyalty_card_handler.link_to_user = user_asc
    loyalty_card_handler.card_id = new_loyalty_card.id

    loyalty_card_handler.handle_update_register_card()

    assert mock_hermes_msg.called is False


# ----------------COMPLETE JOIN JOURNEY------------------


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_handle_join_card(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that user is successfully linked to a newly created Scheme Account (JOIN)"""

    answer_fields = {
        "join_fields": {
            "credentials": [
                {"credential_slug": "postcode", "value": "007"},
                {"credential_slug": "last_name", "value": "Bond"},
            ],
            "consents": [
                {"consent_slug": "Consent_2", "value": "GU554JG"},
            ],
        },
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, consents=True, journey=JOIN
    )

    # adding an optional credential question to check that not providing an answer for it still result in success.
    LoyaltyPlanQuestionFactory(
        type="random",
        label="Random",
        scheme_id=loyalty_plan.id,
        is_optional=True,
        register_field=True,
        enrol_field=True,
    )

    db_session.commit()

    loyalty_card_handler.handle_join_card()

    cards = (
        db_session.query(SchemeAccount)
        .filter(
            SchemeAccount.id == loyalty_card_handler.card_id,
        )
        .all()
    )

    links = (
        db_session.query(SchemeAccountUserAssociation)
        .filter(
            SchemeAccountUserAssociation.scheme_account_id == loyalty_card_handler.card_id,
            SchemeAccountUserAssociation.user_id == user.id,
        )
        .count()
    )

    assert links == 1
    assert len(cards) == 1
    assert cards[0].originating_journey == OriginatingJourney.JOIN
    assert mock_hermes_msg.called is True
    assert mock_hermes_msg.call_args[0][0] == "loyalty_card_join"
    sent_dict = mock_hermes_msg.call_args[0][1]
    assert sent_dict["loyalty_card_id"] == loyalty_card_handler.card_id
    assert sent_dict["user_id"] == user.id
    assert sent_dict["channel_slug"] == "com.test.channel"
    assert sent_dict["join_fields"]


# ----------------COMPLETE UPDATE FAILED JOIN JOURNEY------------------


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_put_join(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that an update on a failed join journey is successfully concluded in Angelia"""

    answer_fields = {
        "join_fields": {
            "credentials": [
                {"credential_slug": "postcode", "value": "007"},
                {"credential_slug": "last_name", "value": "Bond"},
            ],
            "consents": [
                {"consent_slug": "Consent_2", "value": "GU554JG"},
            ],
        },
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, consents=True, journey=JOIN
    )
    # adding an optional credential question to check that not providing an answer for it still result in success.
    LoyaltyPlanQuestionFactory(
        type="random",
        label="Random",
        scheme_id=loyalty_plan.id,
        is_optional=True,
        register_field=True,
        enrol_field=True,
    )

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525")
    db_session.commit()

    user_asc = LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.JOIN_ERROR,
    )
    db_session.commit()

    loyalty_card_handler.card_id = new_loyalty_card.id
    loyalty_card_handler.link_to_user = user_asc
    loyalty_card_handler.handle_put_join()

    cards = (
        db_session.query(SchemeAccountUserAssociation)
        .filter(
            SchemeAccountUserAssociation.scheme_account_id == loyalty_card_handler.card_id,
            SchemeAccountUserAssociation.user_id == user.id,
        )
        .all()
    )
    # needs to link in the user ascoc table here....
    # To Do
    assert cards[0].link_status == LoyaltyCardStatus.JOIN_ASYNC_IN_PROGRESS
    assert mock_hermes_msg.called is True
    assert mock_hermes_msg.call_args[0][0] == "loyalty_card_join"


def test_put_join_in_pending_state(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that an update on a failed join journey fails when card is in a Join Pending state"""

    answer_fields = {
        "join_fields": {
            "credentials": [
                {"credential_slug": "postcode", "value": "007"},
                {"credential_slug": "last_name", "value": "Bond"},
            ],
            "consents": [
                {"consent_slug": "Consent_2", "value": "GU554JG"},
            ],
        },
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, consents=True, journey=JOIN
    )

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525")
    db_session.commit()

    user_asc = LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.JOIN_ASYNC_IN_PROGRESS,
    )
    db_session.commit()

    loyalty_card_handler.link_to_user = user_asc
    loyalty_card_handler.card_id = new_loyalty_card.id
    with pytest.raises(falcon.HTTPConflict):
        loyalty_card_handler.handle_put_join()


def test_put_join_in_non_failed_state(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that an update on a failed join journey fails when card is in an Active state"""

    answer_fields = {
        "join_fields": {
            "credentials": [
                {"credential_slug": "postcode", "value": "007"},
                {"credential_slug": "last_name", "value": "Bond"},
            ],
            "consents": [
                {"consent_slug": "Consent_2", "value": "GU554JG"},
            ],
        },
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        all_answer_fields=answer_fields, consents=True, journey=JOIN
    )

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525")
    db_session.commit()

    user_asc = LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id, user_id=user.id, link_status=LoyaltyCardStatus.ACTIVE
    )
    db_session.commit()

    loyalty_card_handler.link_to_user = user_asc
    loyalty_card_handler.card_id = new_loyalty_card.id
    with pytest.raises(falcon.HTTPConflict):
        loyalty_card_handler.handle_put_join()


# ----------------COMPLETE DELETE JOURNEY------------------


def test_delete_join(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Test that a delete join journey is successfully concluded in Angelia"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()
    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525")
    db_session.commit()

    user_asc = LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.JOIN_ERROR,
    )
    db_session.commit()

    loyalty_card_handler.link_to_user = user_asc
    loyalty_card_handler.card_id = new_loyalty_card.id
    loyalty_card_handler.handle_delete_join()

    updated_scheme_account = db_session.query(SchemeAccount).filter(SchemeAccount.id == new_loyalty_card.id).all()
    links = (
        db_session.query(SchemeAccountUserAssociation)
        .filter(
            SchemeAccountUserAssociation.scheme_account_id == new_loyalty_card.id,
            SchemeAccountUserAssociation.scheme_account_id == user.id,
        )
        .count()
    )

    assert updated_scheme_account[0].is_deleted
    assert links == 0


def test_delete_join_not_in_failed_status(
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Test return 409 if status not in the list of failed joined statuses"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()
    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525")
    db_session.commit()

    user_asc = LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id, user_id=user.id, link_status=LoyaltyCardStatus.ACTIVE
    )
    db_session.commit()

    loyalty_card_handler.link_to_user = user_asc
    loyalty_card_handler.card_id = new_loyalty_card.id

    with pytest.raises(falcon.HTTPConflict):
        loyalty_card_handler.handle_delete_join()


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_handle_delete_card(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that a delete card journey is successfully concluded in Angelia"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525")
    db_session.commit()

    entry = LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.WALLET_ONLY,
    )
    db_session.commit()

    loyalty_card_handler.card_id = new_loyalty_card.id
    loyalty_card_handler.link_to_user = entry
    loyalty_card_handler.handle_delete_card()

    assert mock_hermes_msg.called is True
    assert mock_hermes_msg.call_args[0][0] == "delete_loyalty_card"
    sent_dict = mock_hermes_msg.call_args[0][1]
    assert sent_dict["loyalty_card_id"] == new_loyalty_card.id
    assert sent_dict["user_id"] == user.id
    assert sent_dict["channel_slug"] == "com.test.channel"


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_delete_error_join_in_progress(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
) -> None:
    """Tests that a delete card journey raises an error if the requested scheme_account is async_join_in_progress"""

    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler()

    new_loyalty_card = LoyaltyCardFactory(scheme=loyalty_plan, card_number="9511143200133540455525")

    db_session.commit()

    user_asc = LoyaltyCardUserAssociationFactory(
        scheme_account_id=new_loyalty_card.id,
        user_id=user.id,
        link_status=LoyaltyCardStatus.JOIN_ASYNC_IN_PROGRESS,
    )

    db_session.commit()

    loyalty_card_handler.link_to_user = user_asc
    loyalty_card_handler.card_id = new_loyalty_card.id

    with pytest.raises(falcon.HTTPConflict):
        loyalty_card_handler.handle_delete_card()


@pytest.fixture
def trusted_add_answer_fields(trusted_add_req_data: dict) -> None:
    """The account_id field in the request data is converted by the serializer into merchant_identifier.
    Since the data isn't serialized for these tests we need to do the conversion for the handler to process
    correctly.
    """
    answer_fields = trusted_add_req_data["account"]
    answer_fields["merchant_fields"] = {"merchant_identifier": answer_fields["merchant_fields"]["account_id"]}

    return answer_fields


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_trusted_add_success(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    trusted_add_answer_fields: dict,
) -> None:
    loyalty_card_handler, loyalty_plan, questions, channel, user = setup_loyalty_card_handler(
        journey=TRUSTED_ADD, all_answer_fields=trusted_add_answer_fields
    )

    loyalty_card_count_q = select(func.count(SchemeAccount.id))
    user_link_q = select(SchemeAccountUserAssociation).where(SchemeAccountUserAssociation.user_id == user.id)

    loyalty_card_count_before = db_session.scalar(loyalty_card_count_q)
    user_links_before = db_session.execute(user_link_q).all()

    loyalty_card_handler.handle_trusted_add_card()

    loyalty_card_count_after = db_session.scalar(loyalty_card_count_q)
    user_links_after = db_session.execute(user_link_q).all()
    assert mock_hermes_msg.called
    assert loyalty_card_count_before == 0
    assert len(user_links_before) == 0
    assert loyalty_card_count_after == 1
    assert len(user_links_after) == 1

    link = user_links_after[0].SchemeAccountUserAssociation
    loyalty_card = link.scheme_account
    assert link.link_status == LoyaltyCardStatus.ACTIVE
    assert trusted_add_answer_fields["merchant_fields"]["merchant_identifier"] == loyalty_card.merchant_identifier
    assert loyalty_card.originating_journey == OriginatingJourney.ADD
    assert loyalty_card.link_date
    assert mock_hermes_msg.call_args_list[1][0][0] == "loyalty_card_trusted_add_success_event"


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_trusted_add_existing_matching_credentials(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    trusted_add_answer_fields: dict,
) -> None:
    card_number = ("9511143200133540455525",)
    merchant_identifier = "12e34r3edvcsd"

    loyalty_card_handler, loyalty_plan, questions, channel, user1 = setup_loyalty_card_handler(
        journey=TRUSTED_ADD, all_answer_fields=trusted_add_answer_fields
    )

    user2 = UserFactory(client=channel.client_application)
    existing_card = LoyaltyCardFactory(
        scheme=loyalty_plan, card_number=card_number, merchant_identifier=merchant_identifier
    )
    db_session.flush()

    association1 = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card.id,
        user_id=user2.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    db_session.flush()

    question_id = next(q.id for q in questions if q.third_party_identifier)
    LoyaltyCardAnswerFactory(
        question_id=question_id,
        scheme_account_entry_id=association1.id,
        answer=merchant_identifier,
    )
    db_session.commit()

    user_link_q = select(SchemeAccountUserAssociation).where(SchemeAccountUserAssociation.user_id == user1.id)
    user_links_before = db_session.execute(user_link_q).all()

    loyalty_card_handler.handle_trusted_add_card()

    user_links_after = db_session.execute(user_link_q).all()
    assert mock_hermes_msg.called
    assert len(user_links_before) == 0
    assert len(user_links_after) == 1
    assert user_links_after[0].SchemeAccountUserAssociation.link_status == LoyaltyCardStatus.ACTIVE


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_trusted_add_same_wallet_existing_matching_credentials_sets_active(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    trusted_add_answer_fields: dict,
) -> None:
    """
    Tests scenario where a user adds a card via non-trusted means and then via trusted_add.
    This should set the card to active and save the merchant identifier if the account was in pending state
    """
    card_number = ("9511143200133540455525",)
    merchant_identifier = "12e34r3edvcsd"

    loyalty_card_handler, loyalty_plan, questions, channel, user1 = setup_loyalty_card_handler(
        journey=TRUSTED_ADD, all_answer_fields=trusted_add_answer_fields
    )

    existing_card = LoyaltyCardFactory(
        scheme=loyalty_plan, card_number=card_number, merchant_identifier=merchant_identifier
    )
    db_session.flush()

    LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card.id,
        user_id=user1.id,
        link_status=LoyaltyCardStatus.PENDING,
    )

    db_session.commit()

    user_link_q = select(SchemeAccountUserAssociation).where(SchemeAccountUserAssociation.user_id == user1.id)
    user_links_before = db_session.execute(user_link_q).all()

    loyalty_card_handler.handle_trusted_add_card()

    user_links_after = db_session.execute(user_link_q).all()
    assert mock_hermes_msg.called
    assert len(user_links_before) == 1
    assert len(user_links_after) == 1
    assert user_links_after[0].SchemeAccountUserAssociation.link_status == LoyaltyCardStatus.ACTIVE


TEST_DATE = arrow.get("2022-12-12").isoformat()


@pytest.mark.parametrize(
    "link_date,join_date", [(None, None), (TEST_DATE, None), (None, TEST_DATE), (TEST_DATE, TEST_DATE)]
)
@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_trusted_add_same_wallet_existing_matching_credentials_sets_link_date(
    mock_hermes_msg: "MagicMock",
    link_date: str | None,
    join_date: str | None,
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    trusted_add_answer_fields: dict,
) -> None:
    """
    Tests that link_date is set when a user has an unauthorised card via non-trusted means and then the card is
    added via trusted_add.
    """
    card_number = ("9511143200133540455525",)
    merchant_identifier = "12e34r3edvcsd"

    loyalty_card_handler, loyalty_plan, questions, channel, user1 = setup_loyalty_card_handler(
        journey=TRUSTED_ADD, all_answer_fields=trusted_add_answer_fields
    )

    existing_card = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number=card_number,
        merchant_identifier=merchant_identifier,
        link_date=link_date,
        join_date=join_date,
    )
    db_session.flush()

    LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card.id,
        user_id=user1.id,
        link_status=LoyaltyCardStatus.PENDING,
    )

    db_session.commit()

    loyalty_card_handler.handle_trusted_add_card()

    assert mock_hermes_msg.called

    db_session.refresh(existing_card)
    if not (link_date or join_date):
        assert existing_card.link_date
    elif join_date and not link_date:
        assert existing_card.join_date == arrow.get(TEST_DATE).datetime
        assert not existing_card.link_date
    elif link_date and not join_date:
        assert existing_card.link_date == arrow.get(TEST_DATE).datetime
        assert not existing_card.join_date
    else:
        # not likely to happen where both join_date and link_date are populated
        # but nothing should be updated in this scenario
        assert existing_card.join_date == arrow.get(TEST_DATE).datetime
        assert existing_card.link_date == arrow.get(TEST_DATE).datetime


@pytest.mark.parametrize("credential", ["merchant_identifier", "card_number"])
@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_trusted_add_existing_non_matching_credentials(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    trusted_add_answer_fields: dict,
    credential: str,
) -> None:
    credentials = {
        "card_number": trusted_add_answer_fields["add_fields"]["credentials"][0]["value"],
        "merchant_identifier": trusted_add_answer_fields["merchant_fields"]["merchant_identifier"],
    }
    credentials.update({credential: "111111111111"})

    loyalty_card_handler, loyalty_plan, questions, channel, user1 = setup_loyalty_card_handler(
        journey=TRUSTED_ADD, all_answer_fields=trusted_add_answer_fields
    )

    user2 = UserFactory(client=channel.client_application)
    existing_card = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number=credentials["card_number"],
        merchant_identifier=credentials["merchant_identifier"],
    )
    db_session.flush()

    association1 = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card.id,
        user_id=user2.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    db_session.flush()

    question_id = next(q.id for q in questions if q.third_party_identifier)
    LoyaltyCardAnswerFactory(
        question_id=question_id,
        scheme_account_entry_id=association1.id,
        answer=credentials["merchant_identifier"],
    )
    db_session.commit()

    user_link_q = select(SchemeAccountUserAssociation).where(SchemeAccountUserAssociation.user_id == user1.id)

    with pytest.raises(falcon.HTTPConflict) as e:
        loyalty_card_handler.handle_trusted_add_card()

    err_resp = {
        "card_number": "A loyalty card with this account_id has already been added in a wallet, "
        "but the key credential does not match.",
        "merchant_identifier": "A loyalty card with this key credential has already been added "
        "in a wallet, but the account_id does not match.",
    }
    assert e.value.title == err_resp[credential]
    assert e.value.code == "CONFLICT"

    user_links = db_session.execute(user_link_q).all()
    assert not mock_hermes_msg.called
    assert len(user_links) == 0


@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_trusted_add_multi_wallet_existing_key_cred_matching_credentials(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    trusted_add_account_single_auth_field_data: dict,
) -> None:
    """
    This test replicates Squaremeal-type schemes which use an auth field to add a card and also have
    the merchant return a card number. This leads to having both card_number and alt_main_answer
    populated on the scheme account. The test ensures that validation is done against the correct field
    when checking the unique-together-ness of the key credential(email) and merchant_identifier.
    """
    credentials = {"email": "differentemail@bink.com", "merchant_identifier": "12e34r3edvcsd"}

    trusted_add_account_single_auth_field_data["merchant_fields"] = {
        "merchant_identifier": trusted_add_account_single_auth_field_data["merchant_fields"]["account_id"]
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user1 = setup_loyalty_card_handler(
        journey=TRUSTED_ADD,
        all_answer_fields=trusted_add_account_single_auth_field_data,
        questions=False,
    )

    questions = [
        LoyaltyPlanQuestionFactory(
            id=1,
            scheme_id=loyalty_plan.id,
            type="card_number",
            label="Card Number",
            add_field=False,
            manual_question=False,
        ),
        LoyaltyPlanQuestionFactory(
            id=3,
            scheme_id=loyalty_plan.id,
            type="email",
            label="Email",
            auth_field=True,
            manual_question=True,
        ),
        LoyaltyPlanQuestionFactory(id=4, scheme_id=loyalty_plan.id, type="password", label="Password", auth_field=True),
        LoyaltyPlanQuestionFactory(
            id=7,
            scheme_id=loyalty_plan.id,
            type="merchant_identifier",
            label="Merchant Identifier",
            third_party_identifier=True,
            options=7,
        ),
    ]

    user2 = UserFactory(client=channel.client_application)
    existing_card = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number="111111111111",
        merchant_identifier=credentials["merchant_identifier"],
        alt_main_answer="someemail@bink.com",
    )
    db_session.flush()

    association1 = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card.id,
        user_id=user2.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    db_session.flush()

    question_id = next(q.id for q in questions if q.third_party_identifier)
    LoyaltyCardAnswerFactory(
        question_id=question_id,
        scheme_account_entry_id=association1.id,
        answer=credentials["merchant_identifier"],
    )
    db_session.commit()

    user_link_q = select(SchemeAccountUserAssociation).where(SchemeAccountUserAssociation.user_id == user1.id)
    user_links_before = db_session.execute(user_link_q).all()

    loyalty_card_handler.handle_trusted_add_card()

    user_links_after = db_session.execute(user_link_q).all()
    assert mock_hermes_msg.called
    assert len(user_links_before) == 0
    assert len(user_links_after) == 1
    assert user_links_after[0].SchemeAccountUserAssociation.link_status == LoyaltyCardStatus.ACTIVE


@pytest.mark.parametrize("credential", ["merchant_identifier", "email"])
@patch("app.handlers.loyalty_card.send_message_to_hermes")
def test_trusted_add_multi_wallet_existing_key_cred_non_matching_credentials(
    mock_hermes_msg: "MagicMock",
    db_session: "Session",
    setup_loyalty_card_handler: typing.Callable[
        ...,
        tuple[LoyaltyCardHandler, Scheme, list[SchemeCredentialQuestion], Channel, User],
    ],
    trusted_add_account_single_auth_field_data: dict,
    credential: str,
) -> None:
    """
    This test replicates Squaremeal-type schemes which use an auth field to add a card and also have
    the merchant return a card number. This leads to having both card_number and alt_main_answer
    populated on the scheme account. The test ensures that validation is done against the correct field
    when checking the unique-together-ness of the key credential(email) and merchant_identifier.
    """
    credentials = {"email": "someemail@bink.com", "merchant_identifier": "12e34r3edvcsd"}
    credentials.update({credential: "111111111111"})

    trusted_add_account_single_auth_field_data["merchant_fields"] = {
        "merchant_identifier": trusted_add_account_single_auth_field_data["merchant_fields"]["account_id"]
    }

    loyalty_card_handler, loyalty_plan, questions, channel, user1 = setup_loyalty_card_handler(
        journey=TRUSTED_ADD,
        all_answer_fields=trusted_add_account_single_auth_field_data,
        questions=False,
    )

    questions = [
        LoyaltyPlanQuestionFactory(
            id=1,
            scheme_id=loyalty_plan.id,
            type="card_number",
            label="Card Number",
            add_field=False,
            manual_question=False,
        ),
        LoyaltyPlanQuestionFactory(
            id=3,
            scheme_id=loyalty_plan.id,
            type="email",
            label="Email",
            auth_field=True,
            manual_question=True,
        ),
        LoyaltyPlanQuestionFactory(id=4, scheme_id=loyalty_plan.id, type="password", label="Password", auth_field=True),
        LoyaltyPlanQuestionFactory(
            id=7,
            scheme_id=loyalty_plan.id,
            type="merchant_identifier",
            label="Merchant Identifier",
            third_party_identifier=True,
            options=7,
        ),
    ]

    user2 = UserFactory(client=channel.client_application)
    existing_card = LoyaltyCardFactory(
        scheme=loyalty_plan,
        card_number="111111111111",
        merchant_identifier=credentials["merchant_identifier"],
        alt_main_answer=credentials["email"],
    )
    db_session.flush()

    association1 = LoyaltyCardUserAssociationFactory(
        scheme_account_id=existing_card.id,
        user_id=user2.id,
        link_status=LoyaltyCardStatus.ACTIVE,
    )
    db_session.flush()

    question_id = next(q.id for q in questions if q.third_party_identifier)
    LoyaltyCardAnswerFactory(
        question_id=question_id,
        scheme_account_entry_id=association1.id,
        answer=credentials["merchant_identifier"],
    )
    db_session.commit()

    user_link_q = select(SchemeAccountUserAssociation).where(SchemeAccountUserAssociation.user_id == user1.id)

    with pytest.raises(falcon.HTTPConflict) as e:
        loyalty_card_handler.handle_trusted_add_card()

    err_resp = {
        "email": "A loyalty card with this account_id has already been added in a wallet, "
        "but the key credential does not match.",
        "merchant_identifier": "A loyalty card with this key credential has already been added "
        "in a wallet, but the account_id does not match.",
    }
    assert e.value.title == err_resp[credential]
    assert e.value.code == "CONFLICT"

    user_links = db_session.execute(user_link_q).all()
    assert not mock_hermes_msg.called
    assert len(user_links) == 0
