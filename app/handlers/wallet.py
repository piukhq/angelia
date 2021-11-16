from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, select

from app.handlers.base import BaseHandler
from app.hermes.models import (
    PaymentAccount,
    PaymentAccountUserAssociation,
    PaymentCard,
    PaymentSchemeAccountAssociation,
    Scheme,
    SchemeAccount,
    SchemeAccountUserAssociation,
    SchemeOverrideError,
    User,
)
from app.lib.loyalty_card import LoyaltyCardStatus, StatusName

JOIN_IN_PROGRESS_STATES = [
    LoyaltyCardStatus.JOIN_IN_PROGRESS,
    LoyaltyCardStatus.JOIN_ASYNC_IN_PROGRESS,
    LoyaltyCardStatus.JOIN,
    LoyaltyCardStatus.JOIN_ERROR,
]


def add_fields(source: dict, fields: list) -> dict:
    return {field: source.get(field) for field in fields}


def money_str(prefix: str, value: any) -> str:
    try:
        money_float = float(value)
        if money_float.is_integer():
            value_str = f"{abs(int(money_float))}"
        else:
            value_str = f"{abs(money_float):.2f}"

        if value < 0:
            value_str = f"-{prefix}{value_str}"
        else:
            value_str = f"{prefix}{value_str}"

    except (ValueError, FloatingPointError, ArithmeticError, TypeError):
        if value:
            value_str = f"{prefix}{value}"
        else:
            value_str = ""
    return value_str


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


def process_prefix_suffix_values(prefix: str, value: any, suffix: any, always_show_prefix: bool = False) -> str:
    integer_values = False
    if suffix == "stamps":
        integer_values = True
    value_str = process_value(value, integer_values)
    if prefix and value_str:
        value_str = f"{prefix} {value_str}"
    elif prefix and always_show_prefix:
        value_str = f"{prefix}"
    return value_str


def add_prefix_suffix(
    prefix: str, value: any, suffix: any, append_suffix: bool = True, always_show_prefix: bool = False
) -> str:
    if prefix in ["£", "$", "€"]:
        value_str = money_str(prefix, value)
    else:
        value_str = process_prefix_suffix_values(prefix, value, suffix, always_show_prefix)
    if append_suffix and suffix and value_str:
        value_str = add_suffix(suffix, value_str)
    return value_str if value_str else None


def make_display_string(values_dict) -> str:
    value = values_dict.get("value")
    prefix = values_dict.get("prefix", "")
    suffix = values_dict.get("suffix", "")
    return add_prefix_suffix(prefix, value, suffix)


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
        self.earn_def = raw_voucher.get("earn", {})
        self.burn_def = raw_voucher.get("burn", {})
        self.earn_type = self.earn_def.get("type") if self.earn_def else None

    @property
    def progress_text(self):
        earn_value = self.earn_def.get("value", "")
        earn_target_value = self.earn_def.get("target_value", "")
        earn_suffix = self.earn_def.get("suffix", "")
        earn_prefix = self.earn_def.get("prefix", "")

        current = add_prefix_suffix(earn_prefix, earn_value, earn_suffix, append_suffix=False)
        target = add_prefix_suffix(earn_prefix, earn_target_value, earn_suffix, append_suffix=False)
        if current and target:
            display_str = f"{current}/{target}"
        elif current:
            display_str = f"{current}"
        else:
            return None
        return add_suffix(earn_suffix, display_str)

    @property
    def reward_text(self):
        burn_suffix = self.burn_def.get("suffix", "")
        burn_prefix = self.burn_def.get("prefix", "")
        burn_value = self.burn_def.get("value", "")
        return add_prefix_suffix(burn_prefix, burn_value, burn_suffix, always_show_prefix=True)


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


def process_vouchers(raw_vouchers: list) -> list:
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
                        "barcode_type",
                        "body_text",
                        "terms_and_conditions_url",
                        "date_issued",
                        "expiry_date",
                        "date_redeemed",
                    ],
                )
                voucher["earn_type"] = voucher_display.earn_type
                voucher["progress_display_text"] = voucher_display.progress_text
                voucher["reward_text"] = voucher_display.reward_text
                processed.append(voucher)
    except TypeError:
        pass
    return processed


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
            ret_dict["updated_at"] = values_dict.get("updated_at")
            ret_dict["current_display_value"] = make_display_string(values_dict)

    except (ValueError, IndexError, AttributeError, TypeError):
        pass
    return ret_dict


