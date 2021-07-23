import pytest
from sqlalchemy.orm import Session

from app.handlers.payment_account import PaymentAccountHandler
from app.hermes.db import DB, write_engine as engine


@pytest.fixture
def db_session():
    connection = engine.connect()
    session = Session(bind=connection)
    transaction = connection.begin_nested()
    try:
        yield session
    finally:
        transaction.rollback()
        session.close()


def test_payment_account_handler(db_session):
    handler = PaymentAccountHandler(
        db_session=db_session,
        user_id=1,
        channel_id="",
        expiry_month="",
        expiry_year="",
        token="",
        last_four_digits="",
        first_six_digits="",
        fingerprint="",
    )


def test_link():
    pass


def test_create():
    pass


def test_add_card_new_account():
    pass


def test_add_card_existing_account():
    pass


def test_add_card_multiple_fingerprints():
    pass
