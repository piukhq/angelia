import time
from dataclasses import dataclass
from typing import Any

import falcon
from sqlalchemy import and_, select
from sqlalchemy.engine import Row

from app.api.exceptions import ResourceNotFoundError
from app.handlers.base import BaseHandler
from app.handlers.helpers.images import query_all_images
from app.handlers.loyalty_plan import LoyaltyPlanChannelStatus
from app.hermes.models import (
    Channel,
    ClientApplication,
    PaymentAccount,
    PaymentAccountUserAssociation,
    PaymentCard,
    PaymentSchemeAccountAssociation,
    PLLUserAssociation,
    Scheme,
    SchemeAccount,
    SchemeAccountUserAssociation,
    SchemeChannelAssociation,
    SchemeDocument,
    SchemeOverrideError,
    User,
)
from app.lib.images import ImageTypes
from app.lib.loyalty_card import LoyaltyCardStatus, StatusName
from app.lib.payment_card import PllLinkState, WalletPLLSlug
from app.lib.vouchers import MAX_INACTIVE, VoucherState, voucher_state_names
from app.report import api_logger


def process_loyalty_currency_name(prefix, suffix):
    currency_mapping = {"£": "GBP", "$": "USD", "€": "EUR", "pts": "points", "stamps": "stamps"}
    if prefix in ["£", "$", "€"]:
        return currency_mapping[prefix]
    else:
        return currency_mapping[suffix]


def add_fields(source: dict, fields: list) -> dict:
    return {field: source.get(field) for field in fields}


def money_str(prefix: str, value: any) -> (str, str):
    try:
        money_float = float(value)
        if money_float.is_integer():
            value_str = f"{abs(int(money_float))}"
        else:
            value_str = f"{abs(money_float):.2f}"

        if value < 0:
            value_prefix_str = f"-{prefix}{value_str}"
        else:
            value_prefix_str = f"{prefix}{value_str}"

    except (ValueError, FloatingPointError, ArithmeticError, TypeError):
        if value:
            value_prefix_str = f"{prefix}{value}"
            value_str = str(value)
        else:
            value_prefix_str = ""
            value_str = ""
    return value_str, value_prefix_str


def process_value(value: any, integer_values: bool = False) -> str:
    if value is not None:
        try:
            value_float = float(value)
            if value_float.is_integer() or integer_values:
                value_str = f"{int(value_float)}"
            else:
                value_str = f"{round(value_float, 2)}"
        except ValueError:
            value_str = f"{value}"
        return value_str
    else:
        return ""


def add_suffix(suffix: str, value_str: str, show_suffix_always: bool = False) -> str:
    if suffix and value_str:
        return f"{value_str} {suffix}"
    elif suffix:
        return f"{suffix}" if show_suffix_always else None
    return value_str


def process_prefix_suffix_values(prefix: str, value: any, suffix: any, always_show_prefix: bool = False) -> (str, str):
    integer_values = False
    if suffix == "stamps":
        integer_values = True
    value_str = process_value(value, integer_values)
    value_prefix_str = value_str
    if prefix and value_str:
        value_prefix_str = f"{prefix} {value_str}"
    elif prefix and always_show_prefix:
        value_prefix_str = f"{prefix}"
    return value_str, value_prefix_str


def add_prefix_suffix(
    prefix: str, value: any, suffix: any, append_suffix: bool = True, always_show_prefix: bool = False
) -> (str, str):
    if prefix in ["£", "$", "€"]:
        value_str, value_text = money_str(prefix, value)
    else:
        value_str, value_text = process_prefix_suffix_values(prefix, value, suffix, always_show_prefix)
    if append_suffix and suffix and value_text:
        value_text = add_suffix(suffix, value_text)
    return value_str if value_str else None, value_text if value_text else None


def make_display_string(values_dict) -> str:
    value = values_dict.get("value")
    prefix = values_dict.get("prefix", "")
    suffix = values_dict.get("suffix", "")
    _, display_str = add_prefix_suffix(prefix, value, suffix)
    return display_str


