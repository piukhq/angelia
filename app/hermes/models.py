from sqlalchemy import MetaData, Table
from sqlalchemy.orm import relationship

from settings import TESTING

from .db import Base, engine

# Create an engine and get the metadata
if TESTING:
    from .db import read_engine

    metadata = MetaData(bind=read_engine)
else:
    metadata = MetaData(bind=engine)


# Reflect each database table we need to use, using metadata
class User(Base):
    __table__ = Table("user", metadata, autoload=True)
    profile = relationship("UserDetail", backref="user", uselist=False)  # uselist = False sets one to one relation
    scheme_account_user_associations = relationship("SchemeAccountUserAssociation", backref="user")
    payment_account_user_assoc = relationship("PaymentAccountUserAssociation", backref="user")
    client = relationship("ClientApplication", backref="user")


class UserDetail(Base):
    __table__ = Table("user_userdetail", metadata, autoload=True)


class Organisation(Base):
    __table__ = Table("user_organisation", metadata, autoload=True)
    client_applications = relationship("ClientApplication", backref="organisation")


class ClientApplication(Base):
    __table__ = Table("user_clientapplication", metadata, autoload=True)
    channel = relationship("Channel", backref="client_application")


class Channel(Base):
    __table__ = Table("user_clientapplicationbundle", metadata, autoload=True)
    issuer_associations = relationship("IssuerChannelAssociation", backref="channel")
    scheme_associations = relationship("SchemeChannelAssociation", backref="channel")


class Issuer(Base):
    __table__ = Table("payment_card_issuer", metadata, autoload=True)
    channel = relationship("IssuerChannelAssociation", backref="issuer")


class IssuerChannelAssociation(Base):
    __table__ = Table("user_clientapplicationbundle_issuer", metadata, autoload=True)


class SchemeChannelAssociation(Base):
    __table__ = Table("scheme_schemebundleassociation", metadata, autoload=True)


class Scheme(Base):
    __table__ = Table("scheme_scheme", metadata, autoload=True)
    channel_associations = relationship("SchemeChannelAssociation", backref="scheme")
    category = relationship("Category", backref="scheme")
    consent = relationship("Consent", backref="scheme")
    document = relationship("SchemeDocument", backref="scheme")


class SchemeAccount(Base):
    __table__ = Table("scheme_schemeaccount", metadata, autoload=True)
    scheme_account_user_associations = relationship("SchemeAccountUserAssociation", backref="scheme_account")
    scheme = relationship("Scheme", backref="scheme_account")


class SchemeAccountUserAssociation(Base):
    __table__ = Table("ubiquity_schemeaccountentry", metadata, autoload=True)


class SchemeAccountImage(Base):
    __table__ = Table("scheme_schemeaccountimage", metadata, autoload=True)


class SchemeAccountImageAssociation(Base):
    __table__ = Table("scheme_schemeaccountimage_scheme_accounts", metadata, autoload=True)
    scheme_account = relationship("SchemeAccount", backref="scheme_account_image_association")
    scheme_account_image = relationship("SchemeAccountImage", backref="scheme_account_image_association")


class SchemeCredentialQuestion(Base):
    __table__ = Table("scheme_schemecredentialquestion", metadata, autoload=True)
    scheme_assoc = relationship("Scheme", backref="scheme_credential_question")


class SchemeAccountCredentialAnswer(Base):
    __table__ = Table("scheme_schemeaccountcredentialanswer", metadata, autoload=True)
    scheme_account = relationship("SchemeAccount", backref="scheme_account_credential_answer")
    scheme_credential_question = relationship("SchemeCredentialQuestion", backref="scheme_account_credential_answer")


class PaymentCard(Base):
    __table__ = Table("payment_card_paymentcard", metadata, autoload=True)


class PaymentCardImage(Base):
    __table__ = Table("payment_card_paymentcardimage", metadata, autoload=True)
    payment_card = relationship("PaymentCard", backref="payment_card_image")


class PaymentAccountUserAssociation(Base):
    __table__ = Table("ubiquity_paymentcardaccountentry", metadata, autoload=True)


class PaymentAccount(Base):
    __table__ = Table("payment_card_paymentcardaccount", metadata, autoload=True)
    payment_account_user_assoc = relationship("PaymentAccountUserAssociation", backref="payment_account")
    payment_card = relationship("PaymentCard", backref="payment_account")


class PaymentCardAccountImageAssociation(Base):
    __table__ = Table("payment_card_paymentcardaccountimage_payment_card_accounts", metadata, autoload=True)
    payment_card_account = relationship("PaymentAccount", backref="payment_card_account_image_association")
    payment_card_account_image = relationship(
        "PaymentCardAccountImage", backref="payment_card_account_image_association"
    )


class PaymentCardAccountImage(Base):
    __table__ = Table("payment_card_paymentcardaccountimage", metadata, autoload=True)


class Category(Base):
    __table__ = Table("scheme_category", metadata, autoload=True)


class Consent(Base):
    __table__ = Table("scheme_consent", metadata, autoload=True)


class SchemeDocument(Base):
    __table__ = Table("ubiquity_membershipplandocument", metadata, autoload=True)


class SchemeImage(Base):
    __table__ = Table("scheme_schemeimage", metadata, autoload=True)
    scheme = relationship("Scheme", backref="scheme_image")


class SchemeDetail(Base):
    __table__ = Table("scheme_schemedetail", metadata, autoload=True)
    scheme = relationship("Scheme", backref="scheme_detail")


class SchemeBalanceDetails(Base):
    __table__ = Table("scheme_schemebalancedetails", metadata, autoload=True)
    scheme = relationship("Scheme", backref="scheme_balance_detail")


class SchemeOverrideError(Base):
    __table__ = Table("scheme_schemeoverrideerror", metadata, autoload=True)
    scheme = relationship("Scheme", backref="scheme_override_error")


class SchemeContent(Base):
    __table__ = Table("scheme_schemecontent", metadata, autoload=True)
    scheme = relationship("Scheme", backref="scheme_content")


class ThirdPartyConsentLink(Base):
    __table__ = Table("scheme_thirdpartyconsentlink", metadata, autoload=True)
    scheme = relationship("Scheme", backref="thirdpartylink")
    consent = relationship("Consent", backref="thirdpartylink")
    client_application = relationship("ClientApplication", backref="thirdpartylink")


class PaymentSchemeAccountAssociation(Base):
    __table__ = Table("ubiquity_paymentcardschemeentry", metadata, autoload=True)
    payment_account = relationship("PaymentAccount", backref="PaymentSchemeAccountAssociation")
    scheme_account = relationship("SchemeAccount", backref="PaymentSchemeAccountAssociation")


class ServiceConsent(Base):
    __table__ = Table("ubiquity_serviceconsent", metadata, autoload=True)
    user = relationship("User", backref="service_consent")
