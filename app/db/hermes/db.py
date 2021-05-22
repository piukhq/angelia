from functools import wraps

from psycopg2 import errors
from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.report import api_logger
from settings import POSTGRES_WRITE_DSN, POSTGRES_READ_DSN

write_engine = create_engine(POSTGRES_WRITE_DSN, poolclass=NullPool)
read_engine = create_engine(POSTGRES_READ_DSN, poolclass=NullPool)
Base = declarative_base()


class Singleton(type):
    instance = None

    def __call__(cls, *args, **kwargs):
        if cls.instance is None:
            cls.instance = super(Singleton, cls).__call__(*args, **kwargs)
        return cls.instance


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
        """Note as a singleton will only run on first instantiation
        """
        self._Write_Session = sessionmaker(bind=write_engine)
        self._Read_Session = sessionmaker(bind=read_engine)
        self.session = None

    def __enter__(self):
        """Return session to the variable referenced in the "with as" statement"""
        return self.session

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def open_write(self):
        """Returns self to allow with clause to work and to allow chaining eg db().open_write().session"""
        self.session = self._Write_Session()
        return self

    def open_read(self):
        """Returns self to allow with clause to work and to allow chaining eg db().open_read().session"""
        self.session = self._Read_Session()
        return self

    def close(self):
        self.session.close()
        self.session = None


# based on the following stackoverflow answer:
# https://stackoverflow.com/a/30004941
def run_query_decorator(fn):
    @wraps(fn)
    def run_query(attempts: int = 2, write: bool = False, *args, **kwargs):
        # Note write is now redundant but has been kept to avoid breaking code
        # Should be removed when refactoring
        while attempts > 0:
            attempts -= 1
            db_session = DB().session
            try:
                return fn(db_session, *args, **kwargs)
            except DBAPIError as ex:
                api_logger.warning(
                    f"Database query {fn} failed with {type(ex).__name__}. {attempts} attempt(s) remaining.")
                if errors.UniqueViolation:
                    db_session.rollback()
                    print(ex)
                    raise
                elif attempts > 0 and ex.connection_invalidated:
                    db_session.rollback()
                else:
                    raise

    return run_query
