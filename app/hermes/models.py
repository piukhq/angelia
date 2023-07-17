from typing import cast

from sqlalchemy import Table
from sqlalchemy.orm import DeclarativeMeta, relationship

from app.hermes.db import DB

ModelBase: DeclarativeMeta = cast(DeclarativeMeta, DB().Base)


# Reflect each database table we need to use, using metadata
class User(ModelBase):
    __table__ = Table("user", DB().metadata, autoload=True)
    profile = relationship("UserDetail", backref="user", uselist=False)  # uselist = False sets one to one relation
    scheme_account_user_associations = relationship("SchemeAccountUserAssociation", backref="user")
    client = relationship("ClientApplication", backref="user")


class UserDetail(ModelBase):
    __table__ = Table("user_userdetail", DB().metadata, autoload=True)


class Organisation(ModelBase):
    __table__ = Table("user_organisation", DB().metadata, autoload=True)
    client_applications = relationship("ClientApplication", backref="organisation")


class ClientApplication(ModelBase):
    __table__ = Table("user_clientapplication", DB().metadata, autoload=True)
    channel = relationship("Channel", backref="client_application")


class Channel(ModelBase):
    __table__ = Table("user_clientapplicationbundle", DB().metadata, autoload=True)
    issuer_associations = relationship("IssuerChannelAssociation", backref="channel")
    scheme_associations = relationship("SchemeChannelAssociation", backref="channel")


class Issuer(ModelBase):
    __table__ = Table("payment_card_issuer", DB().metadata, autoload=True)
    channel = relationship("IssuerChannelAssociation", backref="issuer")


class IssuerChannelAssociation(ModelBase):
    __table__ = Table("user_clientapplicationbundle_issuer", DB().metadata, autoload=True)


class SchemeChannelAssociation(ModelBase):
    __table__ = Table("scheme_schemebundleassociation", DB().metadata, autoload=True)


class Scheme(ModelBase):
    __table__ = Table("scheme_scheme", DB().metadata, autoload=True)
    channel_associations = relationship("SchemeChannelAssociation", backref="scheme")
    category = relationship("Category", lazy="joined", backref="scheme")
    consent = relationship("Consent", backref="scheme")
    document = relationship("SchemeDocument", backref="scheme")


class SchemeAccount(ModelBase):
    __table__ = Table("scheme_schemeaccount", DB().metadata, autoload=True)
    scheme_account_user_associations = relationship("SchemeAccountUserAssociation", backref="scheme_account")
    scheme = relationship("Scheme", backref="scheme_account")


class SchemeAccountUserAssociation(ModelBase):
    __table__ = Table("ubiquity_schemeaccountentry", DB().metadata, autoload=True)


class SchemeAccountImage(ModelBase):
    __table__ = Table("scheme_schemeaccountimage", DB().metadata, autoload=True)


class SchemeAccountImageAssociation(ModelBase):
    __table__ = Table("scheme_schemeaccountimage_scheme_accounts", DB().metadata, autoload=True)
    scheme_account = relationship("SchemeAccount", backref="scheme_account_image_association")
    scheme_account_image = relationship("SchemeAccountImage", backref="scheme_account_image_association")


class SchemeCredentialQuestion(ModelBase):
    __table__ = Table("scheme_schemecredentialquestion", DB().metadata, autoload=True)
    scheme_assoc = relationship("Scheme", backref="scheme_credential_question")


class SchemeAccountCredentialAnswer(ModelBase):
    __table__ = Table("scheme_schemeaccountcredentialanswer", DB().metadata, autoload=True)
    scheme_account_entry = relationship("SchemeAccountUserAssociation", backref="scheme_account_credential_answer")
    scheme_credential_question = relationship("SchemeCredentialQuestion", backref="scheme_account_credential_answer")


class PaymentCard(ModelBase):
    __table__ = Table("payment_card_paymentcard", DB().metadata, autoload=True)


