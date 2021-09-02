import typing
from unittest.mock import patch

import faker
import pytest

from app.hermes.models import PaymentAccountUserAssociation
from tests.factories import PaymentAccountFactory, PaymentAccountHandlerFactory, PaymentCardFactory, UserFactory

if typing.TYPE_CHECKING:
    from unittest.mock import MagicMock

    from sqlalchemy.orm import Session


fake = faker.Faker()


@pytest.fixture(scope="function", autouse=True)
def data_setup(db_session):
    other = PaymentCardFactory(slug="other")
    amex = PaymentCardFactory(slug="amex")
    visa = PaymentCardFactory(slug="visa")
    mastercard = PaymentCardFactory(slug="mastercard")

    db_session.add(other)
    db_session.add(amex)
    db_session.add(visa)
    db_session.add(mastercard)

    db_session.commit()


def test_link(db_session: "Session"):
    """Tests linking user to existing payment account creates a link between user and payment account"""
    user = UserFactory()
    db_session.flush()
    payment_account_handler = PaymentAccountHandlerFactory(db_session=db_session, user_id=user.id)
    payment_account = PaymentAccountFactory()
    db_session.commit()

    payment_acc = payment_account_handler.link(payment_account, [])

    assert (
        db_session.query(PaymentAccountUserAssociation)
        .filter(
            PaymentAccountUserAssociation.user_id == user.id,
            PaymentAccountUserAssociation.payment_card_account_id == payment_acc.id,
        )
        .count()
        == 1
    )


def test_link_when_a_link_already_exists(db_session: "Session"):
    """Tests that calling link does not create a new link if the user is in the linked_users argument"""
    user = UserFactory()
    db_session.flush()
    payment_account_handler = PaymentAccountHandlerFactory(db_session=db_session, user_id=user.id)
    payment_account = PaymentAccountFactory()
    db_session.commit()

    payment_acc = payment_account_handler.link(payment_account, [user])

    assert (
        db_session.query(PaymentAccountUserAssociation)
        .filter(
            PaymentAccountUserAssociation.user_id == user.id,
            PaymentAccountUserAssociation.payment_card_account_id == payment_acc.id,
        )
        .count()
        == 0
    )


def test_link_updates_account_details_for_a_new_link(db_session: "Session"):
    """Tests calling link updates a payment account details when linking a new user"""
    user = UserFactory()
    db_session.flush()

    pan_start = "123456"
    pan_end = "1234"
    fingerprint = "somefingerprint"
    token = "sometoken"
    psp_token = "somepsptoken"
    status = 0
    card_nickname = "somenickname"

    payment_account = PaymentAccountFactory(
        expiry_month="12",
        expiry_year="2022",
        name_on_card="Bonky Bonk",
        # card_nickname="Binky",
        pan_start=pan_start,
        pan_end=pan_end,
        fingerprint=fingerprint,
        token=token,
        psp_token=psp_token,
        status=status,
        card_nickname=card_nickname,
    )
    db_session.commit()
    payment_account_handler = PaymentAccountHandlerFactory(
        db_session=db_session,
        user_id=user.id,
        expiry_month="01",
        expiry_year="2025",
        name_on_card="They call me Bunk now",
        card_nickname="Bunkbed",
    )

    payment_acc = payment_account_handler.link(payment_account, [])

    # updated fields
    assert payment_acc.expiry_month == 1
    assert payment_acc.expiry_year == 2025
    assert payment_acc.name_on_card == "They call me Bunk now"
    assert payment_acc.card_nickname == "Bunkbed"

    # Fields that should stay the same
    assert payment_acc.pan_start == pan_start
    assert payment_acc.pan_end == pan_end
    assert payment_acc.fingerprint == fingerprint
    assert payment_acc.token == token
    assert payment_acc.psp_token == psp_token
    assert payment_acc.status == status


def test_link_updates_account_details_for_an_existing_link(db_session: "Session"):
    """Tests calling link updates a payment account details when linking an existing user"""
    user = UserFactory()
    db_session.flush()

    pan_start = "123456"
    pan_end = "1234"
    fingerprint = "somefingerprint"
    token = "sometoken"
    psp_token = "somepsptoken"
    status = 0
    card_nickname = "somenickname"

    payment_account = PaymentAccountFactory(
        expiry_month="12",
        expiry_year="2022",
        name_on_card="Bonky Bonk",
        # card_nickname="Binky",
        pan_start=pan_start,
        pan_end=pan_end,
        fingerprint=fingerprint,
        token=token,
        psp_token=psp_token,
        status=status,
        card_nickname=card_nickname,
    )
    db_session.commit()
    payment_account_handler = PaymentAccountHandlerFactory(
        db_session=db_session,
        user_id=user.id,
        expiry_month="01",
        expiry_year="2025",
        name_on_card="They call me Bunk now",
        card_nickname="Bunkbed",
    )

    payment_acc = payment_account_handler.link(payment_account, [user])

    # updated fields
    assert payment_acc.expiry_month == 1
    assert payment_acc.expiry_year == 2025
    assert payment_acc.name_on_card == "They call me Bunk now"
    assert payment_acc.card_nickname == "Bunkbed"

    # Fields that should stay the same
    assert payment_acc.pan_start == pan_start
    assert payment_acc.pan_end == pan_end
    assert payment_acc.fingerprint == fingerprint
    assert payment_acc.token == token
    assert payment_acc.psp_token == psp_token
    assert payment_acc.status == status


