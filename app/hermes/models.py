from sqlalchemy import MetaData, Table
from sqlalchemy.orm import relationship

from .db import Base, read_engine

# Create and engine and get the metadata
metadata = MetaData(bind=read_engine)


# Reflect each database table we need to use, using metadata
class User(Base):
    __table__ = Table("user", metadata, autoload=True)
    profile = relationship("UserDetail", backref="user", uselist=False)  # uselist = False sets one to one relation
    scheme_account_user_associations = relationship("SchemeAccountUserAssociation", backref="user")
    payment_account_user_assoc = relationship("PaymentAccountUserAssociation", backref="user")


class UserDetail(Base):
    __table__ = Table("user_userdetail", metadata, autoload=True)


class Organisation(Base):
    __table__ = Table("user_organisation", metadata, autoload=True)
    client_applications = relationship("ClientApplication", backref="organisation")


class ClientApplication(Base):
    __table__ = Table("user_clientapplication", metadata, autoload=True)
    channels = relationship("Channel", backref="client_application")


class Channel(Base):
    __table__ = Table("user_clientapplicationbundle", metadata, autoload=True)
    issuer_associations = relationship("IssuerChannelAssociation", backref="channel")
    scheme_associations = relationship("SchemeChannelAssociation", backref="channel")


class Issuer(Base):
    __table__ = Table("payment_card_issuer", metadata, autoload=True)
    channels = relationship("IssuerChannelAssociation", backref="issuer")


class IssuerChannelAssociation(Base):
    __table__ = Table("user_clientapplicationbundle_issuer", metadata, autoload=True)


class SchemeChannelAssociation(Base):
    __table__ = Table("scheme_schemebundleassociation", metadata, autoload=True)


class Scheme(Base):
    __table__ = Table("scheme_scheme", metadata, autoload=True)
    channel_associations = relationship("SchemeChannelAssociation", backref="scheme")
    scheme_accounts = relationship("SchemeAccount", backref="scheme")


class SchemeAccount(Base):
    __table__ = Table("scheme_schemeaccount", metadata, autoload=True)
    scheme_account_user_associations = relationship("SchemeAccountUserAssociation", backref="scheme_account")


class SchemeAccountUserAssociation(Base):
    __table__ = Table("ubiquity_schemeaccountentry", metadata, autoload=True)


class SchemeCredentialQuestion(Base):
    __table__ = Table("scheme_schemecredentialquestion", metadata, autoload=True)
    scheme_assoc = relationship("Scheme", backref="scheme_credential_question")


class SchemeAccountCredentialAnswer(Base):
    __table__ = Table("scheme_schemeaccountcredentialanswer", metadata, autoload=True)
    scheme_account_assoc = relationship("SchemeAccount", backref="scheme_account_credential_answer")
    scheme_credential_question_assoc = relationship(
        "SchemeCredentialQuestion", backref="scheme_account_credential_answer"
    )


class PaymentCard(Base):
    __table__ = Table("payment_card_paymentcard", metadata, autoload=True)


class PaymentAccountUserAssociation(Base):
    __table__ = Table("ubiquity_paymentcardaccountentry", metadata, autoload=True)


class PaymentAccount(Base):
    __table__ = Table("payment_card_paymentcardaccount", metadata, autoload=True)
    payment_account_user_assoc = relationship("PaymentAccountUserAssociation", backref="payment_account")
