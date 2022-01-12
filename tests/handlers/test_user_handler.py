import typing
from unittest.mock import MagicMock, patch

import falcon
import pytest
from faker import Faker
from sqlalchemy import select

from tests.factories import ChannelFactory, UserFactory, UserHandlerFactory

if typing.TYPE_CHECKING:
    from sqlalchemy.orm import Session

from app.hermes.models import User

fake = Faker()


@pytest.fixture(scope="function")
def setup_channel(db_session: "Session"):
    def _setup_channel():

        channel = ChannelFactory()

        db_session.flush()

        return channel

    return _setup_channel


@pytest.fixture(scope="function")
def setup_user_handler(db_session: "Session", setup_channel):
    def _setup_user_handler():

        user_handler = UserHandlerFactory(db_session=db_session)
        channel = setup_channel()

        return user_handler, channel

    return _setup_user_handler


def test_email_update(db_session: "Session", setup_user_handler):

    user_handler, channel = setup_user_handler()

    user = UserFactory(email="previous@email.com", client=channel.client_application)

    db_session.commit()

    user_handler.user_id = user.id
    new_email = "validemail@test.com"
    user_handler.new_email = new_email

    user_handler.handle_email_update()

    query = (select(User)).where(User.id == user.id)

    result = (db_session.execute(query).one())[0]

    assert isinstance(result, User)
    assert result.id == user.id
    assert result.email == new_email
    assert result.client == channel.client_application


def test_email_update_same_email(db_session: "Session", setup_user_handler):

    user_handler, channel = setup_user_handler()

    user = UserFactory(email="same@email.com", client=channel.client_application)

    db_session.commit()

    user_handler.user_id = user.id
    new_email = "same@email.com"
    user_handler.new_email = new_email

    user_handler.handle_email_update()

    query = (select(User)).where(User.id == user.id)

    result = (db_session.execute(query).one())[0]

    assert isinstance(result, User)
    assert result.id == user.id
    assert result.email == new_email
    assert result.client == channel.client_application


def test_error_email_update_already_exists(db_session: "Session", setup_user_handler):

    user_handler, channel = setup_user_handler()

    user_1 = UserFactory(email="old@email.com", client=channel.client_application)
    UserFactory(email="taken@email.com", client=channel.client_application)

    db_session.commit()

    user_handler.user_id = user_1.id
    new_email = "taken@email.com"
    user_handler.new_email = new_email

    with pytest.raises(falcon.HTTPConflict):
        user_handler.handle_email_update()


def test_error_email_update_multiple_existing_emails(db_session: "Session", setup_user_handler):

    user_handler, channel = setup_user_handler()

    user_1 = UserFactory(email="old@email.com", client=channel.client_application)
    UserFactory(email="taken@email.com", client=channel.client_application, external_id="abcd")
    UserFactory(email="taken@email.com", client=channel.client_application, external_id="1234")

    db_session.commit()

    user_handler.user_id = user_1.id
    new_email = "taken@email.com"
    user_handler.new_email = new_email

    with pytest.raises(falcon.HTTPInternalServerError):
        user_handler.handle_email_update()


@patch("app.handlers.user.send_message_to_hermes")
def test_delete_user(mock_hermes_msg: "MagicMock", db_session: "Session", setup_user_handler):

    user_handler, channel = setup_user_handler()

    user_1 = UserFactory(email="old@email.com", client=channel.client_application)

    db_session.commit()

    user_handler.user_id = user_1.id

    user_handler.send_for_deletion()

    assert mock_hermes_msg.called is True