def test_create(db_session: "Session"):
    user = UserFactory()
    db_session.commit()
    payment_account_handler = PaymentAccountHandlerFactory(db_session=db_session, user_id=user.id)
    new_acc, resp_data = payment_account_handler.create()

    assert resp_data == {
        "expiry_month": payment_account_handler.expiry_month,
        "expiry_year": payment_account_handler.expiry_year,
        "name_on_card": "",
        "card_nickname": "",
        "issuer": "",
        "id": new_acc.id,
        "status": "pending",
    }
    assert new_acc.expiry_month == int(payment_account_handler.expiry_month)
    assert new_acc.expiry_year == int(payment_account_handler.expiry_year)
    assert new_acc.fingerprint == payment_account_handler.fingerprint
    assert new_acc.token == payment_account_handler.token
    assert new_acc.pan_end == payment_account_handler.last_four_digits
    assert new_acc.pan_start == payment_account_handler.first_six_digits

    assert len(new_acc.payment_account_user_assoc) == 1
    assert new_acc.payment_account_user_assoc[0].user_id == 1


@patch("app.handlers.payment_account.send_message_to_hermes")
def test_add_card_new_account(mock_hermes_msg: "MagicMock", db_session: "Session"):
    user = UserFactory()
    db_session.commit()
    payment_account_handler = PaymentAccountHandlerFactory(db_session=db_session, user_id=user.id)

    resp_data, created = payment_account_handler.add_card()

    assert created is True
    assert resp_data == {
        "expiry_month": payment_account_handler.expiry_month,
        "expiry_year": payment_account_handler.expiry_year,
        "name_on_card": payment_account_handler.name_on_card,
        "card_nickname": payment_account_handler.card_nickname,
        "issuer": payment_account_handler.issuer,
        "id": 1,
        "status": "pending",
    }
    assert mock_hermes_msg.called is True

    links = (
        db_session.query(PaymentAccountUserAssociation)
        .filter(
            PaymentAccountUserAssociation.payment_card_account_id == 1, PaymentAccountUserAssociation.user_id == user.id
        )
        .count()
    )
    assert links == 1


@patch("app.handlers.payment_account.send_message_to_hermes")
def test_add_card_existing_account(mock_hermes_msg: "MagicMock", db_session: "Session"):
    user = UserFactory()
    fingerprint = "some-fingerprint"
    payment_account = PaymentAccountFactory(fingerprint=fingerprint)
    db_session.commit()

    payment_account_handler = PaymentAccountHandlerFactory(
        db_session=db_session,
        user_id=user.id,
        fingerprint=fingerprint,
    )

    resp_data, created = payment_account_handler.add_card()

    assert created is False
    assert resp_data == {
        "expiry_month": int(payment_account_handler.expiry_month),
        "expiry_year": int(payment_account_handler.expiry_year),
        "name_on_card": payment_account_handler.name_on_card,
        "card_nickname": payment_account_handler.card_nickname,
        "issuer": payment_account.issuer_name,
        "id": payment_account.id,
        "status": "pending",
    }
    assert mock_hermes_msg.called is True

    links = (
        db_session.query(PaymentAccountUserAssociation)
        .filter(
            PaymentAccountUserAssociation.payment_card_account_id == payment_account.id,
            PaymentAccountUserAssociation.user_id == user.id,
        )
        .count()
    )
    assert links == 1


@patch("app.handlers.payment_account.send_message_to_hermes")
def test_add_card_multiple_fingerprints(mock_hermes_msg: "MagicMock", db_session: "Session"):
    user = UserFactory()
    fingerprint = "some-fingerprint"
    payment_account = PaymentAccountFactory(fingerprint=fingerprint)
    payment_account2 = PaymentAccountFactory(fingerprint=fingerprint)
    db_session.commit()

    payment_account_handler = PaymentAccountHandlerFactory(
        db_session=db_session,
        user_id=user.id,
        fingerprint=fingerprint,
    )

    resp_data, created = payment_account_handler.add_card()

    assert created is False
    assert resp_data == {
        "expiry_month": int(payment_account_handler.expiry_month),
        "expiry_year": int(payment_account_handler.expiry_year),
        "name_on_card": payment_account_handler.name_on_card,
        "card_nickname": payment_account_handler.card_nickname,
        "issuer": payment_account2.issuer_name,
        "id": payment_account2.id,
        "status": "pending",
    }
    assert mock_hermes_msg.called is True

    links_to_pa2 = (
        db_session.query(PaymentAccountUserAssociation)
        .filter(
            PaymentAccountUserAssociation.payment_card_account_id == payment_account2.id,
            PaymentAccountUserAssociation.user_id == user.id,
        )
        .count()
    )
    assert links_to_pa2 == 1

    links_to_pa1 = (
        db_session.query(PaymentAccountUserAssociation)
        .filter(
            PaymentAccountUserAssociation.payment_card_account_id == payment_account.id,
            PaymentAccountUserAssociation.user_id == user.id,
        )
        .count()
    )
    assert links_to_pa1 == 0