class VoucherDisplay:
    """
    Now updated according to:
    https://hellobink.atlassian.net/wiki/spaces/LP/pages/2802516046/API+v2.0+-+Vouchers+Fields+help
    simplified rule:
    Progress_display_text = data->earned value + </> + Earn->target value + <SPACE> + Earn->suffix.
    examples   2/7 stamps  £10/£100
    simplified rule:
    reward_text = burn_prefix + ("" if burn_prefix == '£' else " ") + burn_value + (" " if burn_value != '' else "")
    + burn_suffix
    examples:
    Free Meal   £2.50 Reward   15% off  Free whopper

    """

    def __init__(self, raw_voucher: dict):
        self.barcode_type = raw_voucher.get("barcode_type", None)
        self.earn_def = raw_voucher.get("earn", {})
        self.burn_def = raw_voucher.get("burn", {})
        self.earn_type = self.earn_def.get("type") if self.earn_def else None
        self.current_value = None
        self.target_value = None
        self.earn_suffix = None
        self.earn_prefix = None
        self.progress_text = None
        self.reward_text = None
        self.process_earn_values()
        self.process_burn_values()
        self.process_barcode_type()

    def process_earn_values(self):
        earn_value = self.earn_def.get("value", "")
        earn_target_value = self.earn_def.get("target_value", "")
        self.earn_suffix = self.earn_def.get("suffix", "")
        self.earn_prefix = self.earn_def.get("prefix", "")

        self.current_value, current_text = add_prefix_suffix(
            self.earn_prefix, earn_value, self.earn_suffix, append_suffix=False
        )
        self.target_value, target_text = add_prefix_suffix(
            self.earn_prefix, earn_target_value, self.earn_suffix, append_suffix=False
        )
        if current_text and target_text:
            display_str = f"{current_text}/{target_text}"
        elif current_text:
            display_str = f"{current_text}"
        else:
            self.progress_text = None
            return None
        self.progress_text = add_suffix(self.earn_suffix, display_str)

    def process_burn_values(self):
        burn_suffix = self.burn_def.get("suffix", "")
        burn_prefix = self.burn_def.get("prefix", "")
        burn_value = self.burn_def.get("value", "")
        _, self.reward_text = add_prefix_suffix(burn_prefix, burn_value, burn_suffix, always_show_prefix=True)

    def process_barcode_type(self):
        if self.barcode_type == 9:
            self.barcode_type = None


def process_transactions(raw_transactions: list) -> list:
    processed = []
    try:
        for raw_transaction in raw_transactions:
            if raw_transaction:
                transaction = add_fields(raw_transaction, ["id", "timestamp", "description", "display_value"])
                # Note amounts is a list only know how to process 1st item
                amounts_list = raw_transaction.get("amounts", {})
                if amounts_list:
                    transaction["display_value"] = make_display_string(amounts_list[0])
                processed.append(transaction)

    except TypeError:
        pass
    return processed


def process_vouchers(raw_vouchers: list, voucher_url: str) -> list:
    processed = []
    try:
        for raw_voucher in raw_vouchers:
            if raw_voucher:
                voucher_display = VoucherDisplay(raw_voucher)
                voucher = add_fields(
                    raw_voucher,
                    [
                        "state",
                        "headline",
                        "code",
                        "body_text",
                        "terms_and_conditions_url",
                        "date_issued",
                        "expiry_date",
                        "date_redeemed",
                    ],
                )
                voucher["terms_and_conditions_url"] = voucher_url
                voucher["earn_type"] = voucher_display.earn_type
                voucher["progress_display_text"] = voucher_display.progress_text
                voucher["current_value"] = voucher_display.current_value
                voucher["target_value"] = voucher_display.target_value
                voucher["prefix"] = voucher_display.earn_prefix
                voucher["suffix"] = voucher_display.earn_suffix
                voucher["reward_text"] = voucher_display.reward_text
                voucher["barcode_type"] = voucher_display.barcode_type
                processed.append(voucher)

        # sort by issued date (an int) or NOW if it is None
        right_now = int(time.time())
        processed = sorted(processed, reverse=True, key=lambda i: i["date_issued"] or right_now)

        # filter the processed vouchers with logic & facts
        # if we have less than 10 vouchers in total keep 'em all
        if len(processed) > MAX_INACTIVE:
            inactive_count = 0
            keepers = []
            for voucher in processed:
                # ISSUED & IN_PROGRESS are always kept
                if voucher["state"] in (
                    voucher_state_names[VoucherState.ISSUED],
                    voucher_state_names[VoucherState.IN_PROGRESS],
                ):
                    keepers.append(voucher)
                else:
                    inactive_count = inactive_count + 1
                    if inactive_count > MAX_INACTIVE:
                        # reached our limit, move along to the next voucher
                        continue
                    else:
                        keepers.append(voucher)
            processed = keepers

    except TypeError:
        pass
    return processed


