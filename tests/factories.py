import base64
import datetime
import os
import random
import uuid

import factory
import faker
from factory.fuzzy import FuzzyAttribute

from app.handlers.loyalty_card import ADD, LoyaltyCardHandler
from app.handlers.loyalty_plan import LoyaltyPlanHandler, LoyaltyPlansHandler
from app.handlers.payment_account import PaymentAccountHandler, PaymentAccountUpdateHandler
from app.handlers.user import UserHandler
from app.hermes.models import (
    Category,
    Channel,
    ClientApplication,
    Consent,
    Organisation,
    PaymentAccount,
    PaymentCard,
    PaymentCardAccountImage,
    PaymentCardAccountImageAssociation,
    PaymentCardImage,
    Scheme,
    SchemeAccount,
    SchemeAccountCredentialAnswer,
    SchemeAccountImage,
    SchemeAccountImageAssociation,
    SchemeAccountUserAssociation,
    SchemeChannelAssociation,
    SchemeContent,
    SchemeCredentialQuestion,
    SchemeDetail,
    SchemeDocument,
    SchemeImage,
    SchemeOverrideError,
    ServiceConsent,
    ThirdPartyConsentLink,
    User,
)
from app.lib.images import ImageStatus, ImageTypes
from app.lib.loyalty_card import LoyaltyCardStatus, OriginatingJourney
from tests import common

fake = faker.Faker("en_GB")


class OrganisationFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Organisation
        sqlalchemy_session = common.Session

    name = fake.slug()
    terms_and_conditions = fake.paragraph(nb_sentences=5)


class ClientApplicationFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = ClientApplication
        sqlalchemy_session = common.Session

    name = fake.text(max_nb_chars=100)
    organisation = factory.SubFactory(OrganisationFactory)
    client_id = fake.slug()
    secret = FuzzyAttribute(uuid.uuid4)


class LoyaltyPlanHandlerFactory(factory.Factory):
    class Meta:
        model = LoyaltyPlanHandler

    user_id = 1
    channel_id = "com.test.channel"
    loyalty_plan_id = 1


class LoyaltyPlansHandlerFactory(factory.Factory):
    class Meta:
        model = LoyaltyPlansHandler

    user_id = 1
    channel_id = "com.test.channel"


class LoyaltyCardUserAssociationFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = SchemeAccountUserAssociation
        sqlalchemy_session = common.Session

    scheme_account_id = 1
    user_id = 1
    auth_provided = False


class LoyaltyCardHandlerFactory(factory.Factory):
    class Meta:
        model = LoyaltyCardHandler

    user_id = 1
    channel_id = "com.test.channel"
    loyalty_plan_id = 1
    all_answer_fields = {}
    journey = ADD
    link_to_user = None


class UserHandlerFactory(factory.Factory):
    class Meta:
        model = UserHandler

    user_id = 1
    channel_id = "com.test.channel"


class PaymentAccountHandlerFactory(factory.Factory):
    class Meta:
        model = PaymentAccountHandler

    user_id = 1
    channel_id = "com.test.channel"
    expiry_month = f"{fake.random.randint(0, 12)}"
    expiry_year = f"{fake.random.randint(2010, 2100)}"
    token = fake.password(length=40, special_chars=False)
    last_four_digits = f"{fake.credit_card_number()[:4]}"
    first_six_digits = f"{fake.credit_card_number()[-6:]}"
    fingerprint = fake.password(length=40, special_chars=False)


class PaymentAccountUpdateHandlerFactory(factory.Factory):
    class Meta:
        model = PaymentAccountUpdateHandler

    user_id = 1
    channel_id = "com.test.channel"
    expiry_month = f"{fake.random.randint(0, 12)}"
    expiry_year = f"{fake.random.randint(2010, 2100)}"
    card_nickname = fake.name()
    name_on_card = fake.name()
    issuer = fake.company()


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
    refresh_token_lifetime = 900
    access_token_lifetime = 900
    email_required = True


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
    name = fake.company() + " Rewards"
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
    text_colour = ""
    balance_renew_period = 1200


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
    alt_main_answer = ""
    pll_links = []
    formatted_images = {}
    originating_journey = OriginatingJourney.UNKNOWN


class LoyaltyErrorOverrideFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = SchemeOverrideError
        sqlalchemy_session = common.Session

    scheme_id = factory.SubFactory(LoyaltyPlanFactory)
    error_code = LoyaltyCardStatus.UNKNOWN_ERROR
    reason_code = "X101"
    error_slug = "UNKNOWN_ERROR"
    message = "test message"
    channel_id = factory.SubFactory(ChannelFactory)


class LoyaltyPlanQuestionFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = SchemeCredentialQuestion
        sqlalchemy_session = common.Session

    scheme_id = factory.SubFactory(LoyaltyPlanFactory)
    type = "card_number"
    label = "Card Number"
    third_party_identifier = False
    manual_question = False
    scan_question = False
    one_question_link = False
    add_field = False
    auth_field = False
    enrol_field = False
    register_field = False
    order = random.randint(0, 9)
    options = 0
    description = ""
    validation = ""
    answer_type = 0


class LoyaltyCardAnswerFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = SchemeAccountCredentialAnswer
        sqlalchemy_session = common.Session

    answer = ""
    scheme_account_entry_id = 1
    question_id = 1


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
    card_nickname = fake.name()
    issuer_name = fake.company()


class PaymentCardImageFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = PaymentCardImage
        sqlalchemy_session = common.Session

    payment_card = factory.SubFactory(PaymentCardFactory)
    image_type_code = random.choice(list(ImageTypes))
    size_code = ""
    strap_line = ""
    description = fake.sentences()
    url = fake.url()
    call_to_action = fake.text(max_nb_chars=150)
    order = fake.random_int(min=0, max=20)
    status = 1
    start_date = fake.date()
    end_date = fake.date()
    created = fake.date()
    image = fake.word() + fake.random.choice([".jpg", ".png"])
    reward_tier = 0
    encoding = ""
    dark_mode_image = ""
    dark_mode_url = fake.url()


class PaymentCardAccountImageFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = PaymentCardAccountImage
        sqlalchemy_session = common.Session

    image_type_code = random.choice(list(ImageTypes))
    size_code = ""
    strap_line = ""
    description = fake.sentences()
    url = fake.url()
    call_to_action = fake.text(max_nb_chars=150)
    order = fake.random_int(min=0, max=20)
    status = 1
    start_date = fake.date()
    end_date = fake.date()
    created = fake.date()
    image = fake.word() + fake.random.choice([".jpg", ".png"])
    reward_tier = 0
    encoding = ""
    dark_mode_image = ""
    dark_mode_url = fake.url()


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
    delete_token = ""


class ServiceConsentFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = ServiceConsent
        sqlalchemy_session = common.Session

    user_id = factory.SubFactory(UserFactory)
    latitude = 0.0
    longitude = 0.0
    timestamp = fake.date_time()


class DocumentFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = SchemeDocument
        sqlalchemy_session = common.Session

    scheme = factory.SubFactory(LoyaltyPlanFactory)
    order = random.randint(0, 9)
    name = "Test Document"
    description = "This is a test plan document"
    url = "https://testdocument.com"
    display = {"ADD", "ENROL"}
    checkbox = True


class ConsentFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Consent
        sqlalchemy_session = common.Session

    scheme = factory.SubFactory(LoyaltyPlanFactory)
    check_box = True
    text = "This is some really descriptive text right here"
    is_enabled = True
    required = False
    order = random.randint(0, 9)
    journey = 0
    slug = fake.slug()
    created_on = datetime.datetime.now()
    modified_on = datetime.datetime.now()


class ThirdPartyConsentLinkFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = ThirdPartyConsentLink
        sqlalchemy_session = common.Session

    scheme = factory.SubFactory(LoyaltyPlanFactory)
    consent = factory.SubFactory(ConsentFactory)
    consent_label = "Consent_label"
    add_field = False
    auth_field = False
    enrol_field = False
    register_field = False
    client_application = factory.SubFactory(ClientApplicationFactory)


class SchemeImageFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = SchemeImage
        sqlalchemy_session = common.Session

    scheme = factory.SubFactory(LoyaltyPlanFactory)
    # plan overview tests for icons explicitly so remove icon as a default to prevent issues with those tests
    image_type_code = random.choice([img_type for img_type in ImageTypes if img_type != ImageTypes.ICON])
    size_code = ""
    strap_line = ""
    description = fake.sentences()
    url = fake.url()
    call_to_action = fake.text(max_nb_chars=150)
    order = fake.random_int(min=0, max=20)
    status = ImageStatus.PUBLISHED
    start_date = datetime.datetime.now()
    end_date = datetime.datetime.now() + datetime.timedelta(minutes=15)
    created = fake.date()
    image = fake.word() + fake.random.choice([".jpg", ".png"])
    reward_tier = 0
    encoding = ""
    dark_mode_image = ""
    dark_mode_url = fake.url()


class SchemeAccountImageFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = SchemeAccountImage
        sqlalchemy_session = common.Session

    image_type_code = random.choice(list(ImageTypes))
    size_code = ""
    strap_line = ""
    description = fake.sentences()
    url = fake.url()
    call_to_action = fake.text(max_nb_chars=150)
    order = fake.random_int(min=0, max=20)
    status = 1
    start_date = fake.date()
    end_date = fake.date()
    created = fake.date()
    image = fake.word() + fake.random.choice([".jpg", ".png"])
    reward_tier = 0
    encoding = ""
    dark_mode_image = ""
    dark_mode_url = fake.url()


class SchemeDetailFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = SchemeDetail
        sqlalchemy_session = common.Session

    scheme = factory.SubFactory(LoyaltyPlanFactory)
    type = 0
    name = fake.word()
    description = fake.sentences()


class SchemeContentFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = SchemeContent
        sqlalchemy_session = common.Session

    scheme = factory.SubFactory(LoyaltyPlanFactory)
    column = fake.word()
    value = fake.sentences()


class SchemeAccountImageAssociationFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = SchemeAccountImageAssociation
        sqlalchemy_session = common.Session

    schemeaccount_id = 1
    schemeaccountimage_id = 1


class PaymentCardAccountImageAssociationFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = PaymentCardAccountImageAssociation
        sqlalchemy_session = common.Session

    paymentcardaccount_id = 1
    paymentcardaccountimage_id = 1
