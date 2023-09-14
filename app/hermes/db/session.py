from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import scoped_session as _scoped_session
from sqlalchemy.orm import sessionmaker

from settings import POSTGRES_CONNECT_ARGS, POSTGRES_DSN, TESTING

if TESTING:
    _template_engine = create_engine(POSTGRES_DSN.replace("_test", ""), connect_args=POSTGRES_CONNECT_ARGS)
    engine = create_engine(POSTGRES_DSN, connect_args=POSTGRES_CONNECT_ARGS)
    metadata = MetaData(bind=_template_engine)
else:
    engine = create_engine(POSTGRES_DSN, connect_args=POSTGRES_CONNECT_ARGS)
    metadata = MetaData(bind=engine)


SessionMaker = sessionmaker(bind=engine, future=True)
scoped_db_session = _scoped_session(SessionMaker)
