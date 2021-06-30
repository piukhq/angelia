ENDPOINT_LOGIN = "/users/login"
ENDPOINT_REGISTER = "/users/register"
ENDPOINT_SERVICE = "/ubiquity/service"

ENDPOINT_MEMBERSHIP_CARDS = "/ubiquity/membership_cards"
ENDPOINT_MEMBERSHIP_CARD = "/ubiquity/membership_card/{}"
ENDPOINT_AUTO_LINK_PAYMENT_AND_MEMBERSHIP_CARD = "/ubiquity/membership_cards?autolink=true"
ENDPOINT_AUTO_LINK_FALSE = "/ubiquity/membership_cards?autolink=false"
ENDPOINT_PATCH_MEMBERSHIP_PAYMENT = "/ubiquity/membership_card/{}/payment_card/{}"
ENDPOINT_PATCH_PAYMENT_MEMBERSHIP = "/ubiquity/payment_card/{}/membership_card/{}"
ENDPOINT_CHECK_MEMBERSHIP_CARDS_BALANCE = "/ubiquity/membership_cards?balances"

ENDPOINT_MEMBERSHIP_PLAN = "/ubiquity/membership_plan/{}"
ENDPOINT_MEMBERSHIP_PLANS = "/ubiquity/membership_plans"

ENDPOINT_MEMBERSHIP_TRANSACTIONS = "/ubiquity/membership_transactions"
ENDPOINT_MEMBERSHIP_CARD_TRANSACTIONS = "/ubiquity/membership_card/{}/membership_transactions"
ENDPOINT_MEMBERSHIP_CARD_SINGLE_TRANSACTION = "/ubiquity/membership_transaction/{}"

ENDPOINT_PAYMENT_CARD = "/ubiquity/payment_card/{}"
ENDPOINT_LINK_PAYMENT_MEMBERSHIP = "/ubiquity/payment_card/{}/membership_card/{}"
ENDPOINT_PAYMENT_CARDS = "/ubiquity/payment_cards"

# --------------------Transaction Matching API--------------------------------------------
ENDPOINT_MASTER_CARD = "/auth_transactions_mock/mastercard"
ENDPOINT_AMEX_CARD_REGISTER = "/auth_transactions/authorize"
ENDPOINT_AMEX_CARD = "/auth_transactions/amex"
ENDPOINT_VISA_CARD = "/auth_transactions/visa"
