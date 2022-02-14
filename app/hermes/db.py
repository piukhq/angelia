from sqlalchemy import MetaData, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker

from app.lib.singletons import Singleton
from settings import POSTGRES_DSN, TESTING


class DB(metaclass=Singleton):
    """This is a singleton class to manage sessions.

    To use the singleton import the DB class then:

    DB().open_write() or DB().open_read()  at start of request ie in middleware
    DB().session   to get the session in database layer
    DB().session.close() to close the session at the end of request in middleware

    For non api code use in with statement:

    with DB().open_write() as session:
    with DB().open_read() as session:


    """

    def __init__(self):
        """Note as a singleton will only run on first instantiation"""
        # test_engine is used only for tests to copy the hermes schema to the hermes_test db
        if TESTING:
            self.test_engine = create_engine(POSTGRES_DSN)
            self.engine = create_engine(f"{POSTGRES_DSN}_test")
            self.metadata = MetaData(bind=self.test_engine)
        else:
            self.engine = create_engine(POSTGRES_DSN)
            self.metadata = MetaData(bind=self.engine)

        self.Base = declarative_base()

        self.Session = scoped_session(sessionmaker(bind=self.engine, future=True))
        self.session = None

    def __enter__(self):
        """Return session to the variable referenced in the "with as" statement"""
        return self.session

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def open(self):
        """Returns self to allow with clause to work and to allow chaining eg db().open_read().session"""
        self.session = self.Session()
        return self

    def close(self):
        self.session.close()
