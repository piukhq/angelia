from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest

from app.hermes.models import Channel
from tests.factories import ChannelFactory

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@pytest.fixture(scope="function")
def setup_channel(db_session: "Session") -> Callable[[], Channel]:
    def _setup_channel() -> Channel:
        channel = ChannelFactory()

        db_session.flush()

        return channel

    return _setup_channel
