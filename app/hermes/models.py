
from sqlalchemy import *

from sqlalchemy.orm import relationship
from .db import Base, read_engine

# Create and engine and get the metadata
metadata = MetaData(bind=read_engine)


# Reflect each database table we need to use, using metadata
class User(Base):
    __table__ = Table('user', metadata, autoload=True)
    profile = relationship("UserDetail", backref="user", uselist=False)   # uselist = False sets one to one relation


class UserDetail(Base):
    __table__ = Table('user_userdetail', metadata, autoload=True)


class Organisation(Base):
    __table__ = Table('user_organisation', metadata, autoload=True)
    client_application = relationship("ClientApplication", backref="client")


class ClientApplication(Base):
    __table__ = Table('user_clientapplication', metadata, autoload=True)
    client_application_bundle = relationship("ClientApplicationBundle", backref="bundle")


class ClientApplicationBundle(Base):
    __table__ = Table('user_clientapplicationbundle', metadata, autoload=True)


class Issuer(Base):
    __table__ = Table('payment_card_issuer', metadata, autoload=True)