class PaymentCardImage(ModelBase):
    __table__ = Table("payment_card_paymentcardimage", DB().metadata, autoload=True)
    payment_card = relationship("PaymentCard", backref="payment_card_image")


class PaymentAccountUserAssociation(ModelBase):
    __table__ = Table("ubiquity_paymentcardaccountentry", DB().metadata, autoload=True)
    payment_card_account = relationship("PaymentAccount", backref="payment_account_user_association")
    user = relationship("User", backref="payment_account_user_association")


class PaymentAccount(ModelBase):
    __table__ = Table("payment_card_paymentcardaccount", DB().metadata, autoload=True)
    payment_card = relationship("PaymentCard", backref="payment_account")


class PaymentCardAccountImageAssociation(ModelBase):
    __table__ = Table("payment_card_paymentcardaccountimage_payment_card_accounts", DB().metadata, autoload=True)
    payment_card_account = relationship("PaymentAccount", backref="payment_card_account_image_association")
    payment_card_account_image = relationship(
        "PaymentCardAccountImage", backref="payment_card_account_image_association"
    )


class PaymentCardAccountImage(ModelBase):
    __table__ = Table("payment_card_paymentcardaccountimage", DB().metadata, autoload=True)


class Category(ModelBase):
    __table__ = Table("scheme_category", DB().metadata, autoload=True)


class Consent(ModelBase):
    __table__ = Table("scheme_consent", DB().metadata, autoload=True)


class SchemeDocument(ModelBase):
    __table__ = Table("ubiquity_membershipplandocument", DB().metadata, autoload=True)


class SchemeImage(ModelBase):
    __table__ = Table("scheme_schemeimage", DB().metadata, autoload=True)
    scheme = relationship("Scheme", backref="scheme_image")


class SchemeDetail(ModelBase):
    __table__ = Table("scheme_schemedetail", DB().metadata, autoload=True)
    scheme = relationship("Scheme", backref="scheme_detail")


class SchemeBalanceDetails(ModelBase):
    __table__ = Table("scheme_schemebalancedetails", DB().metadata, autoload=True)
    scheme = relationship("Scheme", backref="scheme_balance_detail")


class SchemeOverrideError(ModelBase):
    __table__ = Table("scheme_schemeoverrideerror", DB().metadata, autoload=True)
    scheme = relationship("Scheme", backref="scheme_override_error")
    channel = relationship("Channel", backref="scheme_override_error")


class SchemeContent(ModelBase):
    __table__ = Table("scheme_schemecontent", DB().metadata, autoload=True)
    scheme = relationship("Scheme", backref="scheme_content")


class ThirdPartyConsentLink(ModelBase):
    __table__ = Table("scheme_thirdpartyconsentlink", DB().metadata, autoload=True)
    scheme = relationship("Scheme", backref="thirdpartylink")
    consent = relationship("Consent", lazy="joined", backref="thirdpartylink")
    client_application = relationship("ClientApplication", backref="thirdpartylink")


class PaymentSchemeAccountAssociation(ModelBase):
    __table__ = Table("ubiquity_paymentcardschemeentry", DB().metadata, autoload=True)
    payment_card_account = relationship("PaymentAccount", backref="payment_scheme_account_association")
    scheme_account = relationship("SchemeAccount", backref="payment_scheme_account_association")


class PLLUserAssociation(ModelBase):
    __table__ = Table("ubiquity_plluserassociation", DB().metadata, autoload=True)
    user = relationship("User", backref="pll_user_association")
    pll = relationship("PaymentSchemeAccountAssociation", backref="pll_user_association")


class ServiceConsent(ModelBase):
    __table__ = Table("ubiquity_serviceconsent", DB().metadata, autoload=True)
    user = relationship("User", backref="service_consent")


watched_classes = [
    User,
    SchemeAccount,
    SchemeAccountUserAssociation,
    PaymentAccount,
    PaymentAccountUserAssociation,
    PaymentSchemeAccountAssociation,
]

DB().init_mapper_event_listeners(watched_classes)
