from sqlalchemy import Table, event
from sqlalchemy.orm import mapper, relationship

from app.messaging.sender import mapper_history

from .db import DB


# Reflect each database table we need to use, using metadata
class User(DB().Base):
    __table__ = Table("user", DB().metadata, autoload=True)
    profile = relationship("UserDetail", backref="user", uselist=False)  # uselist = False sets one to one relation
    scheme_account_user_associations = relationship("SchemeAccountUserAssociation", backref="user")
    payment_account_user_assoc = relationship("PaymentAccountUserAssociation", backref="user")
    client = relationship("ClientApplication", backref="user")


class UserDetail(DB().Base):
    __table__ = Table("user_userdetail", DB().metadata, autoload=True)


class Organisation(DB().Base):
    __table__ = Table("user_organisation", DB().metadata, autoload=True)
    client_applications = relationship("ClientApplication", backref="organisation")


class ClientApplication(DB().Base):
    __table__ = Table("user_clientapplication", DB().metadata, autoload=True)
    channel = relationship("Channel", backref="client_application")


class Channel(DB().Base):
    __table__ = Table("user_clientapplicationbundle", DB().metadata, autoload=True)
    issuer_associations = relationship("IssuerChannelAssociation", backref="channel")
    scheme_associations = relationship("SchemeChannelAssociation", backref="channel")


class Issuer(DB().Base):
    __table__ = Table("payment_card_issuer", DB().metadata, autoload=True)
    channel = relationship("IssuerChannelAssociation", backref="issuer")


class IssuerChannelAssociation(DB().Base):
    __table__ = Table("user_clientapplicationbundle_issuer", DB().metadata, autoload=True)


class SchemeChannelAssociation(DB().Base):
    __table__ = Table("scheme_schemebundleassociation", DB().metadata, autoload=True)


class Scheme(DB().Base):
    __table__ = Table("scheme_scheme", DB().metadata, autoload=True)
    channel_associations = relationship("SchemeChannelAssociation", backref="scheme")
    category = relationship("Category", lazy="joined", backref="scheme")
    consent = relationship("Consent", backref="scheme")
    document = relationship("SchemeDocument", backref="scheme")


class SchemeAccount(DB().Base):
    __table__ = Table("scheme_schemeaccount", DB().metadata, autoload=True)
    scheme_account_user_associations = relationship("SchemeAccountUserAssociation", backref="scheme_account")
    scheme = relationship("Scheme", backref="scheme_account")


class SchemeAccountUserAssociation(DB().Base):
    __table__ = Table("ubiquity_schemeaccountentry", DB().metadata, autoload=True)


class SchemeAccountImage(DB().Base):
    __table__ = Table("scheme_schemeaccountimage", DB().metadata, autoload=True)


class SchemeAccountImageAssociation(DB().Base):
    __table__ = Table("scheme_schemeaccountimage_scheme_accounts", DB().metadata, autoload=True)
    scheme_account = relationship("SchemeAccount", backref="scheme_account_image_association")
    scheme_account_image = relationship("SchemeAccountImage", backref="scheme_account_image_association")


class SchemeCredentialQuestion(DB().Base):
    __table__ = Table("scheme_schemecredentialquestion", DB().metadata, autoload=True)
    scheme_assoc = relationship("Scheme", backref="scheme_credential_question")


class SchemeAccountCredentialAnswer(DB().Base):
    __table__ = Table("scheme_schemeaccountcredentialanswer", DB().metadata, autoload=True)
    scheme_account_entry = relationship("SchemeAccountUserAssociation", backref="scheme_account_credential_answer")
    scheme_credential_question = relationship("SchemeCredentialQuestion", backref="scheme_account_credential_answer")


class PaymentCard(DB().Base):
    __table__ = Table("payment_card_paymentcard", DB().metadata, autoload=True)


class PaymentCardImage(DB().Base):
    __table__ = Table("payment_card_paymentcardimage", DB().metadata, autoload=True)
    payment_card = relationship("PaymentCard", backref="payment_card_image")


class PaymentAccountUserAssociation(DB().Base):
    __table__ = Table("ubiquity_paymentcardaccountentry", DB().metadata, autoload=True)


