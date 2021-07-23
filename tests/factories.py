import base64
import os
import uuid

import factory
import faker
from factory.fuzzy import FuzzyAttribute

from app.handlers.payment_account import PaymentAccountHandler
from app.hermes.models import ClientApplication, Organisation, PaymentAccount, PaymentCard, User
from tests import common

fake = faker.Faker()


class PaymentAccountHandlerFactory(factory.Factory):
    class Meta:
        model = PaymentAccountHandler

    user_id = (1,)
    channel_id = ("com.test.channel",)
    expiry_month = f"{fake.random.randint(0, 12)}"
    expiry_year = f"{fake.random.randint(2010, 2100)}"
    token = fake.password(length=40, special_chars=False)
    last_four_digits = f"{fake.credit_card_number()[:4]}"
    first_six_digits = f"{fake.credit_card_number()[-6:]}"
    fingerprint = fake.password(length=40, special_chars=False)


class PaymentCardFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = PaymentCard
        sqlalchemy_session = common.Session

    name = fake.word()
    slug = FuzzyAttribute(fake.slug)
    url = fake.url()
    scan_message = fake.bs()
    input_label = fake.bs()
    system = "visa"
    type = "visa"
    is_active = True
    token_method = 0
    formatted_images = {}


class PaymentAccountFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = PaymentAccount
        sqlalchemy_session = common.Session

    payment_card = factory.SubFactory(PaymentCardFactory)
    name_on_card = fake.name()
    start_month = fake.month()
    start_year = fake.month()
    expiry_month = fake.month()
    expiry_year = fake.month()
    pan_start = "111111"
    pan_end = "2222"
    order = 0
    fingerprint = FuzzyAttribute(uuid.uuid4)
    token = FuzzyAttribute(uuid.uuid4)
    status = 0
    created = fake.date_time()
    updated = fake.date_time()
    country = "GB"
    currency_code = "GBP"
    is_deleted = False
    psp_token = FuzzyAttribute(uuid.uuid4)
    consents = []
    pll_links = []
    formatted_images = {}
    card_nickname = ""
    issuer_name = ""


class OrganisationFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Organisation
        sqlalchemy_session = common.Session

    name = fake.text(max_nb_chars=100)
    terms_and_conditions = fake.paragraph(nb_sentences=5)


class ClientApplicationFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = ClientApplication
        sqlalchemy_session = common.Session

    name = fake.text(max_nb_chars=100)
    organisation = factory.SubFactory(OrganisationFactory)
    client_id = fake.slug()
    secret = FuzzyAttribute(uuid.uuid4)


class UserFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = User
        sqlalchemy_session = common.Session

    email = FuzzyAttribute(fake.email)
    external_id = ""
    password = fake.password()
    is_active = True
    is_staff = False
    is_superuser = False
    is_tester = False
    salt = base64.b64encode(os.urandom(16))[:8].decode("utf-8")
    date_joined = fake.date_time()
    uid = FuzzyAttribute(uuid.uuid4)
    client = factory.SubFactory(ClientApplicationFactory)
    delete_token = FuzzyAttribute(uuid.uuid4)
