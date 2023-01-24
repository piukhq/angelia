import typing
from datetime import datetime

import faker

from app.hermes.models import PaymentAccountUserAssociation, SchemeChannelAssociation
from app.lib.images import ImageStatus, ImageTypes
from app.lib.loyalty_card import LoyaltyCardStatus
from tests.factories import (
    ChannelFactory,
    ClientApplicationFactory,
    LoyaltyCardFactory,
    LoyaltyCardUserAssociationFactory,
    LoyaltyErrorOverrideFactory,
    LoyaltyPlanFactory,
    OrganisationFactory,
    PaymentAccountFactory,
    PaymentCardAccountImageAssociationFactory,
    PaymentCardAccountImageFactory,
    PaymentCardFactory,
    PaymentCardImageFactory,
    PaymentSchemeAccountAssociationFactory,
    PLLUserAssociationFactory,
    SchemeAccountImageAssociationFactory,
    SchemeAccountImageFactory,
    SchemeImageFactory,
    UserFactory,
)

if typing.TYPE_CHECKING:
    from sqlalchemy.orm import Session

fake = faker.Faker()


def setup_database(db_session: "Session") -> tuple:
    channels = {}
    users = {}

    for name in ["bank1", "bank2", "bank3"]:
        org = OrganisationFactory(name=name)
        bundle_id = f"com.{name}.test"
        client = ClientApplicationFactory(organisation=org, name=name, client_id=f"213124_{name}_3883248")
        channels[bundle_id] = ChannelFactory(bundle_id=bundle_id, client_application=client)
        for i in range(0, 3):
            users[f"{name}_{i}"] = UserFactory(client=channels[bundle_id].client_application)
            db_session.flush()
    db_session.commit()
    return channels, users


def set_up_loyalty_plans(db_session: "Session", channels: dict) -> dict:
    loyalty_plans = {}

    for slug in ["merchant_1", "merchant_2"]:
        loyalty_plans[slug] = LoyaltyPlanFactory(slug=slug)
        db_session.flush()

    for slug, plan in loyalty_plans.items():
        for bundle_id, channel in channels.items():
            sca = SchemeChannelAssociation(status=0, bundle_id=channel.id, scheme_id=plan.id, test_scheme=False)
            db_session.add(sca)

    db_session.commit()
    return loyalty_plans


def set_up_payment_cards(db_session: "Session") -> dict:
    payment_cards = {}

    for slug in ["bankcard1", "bankcard2"]:
        payment_cards[slug] = PaymentCardFactory(slug=slug)
        db_session.flush()

    db_session.commit()
    return payment_cards


def setup_loyalty_cards(
    db_session: "Session",
    users: dict,
    loyalty_plans: dict,
    balances: list = None,
    vouchers: list = None,
    transactions: list = None,
    for_user: str = None,
) -> dict:
    loyalty_cards = {}

    # Add a loyalty card for each user
    for user_name, user in users.items():
        card_number = f"951114320013354045551{user.id}"
        loyalty_cards[user_name] = {}
        if for_user == user_name:
            set_balances = balances
            set_vouchers = vouchers
            set_transactions = transactions
        else:
            if balances:
                set_balances = balances
                set_vouchers = set_transactions = []
            else:
                set_balances = set_vouchers = set_transactions = []
        loyalty_cards[user_name]["merchant_1"] = LoyaltyCardFactory(
            scheme=loyalty_plans["merchant_1"],
            card_number=card_number,
            balances=set_balances,
            vouchers=set_vouchers,
            transactions=set_transactions,
        )
        db_session.flush()
        LoyaltyCardUserAssociationFactory(
            scheme_account_id=loyalty_cards[user_name]["merchant_1"].id,
            user_id=user.id,
            link_status=LoyaltyCardStatus.ACTIVE,
        )
        db_session.flush()
        card_number = f"951114320013354045552{user.id}"
        loyalty_cards[user_name]["merchant_2"] = LoyaltyCardFactory(
            scheme=loyalty_plans["merchant_2"],
            card_number=card_number,
            balances=set_balances,
        )
        db_session.flush()
        LoyaltyCardUserAssociationFactory(
            scheme_account_id=loyalty_cards[user_name]["merchant_2"].id,
            user_id=user.id,
            link_status=LoyaltyCardStatus.WALLET_ONLY,
        )
        db_session.flush()
    db_session.commit()
    return loyalty_cards


def setup_loyalty_scheme_override(
    db_session: "Session", loyalty_plan_id: int, channel_id: int, error_code: int
) -> dict:
    override = LoyaltyErrorOverrideFactory(scheme_id=loyalty_plan_id, channel_id=channel_id, error_code=error_code)
    db_session.flush()
    error_override = {
        "loyalty": override.scheme_id,
        "slug": override.error_slug,
        "error_code": override.error_code,
        "message": override.message,
        "channel": override.channel_id,
    }

    return error_override


def setup_payment_accounts(db_session: "Session", users: dict, payment_cards: dict) -> dict:
    payment_accounts = {}
    # Add a payment account for each user
    for user_name, user in users.items():
        payment_accounts[user_name] = {}
        bank, _ = user_name.split("_", 1)
        for bankcard, payment_card in payment_cards.items():
            payment_account = PaymentAccountFactory(
                payment_card=payment_card, status=1, name_on_card=fake.name(), issuer_name=bank, card_nickname=bankcard
            )
            db_session.flush()
            payment_account_user_association = PaymentAccountUserAssociation(
                payment_card_account_id=payment_account.id, user_id=user.id
            )
            db_session.add(payment_account_user_association)
            payment_accounts[user_name][payment_account.id] = payment_account

    db_session.commit()
    return payment_accounts


