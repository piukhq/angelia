from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from sqlalchemy.sql.selectable import Select


def query_scheme_account_images(user_id: int, show_type: ImageTypes = None) -> Select:
    select_query = (
        select(
            SchemeAccountImage.id,
            SchemeAccountImage.image_type_code.label("type"),
            SchemeAccountImage.image.label("url"),
            SchemeAccountImage.description,
            SchemeAccountImage.encoding,
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
            ),
        )
        .where(
            SchemeAccount.is_deleted.is_(False),
            SchemeAccountImage.start_date <= datetime.now(),
            SchemeAccountImage.status != ImageStatus.DRAFT,
            or_(SchemeAccountImage.end_date.is_(None), SchemeAccountImage.end_date >= datetime.now()),
        )
    )

    if show_type is not None:
        select_query = select_query.where(SchemeAccountImage.image_type_code == show_type)

    return select_query


def query_scheme_images(channel_id: str, show_type: ImageTypes = None) -> Select:
    select_query = (
        select(
            SchemeImage.id,
            SchemeImage.image_type_code.label("type"),
            SchemeImage.image.label("url"),
            SchemeImage.description,
            SchemeImage.encoding,
            SchemeImage.scheme_id.label("plan_id"),
            None,
            literal("scheme").label("table_type"),
        )
        .join(SchemeChannelAssociation, SchemeChannelAssociation.scheme_id == SchemeImage.scheme_id)
        .join(Channel, and_(Channel.id == SchemeChannelAssociation.bundle_id, Channel.bundle_id == channel_id))
        .where(
            SchemeImage.start_date <= datetime.now(),
            SchemeImage.status != ImageStatus.DRAFT,
            or_(SchemeImage.end_date.is_(None), SchemeImage.end_date >= datetime.now()),
        )
    )

    if show_type is not None:
        select_query = select_query.where(SchemeImage.image_type_code == show_type)

    return select_query


def query_card_account_images(user_id: int, pay_card_index: dict, show_type: ImageTypes = None) -> Select:

    account_list = [k for k in pay_card_index.keys()]

    select_query = (
        select(
            PaymentCardAccountImage.id,
            PaymentCardAccountImage.image_type_code.label("type"),
            PaymentCardAccountImage.image.label("url"),
            PaymentCardAccountImage.description,
            PaymentCardAccountImage.encoding,
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
                PaymentAccountUserAssociation.payment_card_account_id.in_(account_list)
            ),
        )
        .where(
            PaymentAccount.is_deleted.is_(False),
            PaymentCardAccountImage.start_date <= datetime.now(),
            PaymentCardAccountImage.status != ImageStatus.DRAFT,
            or_(PaymentCardAccountImage.end_date.is_(None), PaymentCardAccountImage.end_date >= datetime.now()),
        )
    )
    if show_type is not None:
        select_query = select_query.where(PaymentCardAccountImage.image_type_code == show_type)
    return select_query


def query_payment_card_images(pay_card_index: dict, show_type: ImageTypes = None) -> Select:
    # get Unique list of card_ids
    card_id_dict = {k: None for k in pay_card_index.values()}
    plan_list = [k for k in card_id_dict.keys()]

    select_query = select(
        PaymentCardImage.id,
        PaymentCardImage.image_type_code.label("type"),
        PaymentCardImage.image.label("url"),
        PaymentCardImage.description,
        PaymentCardImage.encoding,
        PaymentCardImage.payment_card_id.label("plan_id"),
        None,
        literal("payment").label("table_type"),
    ).where(
        PaymentCardImage.payment_card_id.in_(plan_list),
        PaymentCardImage.start_date <= datetime.now(),
        PaymentCardImage.status != ImageStatus.DRAFT,
        or_(PaymentCardImage.end_date.is_(None), PaymentCardImage.end_date >= datetime.now()),
    )

    if show_type is not None:
        select_query = select_query.where(PaymentCardImage.image_type_code == show_type)

    return select_query


def query_all_images(
    db_session: Session,
    user_id: int,
    channel_id: str,
    loyalty_card_index: dict,
    pay_card_index: dict,
    show_type: ImageTypes = None,
    included_payment: bool = True,
    included_scheme: bool = True,
) -> dict:
    """
    By all images relating to a user or channel as defined by the input parameters.
    Note both scheme and payment images have 2 tables one for the account and the other
    for the scheme.  Account images override scheme images and have a 10,000,000 offset on
    the id field.
    An image is found if its is not a draft image, its start date is set in the past and
    the end date ie either not set or in the future and is not limited to an image type.

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
        select_list.append(query_card_account_images(user_id, pay_card_index, show_type))
        select_list.append(query_payment_card_images(pay_card_index, show_type))
    if included_scheme:
        select_list.append(query_scheme_account_images(user_id, show_type))
        select_list.append(query_scheme_images(channel_id, show_type))

    u = union_all(*select_list)
    results = db_session.execute(u).all()
    return process_images_query(results)


def process_images_query(query: list) -> dict:
    """
    Presupposes that query filters to only types required
    :param query:   image query result union to 4 image tables queried
    :return: dict structure which can be interrogated to find image output
    """
    images_obj = {}
    for image in query:
        image_dict = dict(image)
        image_type = image_dict.get("type")
        # pop fields not required in images output
        account_id = image_dict.pop("account_id", None)
        plan_id = image_dict.pop("plan_id", None)
        table_type = image_dict.pop("table_type", "unknown")

        if image_dict:
            if not image_dict.get("encoding"):
                try:
                    image_dict["encoding"] = image_dict["url"].split(".")[-1].replace("/", "")
                except (IndexError, AttributeError):
                    pass
            if not images_obj.get(table_type):
                images_obj[table_type] = {}
            if not images_obj[table_type].get(image_type):
                images_obj[table_type][image_type] = {"account": {}, "plan": {}}
            if account_id is None:
                if not images_obj[table_type][image_type]["plan"].get(plan_id):
                    images_obj[table_type][image_type]["plan"][plan_id] = []
                images_obj[table_type][image_type]["plan"][plan_id].append(image_dict)
            else:
                if not images_obj[table_type][image_type]["account"].get(account_id):
                    images_obj[table_type][image_type]["account"][account_id] = []
                image_dict["id"] += 10000000

                images_obj[table_type][image_type]["account"][account_id].append(image_dict)
    return images_obj
