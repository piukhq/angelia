import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import MagicMock
from uuid import uuid4

import jwt
import pytest
from sqlalchemy.future import select

from app.api.exceptions import MagicLinkExpiredTokenError, MagicLinkValidationError
from app.handlers.magic_link import MagicLinkHandler
from app.hermes.models import Channel, SchemeAccountUserAssociation, User
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