def is_reward_available(raw_vouchers: list) -> bool:
    reward = False
    for voucher in raw_vouchers:
        if voucher:
            if voucher["state"] == "issued":
                reward = True
                break

    return reward


def dict_from_obj(values_obj: Any) -> dict:
    values_dict = {}
    if values_obj:
        try:
            values_dict = values_obj.pop(0)
        except (KeyError, AttributeError):
            values_dict = values_obj
    return values_dict


def get_balance_dict(values_obj: Any) -> dict:
    ret_dict = {"updated_at": None, "current_display_value": None}
    values_dict = dict_from_obj(values_obj)
    try:
        if values_dict:
            prefix = values_dict.get("prefix")
            suffix = values_dict.get("suffix")
            value = process_value(values_dict.get("value"))

            ret_dict["updated_at"] = values_dict.get("updated_at")
            ret_dict["current_display_value"] = make_display_string(values_dict)
            ret_dict["loyalty_currency_name"] = process_loyalty_currency_name(prefix, suffix)
            ret_dict["prefix"] = prefix
            ret_dict["suffix"] = suffix
            ret_dict["current_value"] = value if float(value).is_integer() else f"{float(value):.2f}"
            ret_dict["reward_tier"] = values_dict.get("reward_tier")

    except (ValueError, IndexError, AttributeError, TypeError):
        pass
    return ret_dict


def check_one(results: list, row_id: int, log_message_multiple: str) -> dict:
    no_of_rows = len(results)

    if no_of_rows < 1:
        raise ResourceNotFoundError

    elif no_of_rows > 1:
        api_logger.error(f"{log_message_multiple} Multiple rows returned for id: {row_id}")
        raise falcon.HTTPInternalServerError
    return dict(results[0])


def process_hero_image(
    available_images: dict, table_type: str, account_id: int, plan_id: int, tier: int, image_list: list
) -> None:
    # Determine what image to return as the hero image.
    # If tier image is available return that as the hero image.
    # Scheme account images still takes precedent over scheme images.
    account_tier_images = available_images[table_type][ImageTypes.TIER]["account"].get(account_id, [])
    account_hero_images = available_images[table_type][ImageTypes.HERO]["account"].get(account_id, [])

    plan_tier_images = available_images[table_type][ImageTypes.TIER]["plan"].get(plan_id, [])
    plan_hero_images = available_images[table_type][ImageTypes.HERO]["plan"].get(plan_id, [])

    reward_tier = False

    for tier_image in plan_tier_images if not account_tier_images else account_tier_images:
        if tier_image["reward_tier"] == tier and not account_hero_images:
            tier_image["type"] = ImageTypes.HERO
            tier_image.pop("reward_tier", None)

            image_list.append(tier_image)
            reward_tier = True
            break

    # Return hero image if tier image is not found
    if not reward_tier:
        for hero_image in plan_hero_images if not account_hero_images else account_hero_images:
            hero_image.pop("reward_tier", None)
            image_list.append(hero_image)


def get_image_list(
    available_images: dict, table_type: str, account_id: int, plan_id: int, tier: [bool, int] = None
) -> list:
    image_list = []
    try:
        tier_image_available = ImageTypes.TIER in available_images[table_type].keys()
        for image_type in available_images[table_type].keys():
            image = available_images[table_type][image_type]["account"].get(account_id, [])
            if not image:
                image = available_images[table_type][image_type]["plan"].get(plan_id, [])
            if image:
                if tier_image_available and image_type in [ImageTypes.TIER, ImageTypes.HERO]:
                    # Hero image and tier image handled by process_hero_image()
                    continue
                for each in image:
                    each.pop("reward_tier", None)
                    image_list.append(each)

        if tier_image_available:
            process_hero_image(available_images, table_type, account_id, plan_id, tier, image_list)
    except KeyError:
        pass
    return image_list


