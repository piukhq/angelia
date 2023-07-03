import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import MagicMock
from uuid import uuid4

import falcon
import jwt
import pytest
from sqlalchemy.future import select

from app.api.exceptions import MagicLinkExpiredTokenError, MagicLinkValidationError
from app.handlers.magic_link import MagicLinkHandler
from app.hermes.models import Channel, SchemeAccountUserAssociation, SchemeBundleAssociation, User
from tests.factories import (
    LoyaltyCardAnswerFactory,
    LoyaltyCardFactory,
    LoyaltyPlanFactory,
    LoyaltyPlanQuestionFactory,
    UserFactory,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture
    from sqlalchemy.orm import Session


@dataclass
class Mocks:
    redis: MagicMock
    dt_now: datetime


@pytest.fixture(scope="function")
def setup_user(db_session: "Session", setup_channel: Callable[[], Channel]) -> Callable[[], tuple[User, Channel]]:
    def _setup_user() -> tuple[User, Channel]:
        channel = setup_channel()
        user = UserFactory(client=channel.client_application)
        db_session.commit()

        return user, channel

    return _setup_user


@pytest.fixture(scope="function")
def mocks(mocker: "MockerFixture") -> Mocks:
    now = datetime.now(tz=UTC)

    mock_redis = mocker.patch("app.handlers.magic_link.redis")
    mock_redis.get.return_value = None

    mocker.patch("app.handlers.magic_link.datetime").now.return_value = now
    mocker.patch("app.hermes.models.datetime").now.return_value = now

    # this function is called only for channel's bundle_id "com.wasabi.bink.web" and is unittested separatedly.
    mocker.patch.object(MagicLinkHandler, "auto_add_membership_cards_with_email")

    return Mocks(
        redis=mock_redis,
        dt_now=now,
    )


def test_access_token_existing_user(
    db_session: "Session", mocker: "MockerFixture", setup_user: Callable[[], tuple[User, Channel]], mocks: Mocks
) -> None:
    user, channel = setup_user()
    test_jwt_secret = str(uuid4())

    mocker.patch("app.handlers.magic_link.get_channel_jwt_secret", return_value=test_jwt_secret)

    magic_link_token_data = {
        "email": user.email,
        "bundle_id": channel.bundle_id,
        "exp": int(mocks.dt_now.timestamp()) + 600,
    }
    tmp_token = jwt.encode(magic_link_token_data, key=test_jwt_secret, algorithm="HS512")
    token_hash = hashlib.md5(tmp_token.encode()).hexdigest()

    assert not user.magic_link_verified

    result = MagicLinkHandler(db_session=db_session).get_or_create_user(tmp_token)

    result_payload = jwt.decode(result["access_token"], user.client.secret + user.salt, algorithms=["HS256"])

    db_session.refresh(user)

    assert user.magic_link_verified
    assert result_payload == {
        "bundle_id": channel.bundle_id,
        "user_id": user.email,
        "sub": user.id,
        "iat": int(mocks.dt_now.timestamp()),
    }
    mocks.redis.get.assert_called_once_with(f"ml:{token_hash}")
    mocks.redis.set.assert_called_once_with(f"ml:{token_hash}", "y", 601)


def test_access_token_new_user(
    db_session: "Session", mocker: "MockerFixture", setup_channel: Callable[[], Channel], mocks: Mocks
) -> None:
    channel = setup_channel()
    test_jwt_secret = str(uuid4())
    email = "new@test.user"
    magic_link_token_data = {
        "email": email,
        "bundle_id": channel.bundle_id,
        "exp": int(mocks.dt_now.timestamp()) + 600,
    }
    tmp_token = jwt.encode(magic_link_token_data, key=test_jwt_secret, algorithm="HS512")
    token_hash = hashlib.md5(tmp_token.encode()).hexdigest()

    mocker.patch("app.handlers.magic_link.get_channel_jwt_secret", return_value=test_jwt_secret)
    assert not db_session.scalar(select(User).where(User.email == email))

    result = MagicLinkHandler(db_session=db_session).get_or_create_user(tmp_token)

    assert (new_user := db_session.scalar(select(User).where(User.email == email)))
    assert new_user.magic_link_verified

    result_payload = jwt.decode(result["access_token"], new_user.client.secret + new_user.salt, algorithms=["HS256"])
    assert result_payload == {
        "bundle_id": channel.bundle_id,
        "user_id": new_user.email,
        "sub": new_user.id,
        "iat": int(mocks.dt_now.timestamp()),
    }
    mocks.redis.get.assert_called_once_with(f"ml:{token_hash}")
    mocks.redis.set.assert_called_once_with(f"ml:{token_hash}", "y", 601)


def test_access_token_used_token(db_session: "Session", mocker: "MockerFixture", mocks: Mocks) -> None:
    email = "new@test.user"
    test_jwt_secret = str(uuid4())
    magic_link_token_data = {
        "email": email,
        "bundle_id": "sample",
        "exp": int(mocks.dt_now.timestamp()) + 600,
    }
    tmp_token = jwt.encode(magic_link_token_data, key=test_jwt_secret, algorithm="HS512")
    token_hash = hashlib.md5(tmp_token.encode()).hexdigest()

    mocks.redis.get.return_value = "y"
    mocker.patch("app.handlers.magic_link.get_channel_jwt_secret", return_value=test_jwt_secret)
    assert not db_session.scalar(select(User).where(User.email == email))

    with pytest.raises(MagicLinkExpiredTokenError):
        MagicLinkHandler(db_session=db_session).get_or_create_user(tmp_token)

    assert not db_session.scalar(select(User).where(User.email == email))
    mocks.redis.get.assert_called_once_with(f"ml:{token_hash}")
    mocks.redis.set.assert_not_called()


def test_access_token_wrong_token(db_session: "Session", mocker: "MockerFixture", mocks: Mocks) -> None:
    email = "new@test.user"
    test_jwt_secret = str(uuid4())
    magic_link_token_data = {
        "email": email,
        "bundle_id": "sample",
        "exp": int(mocks.dt_now.timestamp()) + 600,
    }
    tmp_token = jwt.encode(magic_link_token_data, key=test_jwt_secret, algorithm="HS512")

    mocker.patch("app.handlers.magic_link.get_channel_jwt_secret", side_effect=jwt.DecodeError)
    assert not db_session.scalar(select(User).where(User.email == email))

    with pytest.raises(MagicLinkValidationError):
        MagicLinkHandler(db_session=db_session).get_or_create_user(tmp_token)

    assert not db_session.scalar(select(User).where(User.email == email))
    mocks.redis.get.assert_not_called()
    mocks.redis.set.assert_not_called()


@pytest.mark.parametrize(
    ("scheme_slug", "card_email", "new_user_email", "excpected_result"),
    (
        pytest.param(
            "wasabi-club",
            "new@test.user",
            "new@test.user",
            "card_added",
            id="emails match and scheme is wasabi, card added",
        ),
        pytest.param(
            "not-wasabi-club",
            "new@test.user",
            "new@test.user",
            "card_ignored",
            id="emails match but scheme is not wasabi, card ignored",
        ),
        pytest.param(
            "wasabi-club",
            "new@test.user",
            "other@test.user",
            "card_ignored",
            id="scheme is wasabi but emails do not match, card ignored",
        ),
        pytest.param(
            "not-wasabi-club",
            "new@test.user",
            "other@test.user",
            "card_ignored",
            id="scheme is not wasabi and emails do not match, card ignored",
        ),
    ),
)
def test_auto_add_membership_cards_with_email(
    scheme_slug: str,
    card_email: str,
    new_user_email: str,
    excpected_result: str,
    db_session: "Session",
    setup_channel: Callable[[], Channel],
) -> None:
    channel = setup_channel()

    old_user = UserFactory(client=channel.client_application)
    new_user = UserFactory(email=new_user_email, client=channel.client_application)

    scheme = LoyaltyPlanFactory(slug=scheme_slug)
    scheme_account = LoyaltyCardFactory(scheme=scheme)
    scheme_account_entry = SchemeAccountUserAssociation(
        user=old_user, scheme_account=scheme_account, link_status=1, authorised=True
    )
    db_session.add(scheme_account_entry)
    db_session.flush()
    question = LoyaltyPlanQuestionFactory(type="email", auth_field=True, scheme_id=scheme.id)
    LoyaltyCardAnswerFactory(
        scheme_account_entry_id=scheme_account_entry.id, question_id=question.id, answer=card_email
    )

    db_session.commit()

    entries_query = select(SchemeAccountUserAssociation).where(SchemeAccountUserAssociation.user_id == new_user.id)

    assert not db_session.execute(entries_query).scalars().all()

    # currently we support this functionality only for Wasabi
    MagicLinkHandler(db_session=db_session).auto_add_membership_cards_with_email(new_user, "wasabi-club")
    db_session.commit()

    match excpected_result:
        case "card_added":
            assert (entries := (db_session.execute(entries_query).scalars().all()))
            assert len(entries) == 1
            assert entries[0].user_id == new_user.id
            assert entries[0].scheme_account_id == scheme_account.id
        case "card_ignored":
            assert not (db_session.execute(entries_query).scalars().all())
        case _:
            raise ValueError(f"excpected_result has unexpected value {excpected_result}")


def test_magic_link_email_happy_path(
    db_session: "Session", mocker: "MockerFixture", setup_channel: Callable[[], Channel]
) -> None:
    email = "new@test.user"
    scheme_slug = "test-scheme-slug"
    channel = setup_channel()
    mock_channel_secret = "channel-jwt-secret"
    channel.magic_link_url = "http://magic.link.url"
    channel.template = "magic_link_templates/bink20/binklogin.html"
    channel.subject = "Magic Link Request"
    scheme = LoyaltyPlanFactory(slug=scheme_slug)
    db_session.add(scheme)
    db_session.flush()

    sba = SchemeBundleAssociation(scheme_id=scheme.id, bundle_id=channel.id, status=0, test_scheme=False)
    db_session.add(sba)
    db_session.commit()

    mocker.patch("app.handlers.magic_link.get_channel_jwt_secret", return_value=mock_channel_secret)
    mock_send_message_to_hermes = mocker.patch("app.handlers.magic_link.send_message_to_hermes")

    MagicLinkHandler(db_session=db_session).send_magic_link_email(
        bundle_id=channel.bundle_id, email=email, locale="en_GB", slug=scheme_slug
    )
    mock_send_message_to_hermes.assert_called_once_with(
        "send_magic_link",
        {
            "bundle_id": "com.test.channel",
            "email": email,
            "email_from": channel.email_from,
            "external_name": "web",
            "locale": "en_GB",
            "slug": scheme_slug,
            "subject": channel.subject,
            "template": channel.template,
            "token": mocker.ANY,
            "url": channel.magic_link_url,
        },
    )
    token = mock_send_message_to_hermes.call_args_list[0].args[1]["token"]
    decoded_token = jwt.decode(token, mock_channel_secret, algorithms=["HS512", "HS256"])
    assert decoded_token["email"] == email
    assert decoded_token["bundle_id"] == channel.bundle_id
    assert datetime.fromtimestamp(decoded_token["exp"], tz=UTC) - datetime.fromtimestamp(
        decoded_token["iat"], tz=UTC
    ) == timedelta(minutes=60)


def test_magic_link_email_errors(
    db_session: "Session", mocker: "MockerFixture", setup_channel: Callable[[], Channel]
) -> None:
    email = "new@test.user"
    scheme_slug = "test-scheme-slug"
    channel = setup_channel()
    channel.subject = "Magic Link Request"
    scheme = LoyaltyPlanFactory(slug=scheme_slug)
    db_session.add(scheme)
    db_session.flush()

    sba = SchemeBundleAssociation(scheme_id=scheme.id, bundle_id=channel.id, status=0, test_scheme=False)
    db_session.add(sba)
    db_session.commit()

    mocker.patch("app.handlers.magic_link.get_channel_jwt_secret", return_value="channel-jwt-secret")
    mock_send_message_to_hermes = mocker.patch("app.handlers.magic_link.send_message_to_hermes")

    with pytest.raises(falcon.HTTPError) as ex:
        MagicLinkHandler(db_session=db_session).send_magic_link_email(
            bundle_id=channel.bundle_id, email=email, locale="en_GB", slug=scheme_slug
        )
    assert ex.value.code == "FIELD_VALIDATION_ERROR"
    assert ex.value.description == f"Config: Magic links not permitted for bundle id {channel.bundle_id}"
    mock_send_message_to_hermes.assert_not_called()

    channel.magic_link_url = "http://magic.link.url"
    db_session.commit()

    with pytest.raises(falcon.HTTPError) as ex:
        MagicLinkHandler(db_session=db_session).send_magic_link_email(
            bundle_id=channel.bundle_id, email=email, locale="en_GB", slug=scheme_slug
        )
    assert ex.value.code == "FIELD_VALIDATION_ERROR"
    assert ex.value.description == f"Config: Missing email template for bundle id {channel.bundle_id}"
    mock_send_message_to_hermes.assert_not_called()

    channel.template = "magic_link_templates/bink20/binklogin.html"
    db_session.commit()

    with pytest.raises(falcon.HTTPError) as ex:
        MagicLinkHandler(db_session=db_session).send_magic_link_email(
            bundle_id="oops.bink.wallet", email=email, locale="en_GB", slug=scheme_slug
        )
    assert ex.value.code == "FIELD_VALIDATION_ERROR"
    assert (
        ex.value.description
        == f"Config: invalid bundle id oops.bink.wallet was not found or did not have an active slug {scheme_slug}"
    )
    mock_send_message_to_hermes.assert_not_called()