@dataclass
class WalletHandler(BaseHandler):
    joins: list = None
    loyalty_cards: list = None
    payment_accounts: list = None
    pll_for_scheme_accounts: dict = None
    pll_for_payment_accounts: dict = None

    def get_response_dict(self) -> dict:
        self._query_db()
        return {"joins": self.joins, "loyalty_cards": self.loyalty_cards, "payment_accounts": self.payment_accounts}

    def _query_db(self) -> None:
        self.joins = []
        self.loyalty_cards = []
        self.payment_accounts = []

        # First get pll lists from a query and use rotate the results to prepare payment and loyalty pll responses
        # Note we could have done this with one complex query on payment but it would have returned more rows and
        # is less readable.  Alternatively we could have used the links json in the Scheme accounts but that seems
        # like a hack used for Ubiquity performance and may need to be removed in the future.

        pll_accounts = self.query_all_pll()
        self.process_pll(pll_accounts)

        # Build the payment account part
        query_accounts = self.query_payment_accounts()
        self.process_payment_card_response(query_accounts)
        # Build the loyalty account part
        query_schemes = self.query_scheme_accounts()
        self.process_loyalty_cards_response(query_schemes)

    def query_all_pll(self) -> list:
        """
        Constructs the payment account and Scheme account pll lists from one query
        to injected into Loyalty and Payment account response dicts

        stores lists of pll responses indexed by scheme and payment account id
        """

        query = (
            select(
                PaymentAccount.id.label("payment_account_id"),
                SchemeAccount.id.label("loyalty_plan_id"),
                PaymentSchemeAccountAssociation.active_link.label("status"),
                Scheme.name.label("loyalty_plan"),
                PaymentCard.name.label("payment_scheme"),
            )
            .join(PaymentAccountUserAssociation)
            .join(User)
            .join(
                PaymentSchemeAccountAssociation,
                PaymentSchemeAccountAssociation.payment_card_account_id == PaymentAccount.id,
            )
            .join(SchemeAccount, PaymentSchemeAccountAssociation.scheme_account_id == SchemeAccount.id)
            .join(Scheme)
            .join(PaymentCard)
            .where(User.id == self.user_id, PaymentAccount.is_deleted.is_(False), SchemeAccount.is_deleted.is_(False))
        )
        accounts = self.db_session.execute(query).all()
        return accounts

    def process_pll(self, accounts: list) -> None:
        self.pll_for_scheme_accounts = {}
        self.pll_for_payment_accounts = {}

        for account in accounts:
            ppl_pay_dict = {}
            ppl_scheme_dict = {}
            dict_row = dict(account)
            if dict_row["status"]:
                dict_row["status"] = "active"
            else:
                dict_row["status"] = "pending"
            for key in ["loyalty_plan_id", "loyalty_plan", "status"]:
                ppl_pay_dict[key] = dict_row[key]
            for key in ["payment_account_id", "payment_scheme", "status"]:
                ppl_scheme_dict[key] = dict_row[key]
            try:
                self.pll_for_payment_accounts[dict_row["payment_account_id"]].append(ppl_pay_dict)
            except KeyError:
                self.pll_for_payment_accounts[dict_row["payment_account_id"]] = [ppl_pay_dict]

            try:
                self.pll_for_scheme_accounts[dict_row["loyalty_plan_id"]].append(ppl_scheme_dict)
            except KeyError:
                self.pll_for_scheme_accounts[dict_row["loyalty_plan_id"]] = [ppl_scheme_dict]

    def query_payment_accounts(self) -> list:
        self.payment_accounts = []
        query = (
            select(
                PaymentAccount.id,
                PaymentAccount.status,
                PaymentAccount.card_nickname,
                PaymentAccount.name_on_card,
                PaymentAccount.expiry_month,
                PaymentAccount.expiry_year,
            )
            .join(PaymentAccountUserAssociation)
            .join(User)
            .where(User.id == self.user_id, PaymentAccount.is_deleted.is_(False))
        )

        accounts_query = self.db_session.execute(query).all()
        return accounts_query

    def process_payment_card_response(self, accounts_query: list) -> None:
        for account in accounts_query:
            account_dict = dict(account)
            account_dict["pll_links"] = self.pll_for_payment_accounts.get(account_dict["id"])
            self.payment_accounts.append(account_dict)

    def query_scheme_accounts(self) -> list:
        self.loyalty_cards = []
        self.joins = []
        query = (
            select(
                SchemeAccount.id,
                SchemeAccount.scheme_id,
                SchemeAccount.status,
                SchemeAccount.balances,
                SchemeAccount.vouchers,
                SchemeAccount.transactions,
                SchemeAccount.barcode,
                SchemeAccount.card_number,
                SchemeAccountUserAssociation.auth_provided,
                Scheme.barcode_type,
                Scheme.colour,
                SchemeOverrideError,
            )
            .join(SchemeAccountUserAssociation, SchemeAccountUserAssociation.scheme_account_id == SchemeAccount.id)
            .join(Scheme)
            .join(
                SchemeOverrideError,
                and_(
                    SchemeOverrideError.scheme_id == Scheme.id, SchemeOverrideError.error_code == SchemeAccount.status
                ),
                isouter=True,
            )
            .where(SchemeAccountUserAssociation.user_id == self.user_id, SchemeAccount.is_deleted.is_(False))
        )
        results = self.db_session.execute(query).all()
        return results

    def process_loyalty_cards_response(self, results: list) -> None:
        for result in results:
            entry = {}
            data_row = dict(result)
            entry["id"] = data_row["id"]
            entry["loyalty_plan_id"] = data_row["scheme_id"]
            status_dict = LoyaltyCardStatus.get_status_dict(data_row["status"])
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

            if data_row["status"] in JOIN_IN_PROGRESS_STATES:
                # If a join card we have the data so save for set data and move on to next loyalty account
                self.joins.append(entry)
                continue

            # Process additional fields for Loyalty cards section
            entry["balance"] = get_balance_dict(data_row["balances"])
            entry["transactions"] = process_transactions(data_row["transactions"])
            entry["vouchers"] = process_vouchers(data_row["vouchers"])
            entry["card"] = add_fields(data_row, fields=["barcode", "barcode_type", "card_number", "colour"])
            entry["pll_links"] = self.pll_for_scheme_accounts.get(data_row["id"])
            self.loyalty_cards.append(entry)