@dataclass
class WalletHandler(BaseHandler):
    joins: list = None
    loyalty_cards: list = None
    payment_accounts: list = None
    pll_for_scheme_accounts: dict = None
    pll_for_payment_accounts: dict = None
    pll_active_accounts: list = None
    pll_fully_linked: bool = None
    all_images: dict = None

    @property
    def _scheme_account_query(self):
        return (
            select(
                SchemeAccount.id,
                SchemeAccount.scheme_id,
                SchemeAccount.balances,
                SchemeAccount.vouchers,
                SchemeAccount.transactions,
                SchemeAccount.barcode,
                SchemeAccount.card_number,
                SchemeAccountUserAssociation.link_status,
                Scheme.barcode_type,
                Scheme.colour,
                Scheme.text_colour,
                Scheme.name.label("scheme_name"),
                SchemeDocument.url.label("voucher_url"),
                SchemeOverrideError,
            )
            .join(SchemeAccountUserAssociation, SchemeAccountUserAssociation.scheme_account_id == SchemeAccount.id)
            .join(Scheme)
            .join(
                SchemeChannelAssociation,
                and_(
                    SchemeChannelAssociation.scheme_id == Scheme.id,
                    SchemeChannelAssociation.status != LoyaltyPlanChannelStatus.INACTIVE.value,
                ),
            )
            .join(Channel, Channel.id == SchemeChannelAssociation.bundle_id)
            .join(
                SchemeOverrideError,
                and_(
                    SchemeOverrideError.scheme_id == Scheme.id,
                    SchemeOverrideError.error_code == SchemeAccountUserAssociation.link_status,
                    SchemeOverrideError.channel_id == SchemeChannelAssociation.bundle_id,
                ),
                isouter=True,
            )
            .join(
                SchemeDocument,
                and_(SchemeDocument.scheme_id == Scheme.id, SchemeDocument.display[1] == "VOUCHER"),
                isouter=True,
            )
            .where(
                SchemeAccountUserAssociation.user_id == self.user_id,
                SchemeAccount.is_deleted.is_(False),
                Channel.bundle_id == self.channel_id,
            )
        )

    def get_wallet_response(self) -> dict:
        self._query_db()
        return {"joins": self.joins, "loyalty_cards": self.loyalty_cards, "payment_accounts": self.payment_accounts}

    def get_overview_wallet_response(self) -> dict:
        self._query_db(full=False)
        return {"joins": self.joins, "loyalty_cards": self.loyalty_cards, "payment_accounts": self.payment_accounts}

    def get_payment_account_channel_links(self) -> dict:
        """
        Get the payment accounts linked to each loyalty_card and the channels linked to each user
        of those payment accounts. The data is then amalgamated based on the payment account ids
        and formatted to return distinct channels.

        This will identify which channels each loyalty_card has a PLL link in.
        """
        self.loyalty_cards = []

        card_results, channel_results = self.query_loyalty_cards_channel_links()
        loyalty_cards = self._merge_channel_links_query_results(card_results, channel_results)

        for mcard_id, linked_channel_info in loyalty_cards.items():
            deduplicated_channels = {
                (channel_info["channel"], channel_info["client_name"]) for channel_info in linked_channel_info
            }

            formatted_channels = [
                {
                    "slug": channel_info[0],
                    "description": f"You have a Payment Card in the {channel_info[1]} channel.",
                }
                for channel_info in deduplicated_channels
            ]

            formatted_card = {
                "id": mcard_id,
                "channels": formatted_channels,
            }
            self.loyalty_cards.append(formatted_card)

        return {"loyalty_cards": self.loyalty_cards}

    def get_loyalty_card_by_id_response(self, loyalty_card_id: int) -> dict:
        self.joins = []
        self.loyalty_cards = []
        self.payment_accounts = []
        self.all_images = {}

        # query & process pll first
        pll_result = self.query_all_pll(schemeaccount_id=loyalty_card_id)
        self.process_pll(pll_result)

        # query loyalty card info
        loyalty_card_query = self._scheme_account_query.where(
            SchemeAccount.id == loyalty_card_id,
            SchemeAccountUserAssociation.link_status.not_in(LoyaltyCardStatus.JOIN_STATES),
        )
        loyalty_card_result = self.db_session.execute(loyalty_card_query).all()
        if len(loyalty_card_result) == 0:
            raise ResourceNotFoundError

        payment_accounts = self.query_payment_accounts()

        loyalty_card_index, loyalty_cards, join_cards = self.process_loyalty_cards_response(
            loyalty_card_result, full=True, accounts=payment_accounts
        )

        # query & process images next
        # at this point loyalty_card_index has only one card in it
        self.all_images = query_all_images(
            db_session=self.db_session,
            user_id=self.user_id,
            channel_id=self.channel_id,
            loyalty_card_index=loyalty_card_index,
            pay_card_index={},
            show_type=None,
            included_payment=False,
            included_scheme=True,
        )
        self.add_scheme_images_to_response(loyalty_cards, join_cards, loyalty_card_index)

        # at this point self.loyalty_cards is a list one exactly one item (we hope)
        return self.loyalty_cards[0]

    def get_loyalty_card_transactions_response(self, loyalty_card_id):
        query_dict = check_one(
            self.query_scheme_account(loyalty_card_id, SchemeAccount.transactions),
            loyalty_card_id,
            "Loyalty Card Transaction Wallet Error:",
        )
        # Filter non-active cards here instead of in the db query itself, so we return empty transactions
        # for cards in a non-active state instead of raising a 404, which should only be raised when the user
        # is not linked to the card
        if query_dict["link_status"] == LoyaltyCardStatus.ACTIVE:
            transactions = process_transactions(query_dict.get("transactions", []))
        else:
            transactions = []

        return {"transactions": transactions}

    def get_loyalty_card_balance_response(self, loyalty_card_id):
        query_dict = check_one(
            self.query_scheme_account(loyalty_card_id, SchemeAccount.balances),
            loyalty_card_id,
            "Loyalty Card Balance Wallet Error:",
        )

        if query_dict["link_status"] == LoyaltyCardStatus.ACTIVE:
            balance = get_balance_dict(query_dict.get("balances", []))
            target_value = self.get_target_value(loyalty_card_id)
            balance["target_value"] = target_value
            balance.pop("reward_tier", None)
        else:
            balance = get_balance_dict(None)

        return {"balance": balance}

    def get_loyalty_card_vouchers_response(self, loyalty_card_id):
        query_dict = check_one(
            self.query_voucher(loyalty_card_id, SchemeAccount.vouchers, SchemeDocument.url.label("voucher_url")),
            loyalty_card_id,
            "Loyalty Card Voucher Wallet Error:",
        )
        # Filter non-active cards here instead of in the db query itself, so we return empty transactions
        # for cards in a non-active state instead of raising a 404, which should only be raised when the user
        # is not linked to the card
        if query_dict["link_status"] == LoyaltyCardStatus.ACTIVE:
            voucher_url = query_dict.get("voucher_url", None) or ""
            vouchers = process_vouchers(query_dict.get("vouchers", []), voucher_url)
        else:
            vouchers = []

        return {"vouchers": vouchers}

    def _query_db(self, full: bool = True) -> None:
        """
        Queries the db for Wallet fields and assembles the required dict for serializer
        :param full:  True for full wallet output, false for abbreviated wallet_overview
        :return: nothing returned sets the 3 class variables used in api response
        """
        self.joins = []
        self.loyalty_cards = []
        self.payment_accounts = []

        self.all_images = {}

        # First get pll lists from a query and use rotate the results to prepare payment and loyalty pll responses
        # Note we could have done this with one complex query on payment but it would have returned more rows and
        # is less readable.  Alternatively we could have used the links json in the Scheme accounts but that seems
        # like a hack used for Ubiquity performance and may need to be removed in the future.

        pll_accounts = self.query_all_pll()
        self.process_pll(pll_accounts)

        if full:
            image_types = None  # Defaults to all image types
        else:
            image_types = ImageTypes.HERO

        # Build the payment account part excluding images which will be confined to accounts and plan ids present.
        query_accounts = self.query_payment_accounts()
        pay_card_index, pay_accounts = self.process_payment_card_response(query_accounts, full)

        # Do same for the loyalty account and join parts
        query_schemes = self.query_scheme_accounts()

        (
            loyalty_card_index,
            loyalty_cards,
            join_cards,
        ) = self.process_loyalty_cards_response(query_schemes, full, query_accounts)

        # Find images from all 4 image tables in one query but restricted to items listed in api
        self.all_images = query_all_images(
            db_session=self.db_session,
            user_id=self.user_id,
            channel_id=self.channel_id,
            loyalty_card_index=loyalty_card_index,
            pay_card_index=pay_card_index,
            show_type=image_types,
        )

        # now add the images into relevant sections of the api output
        self.add_card_images_to_response(pay_accounts, pay_card_index)
        self.add_scheme_images_to_response(loyalty_cards, join_cards, loyalty_card_index)

    def query_all_pll(self, schemeaccount_id=None) -> list:
        """
        Constructs the payment account and Scheme account pll lists from one query
        to injected into Loyalty and Payment account response dicts

        stores lists of pll responses indexed by scheme and payment account id
        """
        query = (
            select(
                PaymentAccount.id.label("payment_account_id"),
                SchemeAccount.id.label("loyalty_card_id"),
                PLLUserAssociation.state,
                PLLUserAssociation.slug,
                Scheme.name.label("loyalty_plan"),
                PaymentCard.name.label("payment_scheme"),
            )
            .join(
                PaymentSchemeAccountAssociation,
                PaymentSchemeAccountAssociation.payment_card_account_id == PaymentAccount.id,
            )
            .join(PLLUserAssociation)
            .join(SchemeAccount, PaymentSchemeAccountAssociation.scheme_account_id == SchemeAccount.id)
            .join(Scheme)
            .join(PaymentCard)
            .where(
                PLLUserAssociation.user_id == self.user_id,
                PaymentAccount.is_deleted.is_(False),
                SchemeAccount.is_deleted.is_(False),
            )
        )

        # I only want one scheme account (loyalty card)
        if schemeaccount_id:
            query = query.where(SchemeAccount.id == schemeaccount_id)

        accounts = self.db_session.execute(query).all()
        return accounts

    def process_pll(self, accounts: list) -> None:
        self.pll_for_scheme_accounts = {}
        self.pll_for_payment_accounts = {}

        for account in accounts:
            pll_pay_dict = {}
            pll_scheme_dict = {}
            dict_row = dict(account)
            dict_row["status"] = {}

            # slug
            slug = dict_row["slug"]
            dict_row["status"]["slug"] = slug

            # description
            description = [item for item in WalletPLLSlug.get_descriptions() if item[1] == slug]
            dict_row["status"]["description"] = description[0][2] if description else ""

            # state
            dict_row["status"]["state"] = PllLinkState.to_str(dict_row["state"])

            for key in ["loyalty_card_id", "loyalty_plan", "status"]:
                pll_pay_dict[key] = dict_row[key]
            for key in ["payment_account_id", "payment_scheme", "status"]:
                pll_scheme_dict[key] = dict_row[key]
            try:
                self.pll_for_payment_accounts[dict_row["payment_account_id"]].append(pll_pay_dict)
            except KeyError:
                self.pll_for_payment_accounts[dict_row["payment_account_id"]] = [pll_pay_dict]

            try:
                self.pll_for_scheme_accounts[dict_row["loyalty_card_id"]].append(pll_scheme_dict)
            except KeyError:
                self.pll_for_scheme_accounts[dict_row["loyalty_card_id"]] = [pll_scheme_dict]

    def is_pll_fully_linked(self, plls: list, accounts: list) -> None:
        total_accounts = len(accounts)
        self.pll_active_accounts = len([pll for pll in plls if pll["status"]["state"] == "active"])
        self.pll_fully_linked = 0 < self.pll_active_accounts == total_accounts > 0

    def query_payment_accounts(self) -> list:
        self.payment_accounts = []
        query = (
            select(
                PaymentAccount.id,
                PaymentCard.name.label("provider"),
                PaymentAccount.status,
                PaymentAccount.card_nickname,
                PaymentAccount.name_on_card,
                PaymentAccount.expiry_month,
                PaymentAccount.expiry_year,
                PaymentAccount.issuer_name.label("issuer"),
                PaymentCard.type,
                PaymentAccount.country,
                PaymentAccount.currency_code,
                PaymentAccount.pan_end.label("last_four_digits"),
                PaymentAccount.payment_card_id.label("plan_id"),
            )
            .join(PaymentAccountUserAssociation)
            .join(User)
            .join(PaymentCard)
            .where(User.id == self.user_id, PaymentAccount.is_deleted.is_(False))
        )

        accounts_query = self.db_session.execute(query).all()
        return accounts_query

    def process_payment_card_response(self, accounts_query: list, full: bool = True) -> (dict, list):
        payment_card_index = {}
        payment_accounts = []
        for account in accounts_query:
            account_dict = dict(account)
            plan_id = account_dict.pop("plan_id", None)
            payment_card_index[account_dict["id"]] = plan_id
            if full:
                account_dict["pll_links"] = self.pll_for_payment_accounts.get(account_dict["id"])
            payment_accounts.append(account_dict)
        return payment_card_index, payment_accounts

    def add_card_images_to_response(self, payment_accounts, payment_card_index):
        for account in payment_accounts:
            plan_id = payment_card_index[account["id"]]
            account["images"] = get_image_list(self.all_images, "payment", account["id"], plan_id)
            self.payment_accounts.append(account)

    def query_scheme_account(self, loyalty_id, *args) -> list:
        query = (
            select(*args, SchemeAccountUserAssociation.link_status)
            .join(SchemeAccountUserAssociation, SchemeAccountUserAssociation.scheme_account_id == SchemeAccount.id)
            .where(
                SchemeAccount.id == loyalty_id,
                SchemeAccountUserAssociation.user_id == self.user_id,
                SchemeAccount.is_deleted.is_(False),
            )
        )
        results = self.db_session.execute(query).all()
        return results

    def query_voucher(self, loyalty_id, *args) -> list:
        query = (
            select(*args, SchemeAccountUserAssociation.link_status)
            .join(SchemeAccountUserAssociation, SchemeAccountUserAssociation.scheme_account_id == SchemeAccount.id)
            .join(
                SchemeDocument,
                and_(SchemeDocument.scheme_id == SchemeAccount.scheme_id, SchemeDocument.display[1] == "VOUCHER"),
                isouter=True,
            )
            .where(
                SchemeAccount.id == loyalty_id,
                SchemeAccountUserAssociation.user_id == self.user_id,
                SchemeAccount.is_deleted.is_(False),
            )
        )
        results = self.db_session.execute(query).all()
        return results

    def query_scheme_accounts(self) -> list:
        self.loyalty_cards = []
        self.joins = []
        query = self._scheme_account_query
        return self.db_session.execute(query).all()

    def process_loyalty_cards_response(
        self,
        results: list,
        full: bool = True,
        accounts: list = [],
    ) -> (dict, list, list):
        loyalty_accounts = []
        join_accounts = []
        loyalty_card_index = {}

        for result in results:
            entry = {}
            data_row = dict(result)
            entry["id"] = data_row["id"]
            entry["loyalty_plan_id"] = data_row["scheme_id"]
            entry["loyalty_plan_name"] = data_row["scheme_name"]
            voucher_url = data_row["voucher_url"] or ""
            status_dict = LoyaltyCardStatus.get_status_dict(data_row["link_status"])
            state = status_dict.get("api2_state")

            if state == StatusName.DEPENDANT:
                if data_row["balances"]:
                    new_status = LoyaltyCardStatus.ACTIVE
                else:
                    new_status = LoyaltyCardStatus.PENDING
                status_dict = LoyaltyCardStatus.get_status_dict(new_status)
                state = status_dict.get("api2_state")

            entry["status"] = {"state": state}
            if data_row["SchemeOverrideError"]:
                override_status = data_row["SchemeOverrideError"]
                entry["status"]["slug"] = override_status.error_slug
                entry["status"]["description"] = override_status.message
            else:
                entry["status"]["slug"] = status_dict.get("api2_slug")
                entry["status"]["description"] = status_dict.get("api2_description")

            plan_id = data_row.get("scheme_id", None)
            loyalty_card_index[data_row["id"]] = plan_id
            entry["card"] = add_fields(
                data_row, fields=["barcode", "barcode_type", "card_number", "colour", "text_colour"]
            )

            if data_row["link_status"] in LoyaltyCardStatus.JOIN_STATES:
                # If a join card we have the data so save for set data and move on to next loyalty account
                join_accounts.append(entry)
                continue

            entry["balance"] = {"updated_at": None, "current_display_value": None}

            if state == StatusName.AUTHORISED:
                # Process additional fields for Loyalty cards section
                # balance object now has target_value (from voucher if available)
                balance = get_balance_dict(data_row["balances"])
                target_value = self.get_target_value(entry["id"])
                balance["target_value"] = target_value
                entry["balance"] = balance

            if full:
                entry["pll_links"] = self.pll_for_scheme_accounts.get(data_row["id"])
                if state == StatusName.AUTHORISED:
                    entry["transactions"] = process_transactions(data_row["transactions"])
                    entry["vouchers"] = process_vouchers(data_row["vouchers"], voucher_url)

            plls = self.pll_for_scheme_accounts.get(data_row["id"], [])
            self.is_pll_fully_linked(plls, accounts)

            entry["reward_available"] = is_reward_available(data_row["vouchers"])
            entry["is_fully_pll_linked"] = self.pll_fully_linked
            entry["pll_linked_payment_accounts"] = self.pll_active_accounts
            entry["total_payment_accounts"] = len(accounts)

            loyalty_accounts.append(entry)

        return loyalty_card_index, loyalty_accounts, join_accounts

    def query_loyalty_cards_channel_links(self) -> tuple[list[Row[int, int]], list[Row[int, str, str]]]:
        cards_query = (
            select(
                SchemeAccount.id,
                PaymentAccount.id,
            )
            .join(SchemeAccountUserAssociation, SchemeAccountUserAssociation.scheme_account_id == SchemeAccount.id)
            .join(Scheme)
            .join(
                SchemeChannelAssociation,
                and_(
                    SchemeChannelAssociation.scheme_id == Scheme.id,
                    SchemeChannelAssociation.status != LoyaltyPlanChannelStatus.INACTIVE.value,
                ),
            )
            .join(Channel, Channel.id == SchemeChannelAssociation.bundle_id)
            .join(
                PaymentSchemeAccountAssociation,
                PaymentSchemeAccountAssociation.scheme_account_id == SchemeAccountUserAssociation.scheme_account_id,
            )
            .join(PaymentAccount)
            .where(
                SchemeAccountUserAssociation.user_id == self.user_id,
                SchemeAccount.is_deleted.is_(False),
                PaymentAccount.is_deleted.is_(False),
                Channel.bundle_id == self.channel_id,
            )
        )
        card_results = self.db_session.execute(cards_query).all()

        user_query = (
            select(PaymentAccountUserAssociation.payment_card_account_id, Channel.bundle_id, ClientApplication.name)
            .join(
                User,
                PaymentAccountUserAssociation.user_id == User.id,
            )
            .join(
                ClientApplication,
                User.client_id == ClientApplication.client_id,
            )
            .join(
                Channel,
                User.client_id == Channel.client_id,
            )
            .where(
                PaymentAccountUserAssociation.payment_card_account_id.in_(set(card[1] for card in card_results)),
            )
            .group_by(PaymentAccountUserAssociation.payment_card_account_id, Channel.bundle_id, ClientApplication.name)
        )
        channel_results = self.db_session.execute(user_query).all()

        return card_results, channel_results

    def add_scheme_images_to_response(self, loyalty_accounts, join_accounts, loyalty_card_index):
        for account in loyalty_accounts:
            plan_id = loyalty_card_index[account["id"]]
            tier = account["balance"].pop("reward_tier", None)
            account["images"] = get_image_list(self.all_images, "scheme", account["id"], plan_id, tier)
            self.loyalty_cards.append(account)
        for account in join_accounts:
            plan_id = loyalty_card_index[account["id"]]
            account["images"] = get_image_list(self.all_images, "scheme", account["id"], plan_id)
            self.joins.append(account)

    def get_target_value(self, loyalty_card_id: int):
        # get vouchers so we can get a target_value
        query_dict_vouch = check_one(
            self.query_scheme_account(loyalty_card_id, SchemeAccount.vouchers),
            loyalty_card_id,
            "Loyalty Card Voucher Wallet Error:",
        )
        vouchers = process_vouchers(query_dict_vouch.get("vouchers", []), "")
        target_value = None
        for v in vouchers:
            if v["state"] == voucher_state_names[VoucherState.IN_PROGRESS]:
                target_value = v["target_value"]
                break  # look no further
        return target_value

    @staticmethod
    def _merge_channel_links_query_results(card_results, channel_results) -> dict:
        card_ids = [{"mcard_id": card[0], "pcard_id": card[1]} for card in card_results]
        channel_info = [
            {"pcard_id": result[0], "channel": result[1], "client_name": result[2]} for result in channel_results
        ]

        # Inefficient method of joining the data but the lists should be so small that this
        # shouldn't have a noticeable performance impact.
        joined_data = []
        for cards in card_ids:
            for channel_data in channel_info:
                if cards["pcard_id"] == channel_data["pcard_id"]:
                    formatted_channel_info = {
                        "mcard_id": cards["mcard_id"],
                        "pcard_id": cards["pcard_id"],
                        "channel": channel_data["channel"],
                        "client_name": channel_data["client_name"],
                    }
                    joined_data.append(formatted_channel_info)

        loyalty_cards = {}
        for channel_link_data in joined_data:
            loyalty_card_id = channel_link_data["mcard_id"]
            if loyalty_card_id not in loyalty_cards:
                loyalty_cards[loyalty_card_id] = [channel_link_data]
            else:
                loyalty_cards[loyalty_card_id].append(channel_link_data)

        return loyalty_cards
