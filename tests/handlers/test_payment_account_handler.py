import typing
from unittest.mock import patch

import faker
import falcon
import pytest

from app.api.exceptions import ResourceNotFoundError
from app.handlers.payment_account import PaymentAccountHandler, PaymentAccountUpdateHandler
from app.hermes.models import PaymentAccountUserAssociation
from app.lib.payment_card import PaymentAccountStatus
from tests.factories import (
    PaymentAccountFactory,
    PaymentAccountHandlerFactory,
    PaymentAccountUpdateHandlerFactory,
    PaymentCardFactory,
    UserFactory,
)

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


def test_delete_card_calls_hermes(db_session: "Session"):
    user = UserFactory()
    payment_account = PaymentAccountFactory()
    association = PaymentAccountUserAssociation(user=user, payment_account=payment_account)

    db_session.add(association)
    db_session.commit()

    with patch("app.handlers.payment_account.send_message_to_hermes") as mock_hermes_call:
        PaymentAccountHandler.delete_card(db_session, "com.test.bink", user.id, payment_account.id)

    assert mock_hermes_call.called


def test_delete_card_acc_not_found(db_session: "Session"):
    user = UserFactory()
    payment_account = PaymentAccountFactory()
    db_session.commit()

    with pytest.raises(ResourceNotFoundError) as excinfo:
        PaymentAccountHandler.delete_card(db_session, "com.test.bink", user.id, payment_account.id)

    assert "RESOURCE_NOT_FOUND" == excinfo.value.code
    assert falcon.HTTP_NOT_FOUND == excinfo.value.status


def test_update_card_details_no_update_fields(db_session: "Session"):
    user = UserFactory()
    payment_account = PaymentAccountFactory()
    db_session.commit()

    update_fields = []

    payment_acc_update_handler = PaymentAccountUpdateHandlerFactory(
        db_session=db_session,
        user_id=user.id,
        account_id=payment_account.id,
    )

    old_pcard_fields = vars(payment_account).copy()
    pcard, fields_updated = payment_acc_update_handler._update_card_details(payment_account, update_fields)
    assert vars(pcard) == old_pcard_fields


def test_partial_update_card_details(db_session: "Session"):
    user = UserFactory()
    payment_account = PaymentAccountFactory()
    db_session.commit()

    update_fields = ["name_on_card", "issuer"]
    name_on_card = "some guy"
    issuer = "some issuer"
    card_nickname = payment_account.card_nickname
    expiry_month = str(payment_account.expiry_month)

    payment_acc_update_handler = PaymentAccountUpdateHandlerFactory(
        db_session=db_session,
        user_id=user.id,
        account_id=payment_account.id,
        issuer=issuer,
        name_on_card=name_on_card,
        card_nickname=card_nickname,
        expiry_month=expiry_month,
    )

    assert payment_account.name_on_card != name_on_card
    assert payment_account.issuer_name != issuer
    assert payment_account.card_nickname == card_nickname
    assert payment_account.expiry_month == int(expiry_month)

    pcard, fields_updated = payment_acc_update_handler._update_card_details(payment_account, update_fields)

    assert "name_on_card" in fields_updated
    assert "issuer_name" in fields_updated
    assert "card_nickname" not in fields_updated
    assert "expiry_month" not in fields_updated

    assert pcard.name_on_card == name_on_card
    assert pcard.issuer_name == issuer
    assert pcard.card_nickname == card_nickname
    assert pcard.expiry_month == int(expiry_month)

    assert payment_account.name_on_card == name_on_card
    assert payment_account.issuer_name == issuer
    assert payment_account.card_nickname == card_nickname
    assert payment_account.expiry_month == int(expiry_month)


def test_full_update_card_details(db_session: "Session"):
    user = UserFactory()
    payment_account = PaymentAccountFactory()
    db_session.commit()

    update_fields = ["name_on_card", "issuer", "expiry_year", "expiry_month", "card_nickname"]
    update_values = {
        "name_on_card": "some guy",
        "issuer_name": "some issuer",
        "expiry_year": "2030",
        "expiry_month": "01",
        "card_nickname": "Nicky",
    }

    payment_acc_update_handler = PaymentAccountUpdateHandlerFactory(
        db_session=db_session,
        user_id=user.id,
        account_id=payment_account.id,
        issuer=update_values["issuer_name"],
        name_on_card=update_values["name_on_card"],
        expiry_year=update_values["expiry_year"],
        expiry_month=update_values["expiry_month"],
        card_nickname=update_values["card_nickname"],
    )

    p_acc_field_names = ["name_on_card", "issuer_name", "expiry_year", "expiry_month", "card_nickname"]

    for field in p_acc_field_names:
        if field in ["expiry_month", "expiry_year"]:
            assert getattr(payment_account, field) != int(update_values[field])
        else:
            assert getattr(payment_account, field) != update_values[field]

    pcard, fields_updated = payment_acc_update_handler._update_card_details(payment_account, update_fields)

    for field in p_acc_field_names:
        assert field in fields_updated

        if field in ["expiry_month", "expiry_year"]:
            assert getattr(pcard, field) == int(update_values[field])
            assert getattr(payment_account, field) == int(update_values[field])
        else:
            assert getattr(pcard, field) == update_values[field]
            assert getattr(payment_account, field) == update_values[field]


def test_update_card_acc_not_found(db_session: "Session"):
    user = UserFactory()
    payment_account = PaymentAccountFactory(
        expiry_month=1,
        expiry_year=2030,
        name_on_card="hello",
        card_nickname="Dumbo",
        issuer_name="Barchillies",
        id=99999999,
        status=PaymentAccountStatus.ACTIVE,
    )
    db_session.commit()

    with pytest.raises(ResourceNotFoundError) as excinfo:
        payment_acc_update_handler = PaymentAccountUpdateHandlerFactory(
            db_session=db_session,
            user_id=user.id,
            account_id=payment_account.id,
        )

        _ = payment_acc_update_handler.update_card(update_fields=[])

    assert "RESOURCE_NOT_FOUND" == excinfo.value.code
    assert falcon.HTTP_NOT_FOUND == excinfo.value.status


def test_update_card(db_session: "Session"):
    user = UserFactory()
    expected_resp = {
        "expiry_month": 1,
        "expiry_year": 2030,
        "name_on_card": "hello",
        "card_nickname": "Dumbo",
        "issuer": "Barchillies",
        "id": 99999999,
        "status": "active",
    }

    payment_account = PaymentAccountFactory(
        expiry_month=expected_resp["expiry_month"],
        expiry_year=expected_resp["expiry_year"],
        name_on_card=expected_resp["name_on_card"],
        card_nickname=expected_resp["card_nickname"],
        issuer_name=expected_resp["issuer"],
        id=expected_resp["id"],
        status=PaymentAccountStatus.ACTIVE,
    )

    association = PaymentAccountUserAssociation(user=user, payment_account=payment_account)

    db_session.add(association)
    db_session.commit()

    with patch.object(PaymentAccountUpdateHandler, "_update_card_details") as mock_update:
        mock_update.return_value = payment_account, []
        payment_acc_update_handler = PaymentAccountUpdateHandlerFactory(
            db_session=db_session,
            user_id=user.id,
            account_id=payment_account.id,
        )

        resp = payment_acc_update_handler.update_card(update_fields=[])

        assert mock_update.called
        assert expected_resp == resp
