import base64
import os
import uuid

import factory
import faker
from factory.fuzzy import FuzzyAttribute

from app.handlers.loyalty_card import LoyaltyCardHandler
from app.handlers.payment_account import PaymentAccountHandler
from app.hermes.models import ClientApplication, Organisation, PaymentAccount, PaymentCard, User, SchemeAccount, \
    Category, SchemeCredentialQuestion, Scheme, SchemeChannelAssociation, Channel
from tests import common

fake = faker.Faker()


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


class LoyaltyCardHandlerFactory(factory.Factory):
    class Meta:
        model = LoyaltyCardHandler

    user_id = (1,)
    channel_id = ("com.test.channel",)
    loyalty_plan_id = (1, )


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


class ChannelFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Channel
        sqlalchemy_session = common.Session

    bundle_id = "com.test.channel"
    client_application = factory.SubFactory(ClientApplicationFactory)
    magic_lifetime = 60
    magic_link_url = ""
    external_name = ""
    subject = ""


class CategoryFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Category
        sqlalchemy_session = common.Session

    name = "Test Category"


class LoyaltyPlanChannelAssociationFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = SchemeChannelAssociation

    status = 0
    channel = factory.SubFactory(ChannelFactory)


class LoyaltyPlanFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Scheme
        sqlalchemy_session = common.Session

    category = factory.SubFactory(CategoryFactory)
    name = fake.company() + ' Rewards'
    slug = fake.slug()
    url = "https://www.testcompany244123.co.uk/testcompany"
    company = fake.company()
    company_url = fake.url()
    scan_message = fake.sentence()
    forgotten_password_url = fake.url()
    identifier = ""
    has_transactions = True
    has_points = True
    tier = 3
    colour = fake.color()
    barcode_regex = ""
    card_number_regex = ""
    barcode_prefix = ""
    card_number_prefix = ""
    transaction_headers = ["header 1", "header 2", "header 3"]
    point_name = "pts"
    android_app_id = ""
    ios_scheme = ""
    itunes_url = ""
    play_store_url = ""
    max_points_value_length = 100
    join_url = ""
    link_account_text = ""
    join_t_and_c = ""
    authorisation_required = False
    digital_only = False
    enrol_incentive = ""
    plan_description = ""
    plan_summary = ""
    barcode_redeem_instructions = ""
    plan_register_info = ""
    linking_support = {}
    formatted_images = {}
    secondary_colour = ""


class LoyaltyCardFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = SchemeAccount
        sqlalchemy_session = common.Session

    scheme = factory.SubFactory(LoyaltyPlanFactory)
    status = 0
    order = 0
    created = fake.date_time()
    updated = fake.date_time()
    is_deleted = False
    link_date = fake.date_time()
    balances = {}
    vouchers = {}
    card_number = fake.credit_card_number()
    barcode = ""
    transactions = {}
    main_answer = card_number
    pll_links = []
    formatted_images = {}


class LoyaltyPlanQuestionFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = SchemeCredentialQuestion
        sqlalchemy_session = common.Session

    scheme_id = factory.SubFactory(LoyaltyPlanFactory)
    type = 'card_number'
    label = 'Card Number'
    third_party_identifier = False
    manual_question = False
    scan_question = False
    one_question_link = False
    add_field = False
    auth_field = False
    enrol_field = False
    register_field = False
    order = 0
    options = 0
    description = ""
    validation = ""
    answer_type = 0


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
