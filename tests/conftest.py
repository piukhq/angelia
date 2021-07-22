from typing import Generator

import pytest
from sqlalchemy_utils import create_database, database_exists, drop_database

from app.hermes.db import write_engine
from app.hermes.db import write_engine as engine
from app.hermes.models import metadata
from tests.common import Session


@pytest.fixture(scope="session", autouse=True)
def setup_db() -> Generator:
    if write_engine.url.database != "hermes_test":
        raise ValueError(f"Unsafe attempt to recreate database: {write_engine.url.database}")

    if database_exists(write_engine.url):
        drop_database(write_engine.url)
    create_database(write_engine.url)

    yield

    # At end of all tests, drop the test db
    drop_database(write_engine.url)


@pytest.fixture(scope="function", autouse=True)
def setup_tables() -> Generator:
    """
    autouse set to True so will be run before each test function, to set up tables
    and tear them down after each test runs
    """
    metadata.create_all(write_engine)

    yield

    # Drop all tables after each test
    metadata.drop_all(write_engine)


@pytest.fixture
def db_session():
    Session.configure(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        Session.remove()
