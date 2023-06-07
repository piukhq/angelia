from __future__ import annotations

import contextlib
from datetime import datetime
from typing import TYPE_CHECKING
from urllib.parse import urljoin

from sqlalchemy import and_, literal, or_, select, union_all
from sqlalchemy.orm import Session

from app.hermes.models import (
    Channel,
    PaymentAccount,
    PaymentAccountUserAssociation,
    PaymentCardAccountImage,
    PaymentCardAccountImageAssociation,
    PaymentCardImage,
    SchemeAccount,
    SchemeAccountImage,
    SchemeAccountImageAssociation,
    SchemeAccountUserAssociation,
    SchemeChannelAssociation,
    SchemeImage,
)
from app.lib.images import ImageStatus, ImageTypes
from settings import CUSTOM_DOMAIN

if TYPE_CHECKING:
    from sqlalchemy.sql.selectable import Select


def query_scheme_account_images(user_id: int, loyalty_card_index: dict, show_type: ImageTypes | None = None) -> Select:
    account_list = list(loyalty_card_index.keys())

    select_query = (
        select(
            SchemeAccountImage.id,
            SchemeAccountImage.image_type_code.label("type"),
            SchemeAccountImage.image.label("url"),
            SchemeAccountImage.call_to_action.label("cta_url"),
            SchemeAccountImage.description,
            SchemeAccountImage.encoding,
            SchemeAccountImage.reward_tier,
            SchemeAccount.scheme_id.label("plan_id"),
            SchemeAccountImageAssociation.schemeaccount_id.label("account_id"),
            literal("scheme").label("table_type"),
        )
        .join(
            SchemeAccountImageAssociation,
            SchemeAccountImageAssociation.schemeaccountimage_id == SchemeAccountImage.id,
        )
        .join(SchemeAccount, SchemeAccount.id == SchemeAccountImageAssociation.schemeaccount_id)
        .join(
            SchemeAccountUserAssociation,
            and_(
                SchemeAccountUserAssociation.scheme_account_id == SchemeAccountImageAssociation.schemeaccount_id,
                SchemeAccountUserAssociation.user_id == user_id,
                SchemeAccountUserAssociation.scheme_account_id.in_(account_list),
            ),
        )
        .where(
            SchemeAccount.is_deleted.is_(False),
            SchemeAccountImage.start_date <= datetime.now(),
            SchemeAccountImage.status != ImageStatus.DRAFT,
            SchemeAccountImage.image_type_code != ImageTypes.ALT_HERO,
            or_(SchemeAccountImage.end_date.is_(None), SchemeAccountImage.end_date >= datetime.now()),
        )
    )

    if show_type is not None:
        select_query = select_query.where(
            or_(SchemeAccountImage.image_type_code == show_type, SchemeAccountImage.image_type_code == ImageTypes.TIER)
        )

    return select_query


def query_scheme_images(channel_id: str, loyalty_card_index: dict, show_type: ImageTypes | None = None) -> Select:
    # get Unique list of card_ids
    plan_list = list(set(loyalty_card_index.values()))

    select_query = (
        select(
            SchemeImage.id,
            SchemeImage.image_type_code.label("type"),
            SchemeImage.image.label("url"),
            SchemeImage.call_to_action.label("cta_url"),
            SchemeImage.description,
            SchemeImage.encoding,
            SchemeImage.reward_tier,
            SchemeImage.scheme_id.label("plan_id"),
            None,
            literal("scheme").label("table_type"),
        )
        .join(SchemeChannelAssociation, SchemeChannelAssociation.scheme_id == SchemeImage.scheme_id)
        .join(Channel, and_(Channel.id == SchemeChannelAssociation.bundle_id, Channel.bundle_id == channel_id))
        .where(
            SchemeImage.scheme_id.in_(plan_list),
            SchemeImage.start_date <= datetime.now(),
            SchemeImage.status != ImageStatus.DRAFT,
            SchemeImage.image_type_code != ImageTypes.ALT_HERO,
            or_(SchemeImage.end_date.is_(None), SchemeImage.end_date >= datetime.now()),
        )
    )

    if show_type is not None:
        select_query = select_query.where(
            or_(SchemeImage.image_type_code == show_type, SchemeImage.image_type_code == ImageTypes.TIER)
        )

    return select_query


def query_card_account_images(user_id: int, pay_card_index: dict, show_type: ImageTypes | None = None) -> Select:
    account_list = list(pay_card_index.keys())

    select_query = (
        select(
            PaymentCardAccountImage.id,
            PaymentCardAccountImage.image_type_code.label("type"),
            PaymentCardAccountImage.image.label("url"),
            literal(None).label("cta_url"),
            PaymentCardAccountImage.description,
            PaymentCardAccountImage.encoding,
            PaymentCardAccountImage.reward_tier,
            PaymentAccount.payment_card_id.label("plan_id"),
            PaymentCardAccountImageAssociation.paymentcardaccount_id.label("account_id"),
            literal("payment").label("table_type"),
        )
        .join(
            PaymentCardAccountImageAssociation,
            PaymentCardAccountImageAssociation.paymentcardaccountimage_id == PaymentCardAccountImage.id,
        )
        .join(PaymentAccount, PaymentAccount.id == PaymentCardAccountImageAssociation.paymentcardaccount_id)
        .join(
            PaymentAccountUserAssociation,
            and_(
                PaymentAccountUserAssociation.payment_card_account_id
                == PaymentCardAccountImageAssociation.paymentcardaccount_id,
                PaymentAccountUserAssociation.user_id == user_id,
                PaymentAccountUserAssociation.payment_card_account_id.in_(account_list),
            ),
        )
        .where(
            PaymentAccount.is_deleted.is_(False),
            PaymentCardAccountImage.start_date <= datetime.now(),
            PaymentCardAccountImage.status != ImageStatus.DRAFT,
            PaymentCardAccountImage.image_type_code != ImageTypes.ALT_HERO,
            or_(PaymentCardAccountImage.end_date.is_(None), PaymentCardAccountImage.end_date >= datetime.now()),
        )
    )
    if show_type is not None:
        select_query = select_query.where(PaymentCardAccountImage.image_type_code == show_type)
    return select_query


