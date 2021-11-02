from app.lib.loyalty_card import LoyaltyCardStatus
from dataclasses import dataclass

from sqlalchemy import select

from app.handlers.base import BaseHandler
from app.hermes.models import (
    PaymentAccount, PaymentAccountUserAssociation, User, SchemeAccountUserAssociation,
    PaymentSchemeAccountAssociation, SchemeAccount, Scheme, PaymentCard, SchemeOverrideError
)

JOIN_IN_PROGRESS_STATES = [

]


def add_fields(source: dict, fields: list) -> dict:
    return {field: source.get(field) for field in fields}


def get_balance_dict(values_dict: dict) -> dict:
    ret_dict = {
        "updated_at": None,
        "current_display_value": None
    }
    try:
        if values_dict:
            ret_dict["updated_at"] = values_dict.get("updated_at")
            value = values_dict.get("value")
            prefix = values_dict.get("prefix", "")
            suffix = values_dict.get("suffix", "")
            if suffix:
                space = " "
            else:
                space = ""
            if value is not None:
                ret_dict["current_display_value"] = f"{prefix}{value}{space}{suffix}"
    except (ValueError, IndexError, AttributeError, TypeError):
        pass
    return ret_dict


@dataclass
class WalletHandler(BaseHandler):
    joins = []
    loyalty_cards = []
    payment_accounts = []
    pll_for_schemes_accounts = {}
    pll_for_payment_accounts = {}

    def get_response_dict(self) -> dict:
        self._query_db()
        return {"joins": self.joins, "loyalty_cards": self.loyalty_cards, "payment_accounts": self.payment_accounts}

    def _query_db(self) -> None:
        # First get pll lists which will be used when building response
        self._query_all_pll()
        # Build the payment account part
        self._query_payment_accounts()
        # Build the loyalty account part
        self._query_scheme_accounts()

    def _query_all_pll(self) -> None:
        """
        Constructs the payment account and Scheme account pll lists from one query
        to injected into Loyalty and Payment account response dicts

        stores lists of pll responses indexed by scheme and payment account id
        """
        self.pll_for_schemes_accounts = {}
        self.pll_for_payment_accounts = {}
        query = (
            select(PaymentAccount.id.label("payment_account_id"),
                   SchemeAccount.id.label("loyalty_plan_id"),
                   PaymentSchemeAccountAssociation.active_link.label("status"),
                   Scheme.name.label("loyalty_plan"),
                   PaymentCard.name.label("payment_scheme"))
            .join(PaymentAccountUserAssociation)
            .join(User)
            .join(PaymentSchemeAccountAssociation,
                  PaymentSchemeAccountAssociation.payment_card_account_id == PaymentAccount.id)
            .join(SchemeAccount,
                  PaymentSchemeAccountAssociation.scheme_account_id == SchemeAccount.id)
            .join(Scheme)
            .join(PaymentCard)
            .where(
                User.id == self.user_id,
                PaymentAccount.is_deleted.is_(False),
                SchemeAccount.is_deleted.is_(False)
            )
        )
        accounts = self.db_session.execute(query).all()
        for account in accounts:
            ppl_pay_dict = {}
            ppl_scheme_dict = {}
            dict_row = dict(account)
            if dict_row['status']:
                dict_row['status'] = 'active'
            else:
                dict_row['status'] = 'pending'
            for key in ["loyalty_plan_id", "loyalty_plan", "status"]:
                ppl_pay_dict[key] = dict_row[key]
            for key in ["payment_account_id", "payment_scheme", "status"]:
                ppl_scheme_dict[key] = dict_row[key]
            try:
                self.pll_for_payment_accounts[dict_row['payment_account_id']].append(ppl_pay_dict)
            except KeyError:
                self.pll_for_payment_accounts[dict_row['payment_account_id']] = [ppl_pay_dict]

            try:
                self.pll_for_schemes_accounts[dict_row['loyalty_plan_id']].append(ppl_scheme_dict)
            except KeyError:
                self.pll_for_schemes_accounts[dict_row['loyalty_plan_id']] = [ppl_scheme_dict]

    def _query_payment_accounts(self) -> None:
        self.payment_accounts = []
        query = (
            select(PaymentAccount.id,
                   PaymentAccount.status,
                   PaymentAccount.card_nickname,
                   PaymentAccount.name_on_card,
                   PaymentAccount.expiry_month,
                   PaymentAccount.expiry_year,
                   )
            .join(PaymentAccountUserAssociation)
            .join(User)
            .where(
                User.id == self.user_id,
                PaymentAccount.is_deleted.is_(False)
            )
        )

        accounts = self.db_session.execute(query).all()
        for account in accounts:
            account_dict = dict(account)
            account_dict['pll_links'] = self.pll_for_payment_accounts.get(account_dict['id'])
            self.payment_accounts.append(account_dict)

    def _query_scheme_accounts(self) -> None:
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
                SchemeOverrideError
            )
            .join(SchemeAccountUserAssociation, SchemeAccountUserAssociation.scheme_account_id == SchemeAccount.id)
            .join(Scheme)
            .join(SchemeOverrideError, SchemeOverrideError.scheme_id == Scheme.id, isouter=True)
            .where(
                SchemeAccountUserAssociation.user_id == self.user_id,
                SchemeAccount.is_deleted.is_(False)
            )
        )
        results = self.db_session.execute(query).all()

        for result in results:
            entry = {}
            data_row = dict(result)
            print(data_row)
            entry["id"] = data_row["id"]
            entry["loyalty_plan_id"] = data_row["scheme_id"]
            if data_row["SchemeOverrideError"]:
                override_status = data_row["SchemeOverrideError"]
                entry["status"] = {
                    "slug": override_status.error_slug,
                    "description": override_status.message
                }
            else:
                status_dict = LoyaltyCardStatus.STATUS_DICT.get(data_row["status"])
                entry["status"] = {
                    "slug": status_dict[0],
                    "description": status_dict[1]
                }

            if data_row["status"] in JOIN_IN_PROGRESS_STATES:
                entry["status"]["state"] = "failed"
                # If a join card we have the data so save for set data and move on to next loyalty account
                self.joins.append(data_row)
                continue

            # Process additional fields for Loyalty cards section
            entry["status"]["state"] = "failed"
            entry["balance"] = get_balance_dict(data_row["balances"])
            entry["transactions"] = []
            entry["vouchers"] = []
            entry["card"] = add_fields(data_row, fields=["barcode", "barcode_type", "card_number", "colour"])
            entry["pll_links"] = self.pll_for_schemes_accounts.get(data_row["id"])
            self.loyalty_cards.append(entry)