def setup_loyalty_card_images(
    db_session: "Session",
    loyalty_plans: dict,
    image_type: ImageTypes,
    status: ImageStatus,
    start_date: datetime,
    end_date: datetime,
    reward_tier: int = 0,
) -> dict:
    loyalty_card_images = {}
    for loyalty_plan_slug, loyalty_plan in loyalty_plans.items():
        enc = fake.random.choice(["jpg", "png"])
        loyalty_card_images[loyalty_plan_slug] = SchemeImageFactory(
            scheme=loyalty_plan,
            image_type_code=image_type,
            status=status,
            start_date=start_date,
            end_date=end_date,
            image=f"{fake.word()}.{enc}",
            encoding=enc,
            description=fake.sentences(),
            url=fake.url(),
            reward_tier=reward_tier,
        )
        db_session.flush()
    db_session.commit()
    return loyalty_card_images


def setup_loyalty_account_images(
    db_session: "Session",
    loyalty_cards: dict,
    image_type: ImageTypes,
    status: ImageStatus,
    start_date: datetime,
    end_date: datetime,
    reward_tier: int = 0,
) -> dict:
    loyalty_account_images = {}
    for user, merchant_loyalty in loyalty_cards.items():
        loyalty_account_images[user] = {}
        enc = fake.random.choice(["jpg", "png"])
        for merchant, loyalty_account in merchant_loyalty.items():
            loyalty_account_images[user][merchant] = SchemeAccountImageFactory(
                image_type_code=image_type,
                status=status,
                start_date=start_date,
                end_date=end_date,
                image=f"{fake.word()}.{enc}",
                encoding=enc,
                description=fake.sentences(),
                url=fake.url(),
                reward_tier=reward_tier,
            )

            db_session.flush()
            SchemeAccountImageAssociationFactory(
                schemeaccount_id=loyalty_account.id, schemeaccountimage_id=loyalty_account_images[user][merchant].id
            )
            db_session.flush()

    db_session.commit()
    return loyalty_account_images


def setup_payment_card_images(
    db_session: "Session",
    payment_cards: dict,
    image_type: ImageTypes,
    status: ImageStatus,
    start_date: datetime,
    end_date: datetime,
) -> dict:
    payment_card_images = {}
    for payment_card_slug, payment_card in payment_cards.items():
        enc = fake.random.choice(["jpg", "png"])
        payment_card_images[payment_card_slug] = PaymentCardImageFactory(
            payment_card=payment_card,
            image_type_code=image_type,
            status=status,
            start_date=start_date,
            end_date=end_date,
            image=f"{fake.word()}.{enc}",
            encoding=enc,
            description=fake.sentences(),
            url=fake.url(),
        )
        db_session.flush()
    db_session.commit()
    return payment_card_images


def setup_payment_card_account_images(
    db_session: "Session",
    payment_accounts: dict,
    image_type: ImageTypes,
    status: ImageStatus,
    start_date: datetime,
    end_date: datetime,
) -> dict:
    payment_card_images = {}
    for user, bank_card in payment_accounts.items():
        payment_card_images[user] = {}
        for bankcard, account in bank_card.items():
            enc = fake.random.choice(["jpg", "png"])
            account_image = PaymentCardAccountImageFactory(
                image_type_code=image_type,
                status=status,
                start_date=start_date,
                end_date=end_date,
                image=f"{fake.word()}.{enc}",
                encoding=enc,
                description=fake.sentences(),
                url=fake.url(),
            )
            db_session.flush()
            PaymentCardAccountImageAssociationFactory(
                paymentcardaccount_id=account.id, paymentcardaccountimage_id=account_image.id
            )
            payment_card_images[user][account.id] = account_image
            db_session.flush()
    db_session.commit()
    return payment_card_images


def setup_pll_links(db_session: "Session", payment_accounts: dict, loyalty_accounts: dict, users: dict) -> dict:
    # loyalty_cards[user_name]["merchant_2"]
    # payment_accounts[user_name][payment_account.id] = payment_account
    pll_links = {}
    for user_name, payment_account_by_id in payment_accounts.items():
        user = users[user_name]
        pll_links[user_name] = {}
        loyalty_by_scheme_name = loyalty_accounts[user_name]
        for scheme_name, scheme_account in loyalty_by_scheme_name.items():
            pll_links[user_name][scheme_name] = {}
            for scheme_associations in scheme_account.scheme_account_user_associations:
                pll_links[user_name][scheme_name][scheme_associations.id] = {}
                for pay_id, payment_account in payment_account_by_id.items():
                    # should check status of scheme_association and payment_account to set active_link, slug and state
                    active_link = True
                    base_link = PaymentSchemeAccountAssociationFactory(
                        payment_card_account=payment_account, scheme_account=scheme_account, active_link=active_link
                    )
                    db_session.flush()
                    pll = PLLUserAssociationFactory(pll=base_link, user=user)
                    db_session.flush()
                    pll_links[user_name][scheme_name][scheme_associations.id][pay_id] = pll

    db_session.commit()
    return pll_links