def query_payment_card_images(pay_card_index: dict, show_type: ImageTypes | None = None) -> Select:
    # get Unique list of card_ids
    plan_list = list(set(pay_card_index.values()))

    select_query = select(
        PaymentCardImage.id,
        PaymentCardImage.image_type_code.label("type"),
        PaymentCardImage.image.label("url"),
        literal(None).label("cta_url"),
        PaymentCardImage.description,
        PaymentCardImage.encoding,
        PaymentCardImage.reward_tier,
        PaymentCardImage.payment_card_id.label("plan_id"),
        None,
        literal("payment").label("table_type"),
    ).where(
        PaymentCardImage.payment_card_id.in_(plan_list),
        PaymentCardImage.start_date <= datetime.now(),
        PaymentCardImage.status != ImageStatus.DRAFT,
        PaymentCardImage.image_type_code != ImageTypes.ALT_HERO,
        or_(PaymentCardImage.end_date.is_(None), PaymentCardImage.end_date >= datetime.now()),
    )

    if show_type is not None:
        select_query = select_query.where(PaymentCardImage.image_type_code == show_type)

    return select_query


def query_all_images(  # noqa: PLR0913
    db_session: Session,
    user_id: int,
    channel_id: str,
    loyalty_card_index: dict,
    pay_card_index: dict,
    show_type: ImageTypes | None = None,
    included_payment: bool = True,
    included_scheme: bool = True,
) -> dict:
    """
    If included_payment and  included_scheme are true 4 image tables are searched and combined into
    Loyalty_card_index and pay_card_index restricts finding images related to listed accounts and plans and by the
    type of image (show_type).
    However, channel, user_id and account ownership is filtered for and an image is excluded if status is draft
    or if the start date is set in the future or if end date is set and has passed.

    Note: Both scheme and payment images have 2 tables one for the account and the other
    for the scheme.  Account images override scheme images for same type and have a 10,000,000 offset on
    the id field in order to avoid duplicating ids on the api response.

    Note: For wallet both payment and scheme are required but in future other endpoints may require  one or the other.

    Note: The index inputs i.e. loyalty_card_index and pay_card_index are by account id. They could have been by
    plan id and only used for restricting the plan queries. For wallet it is not required to filter by a list of
    account ids as all accounts are included.  However, at time of writing the accounts do have this  filter
    applied for consistency and to make this a general utility.

    :param pay_card_index:  card account ids and associated plan id - queries only listed items if permitted
    :param loyalty_card_index: loyalty account ids and associated plan id - queries only listed items if permitted
    :param included_scheme:   Query scheme images if true
    :param included_payment:  Query payment images if true
    :param channel_id: Channel / bundle_id
    :param user_id: User table id
    :param db_session: Database session
    :param show_type: Either None for all types or an image type to restrict to one type
    :return: dictionary of the types of images required
    """

    select_list = []
    if included_payment:
        select_list += [
            query_card_account_images(user_id, pay_card_index, show_type),
            query_payment_card_images(pay_card_index, show_type),
        ]

    if included_scheme:
        select_list += [
            query_scheme_account_images(user_id, loyalty_card_index, show_type),
            query_scheme_images(channel_id, loyalty_card_index, show_type),
        ]

    u = union_all(*select_list)
    results = db_session.execute(u).all()

    return process_images_query(results)


def process_images_query(query: list) -> dict:
    """
    Since all images are queried in one go we need a data structure which can be used to find images
    when processing the relevant API output fields.
    Since the account and plan type tables are merged for both scheme and payment the ids for
    accounts are increased by 10,000,000 to avoid collision with the plan ids

    :param query:   image query result union to 4 image tables queried
    :return: dict structure for easy look up
    """
    images_data: dict[str, dict] = {}
    for image in query:
        image_dict = dict(image)
        image_type = image_dict.get("type")
        # pop fields not required in images output
        account_id = image_dict.pop("account_id", None)
        plan_id = image_dict.pop("plan_id", None)
        table_type = image_dict.pop("table_type", "unknown")

        if image_dict:
            if not image_dict.get("encoding"):
                with contextlib.suppress(IndexError, AttributeError):
                    image_dict["encoding"] = image_dict["url"].split(".")[-1].replace("/", "")

            if not images_data.get(table_type):
                images_data[table_type] = {}
            if not images_data[table_type].get(image_type):
                images_data[table_type][image_type] = {"account": {}, "plan": {}}
            if account_id is None:
                if not images_data[table_type][image_type]["plan"].get(plan_id):
                    images_data[table_type][image_type]["plan"][plan_id] = []
                images_data[table_type][image_type]["plan"][plan_id].append(image_dict)
            else:
                if not images_data[table_type][image_type]["account"].get(account_id):
                    images_data[table_type][image_type]["account"][account_id] = []
                image_dict["id"] += 10000000

                images_data[table_type][image_type]["account"][account_id].append(image_dict)

            image_dict["url"] = urljoin(f"{CUSTOM_DOMAIN}/", image_dict.get("url"))

    return images_data
