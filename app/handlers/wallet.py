
from dataclasses import dataclass

from sqlalchemy import select

from app.handlers.base import BaseHandler
from app.hermes.models import (
    PaymentAccount, PaymentAccountUserAssociation, User,
    PaymentSchemeAccountAssociation, SchemeAccount, Scheme, PaymentCard
)


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
        query = (
            select(SchemeAccount.id,
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
                PaymentAccount.is_deleted.is_(False),
            )
        )