class PaymentAccount(DB().Base):
    __table__ = Table("payment_card_paymentcardaccount", DB().metadata, autoload=True)
    payment_account_user_assoc = relationship("PaymentAccountUserAssociation", backref="payment_account")
    payment_card = relationship("PaymentCard", backref="payment_account")


class PaymentCardAccountImageAssociation(DB().Base):
    __table__ = Table("payment_card_paymentcardaccountimage_payment_card_accounts", DB().metadata, autoload=True)
    payment_card_account = relationship("PaymentAccount", backref="payment_card_account_image_association")
    payment_card_account_image = relationship(
        "PaymentCardAccountImage", backref="payment_card_account_image_association"
    )


class PaymentCardAccountImage(DB().Base):
    __table__ = Table("payment_card_paymentcardaccountimage", DB().metadata, autoload=True)


class Category(DB().Base):
    __table__ = Table("scheme_category", DB().metadata, autoload=True)


class Consent(DB().Base):
    __table__ = Table("scheme_consent", DB().metadata, autoload=True)


class SchemeDocument(DB().Base):
    __table__ = Table("ubiquity_membershipplandocument", DB().metadata, autoload=True)


class SchemeImage(DB().Base):
    __table__ = Table("scheme_schemeimage", DB().metadata, autoload=True)
    scheme = relationship("Scheme", backref="scheme_image")


class SchemeDetail(DB().Base):
    __table__ = Table("scheme_schemedetail", DB().metadata, autoload=True)
    scheme = relationship("Scheme", backref="scheme_detail")


class SchemeBalanceDetails(DB().Base):
    __table__ = Table("scheme_schemebalancedetails", DB().metadata, autoload=True)
    scheme = relationship("Scheme", backref="scheme_balance_detail")


class SchemeOverrideError(DB().Base):
    __table__ = Table("scheme_schemeoverrideerror", DB().metadata, autoload=True)
    scheme = relationship("Scheme", backref="scheme_override_error")
    channel = relationship("Channel", backref="scheme_override_error")


class SchemeContent(DB().Base):
    __table__ = Table("scheme_schemecontent", DB().metadata, autoload=True)
    scheme = relationship("Scheme", backref="scheme_content")


class ThirdPartyConsentLink(DB().Base):
    __table__ = Table("scheme_thirdpartyconsentlink", DB().metadata, autoload=True)
    scheme = relationship("Scheme", backref="thirdpartylink")
    consent = relationship("Consent", lazy="joined", backref="thirdpartylink")
    client_application = relationship("ClientApplication", backref="thirdpartylink")


class PaymentSchemeAccountAssociation(DB().Base):
    __table__ = Table("ubiquity_paymentcardschemeentry", DB().metadata, autoload=True)
    payment_account = relationship("PaymentAccount", backref="PaymentSchemeAccountAssociation")
    scheme_account = relationship("SchemeAccount", backref="PaymentSchemeAccountAssociation")


class PLLUserAssociation(DB().Base):
    __table__ = Table("ubiquity_plluserassociation", DB().metadata, autoload=True)
    user = relationship("User", backref="PaymentSchemeUserAssociation")
    pll = relationship("PaymentSchemeAccountAssociation", backref="PaymentSchemeUserAssociation")


class ServiceConsent(DB().Base):
    __table__ = Table("ubiquity_serviceconsent", DB().metadata, autoload=True)
    user = relationship("User", backref="service_consent")


def history_after_insert_listener(mapped: mapper, connection, target):
    mapper_history(target, "create", mapped)


def history_after_delete_listener(mapped: mapper, connection, target):
    mapper_history(target, "delete", mapped)


def history_after_update_listener(mapped: mapper, connection, target):
    mapper_history(target, "update", mapped)


watched_classes = [
    User,
    SchemeAccount,
    SchemeAccountUserAssociation,
    PaymentAccount,
    PaymentAccountUserAssociation,
    PaymentSchemeAccountAssociation,
]


for w_class in watched_classes:
    event.listen(w_class, "after_update", history_after_update_listener)
    event.listen(w_class, "after_insert", history_after_insert_listener)
    event.listen(w_class, "after_delete", history_after_delete_listener)
