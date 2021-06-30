# ------------------------------------ ---PAYMENT  CARDS ------------------------------------------------------- #

visa_payment_card = {
    "first_six_digits": "555555",
    "last_four_digits": "4444",
    "token": "auto1093448038331testbinkcom",
    "name_on_card": "auto1093448038331testbinkcom",
    "month": 1,
    "year": 2044,
    "fingerprint": "auto1093448038331testbinkcom",
    "status": "active",
    "active_link": True
}

amex_payment_card = {
    "first_six_digits": "555555",
    "last_four_digits": "4444",
    "token": "auto1093448038331testbinkcom",
    "name_on_card": "auto1093448038331testbinkcom",
    "month": 1,
    "year": 2044,
    "fingerprint": "auto1093448038331testbinkcom",
    "status": "active",
    "active_link": True
}

master_payment_card = {
    "first_six_digits": "555555",
    "last_four_digits": "4444",
    "month": 1,
    "year": 2044,
    "status": "active",
    "active_link": True
}

# ------------------------------------ MEMBERSHIP  CARDS ------------------------------------------------------- #

burger_king_membership_card = {
    "card_num": "BK00000031049422"
    # "BK00000035620277",
}
burger_king_invalid_data = {
    "card_num": "BK00000035941500",
    "email": "fail@unknown.com",
}

coop_membership_card = {
    "card_num": "633174918511516552",
    "dob": "11/11/1984",
    "postcode": "BN16 4HE",
    "points": "0.00p",
    "transactions": "0",
}

coop_ghost_card = {
    "card_num": "",
    "dob": "",
    "postcode": "",
}

coop_invalid_data = {
    "postcode": "fail",
    "email": "fail@unknown.com",
}

coop_ghost_card = {
    "card_num": "6332040030522672674",
    "last_name": "Binktest",
    "dob": "01/01/2000",
    "postcode": "SL5 9FE",
    "points": "",
    "transactions": "",
}

fat_face_membership_card = {
    "card_num": "FF00000059702811",
}

fat_face_invalid_data = {
    "card_num": "FF00000059702810",
}

# harvey_nichols_membership_card = {
#     "id": "auto_zero@testbink.com",
#     "password": "Password01",
#     "card_num": "9123001122330",
#     "barcode": "9123001122330",
#     "points": 0,
#     "currency": "Points",
#     "description": "Placeholder Balance Description",
#     "transactions": "0 ",
#     "transaction_status": "",
#     "transaction_currency": "",
#
# }

harvey_nichols_membership_card = {
    "id": "auto_five@testbink.com",
    "password": "Password01",
    "card_num": "9123001122335",
    "barcode": "9123001122335",
    "points": 380,
    "currency": "Points",
    "description": "Placeholder Balance Description",
    "transactions": "5",
    "transaction_status": "active",
    "transaction_currency": "Points",

}

harvey_nichols_invalid_data = {
    "id": "fail@unknown.com"
}

iceland_membership_card = {
    "card_num": "6666666666666666666",
    "barcode": "6666666666666666666",
    "last_name": "six",
    "postcode": "rg6 6aa",
    "points": 1480,
    "currency": "GBP",
    "description": "Placeholder Balance Description",
    "transactions": "6",
    "transaction_status": "active",
    "transaction_currency": "GBP",

}

# iceland_membership_card = {
#     "card_num": "5555555555555555555",
#     "barcode": "5555555555555555555",
#     "last_name": "five",
#     "postcode": "rg5 5aa",
#     "points": 380.01,
#     "currency": "GBP",
#     "description": "Placeholder Balance Description",
#     "transactions": "5",
#     "transaction_status": "active",
#     "transaction_currency": "GBP",
# }
iceland_invalid_data = {
    "email": "fail@unknown.com",
    "postcode": "fail",
}

wasabi_membership_card = {
    "card_num": "1048172852",
    "email": "binktestuser14@wasabi.com",
    "points": 6,
    "currency": "stamps",
    "description": "",
    "transactions": "",
    "transaction_status": "active",
    "transaction_currency": "stamps",
}

wasabi_invalid_data = {
    "card_num": "",
    "email": "fail@unknown.com",
}

whsmith_membership_card = {
    "card_num": "FF00000004827176",
}

whsmith_invalid_data = {
    "card_num": "WHSmithInvalid_Card",
    "email": "fail@unknown.com",
}

# ----------------------------------------MEMBERSHIP PLAN IDs   ----------------------------------------------- #

membership_plan_id = {
    "burger_king": 314,
    "coop": "",
    "fat_face": 281,
    "harvey_nichols": 194,
    "iceland": 105,
    "whsmith": "",
    "wasabi": 316,
}
# ----------------------------------------MEMBERSHIP ACCOUNT STATES & REASON_CODES ---------------------------------- #

membership_card_status_states = {
    "state_pending": "pending",
    "state_authorised": "authorised",
    "state_failed": "failed",
}
membership_card_status_reason_codes = {
    "reason_code_pending_add": "X100",
    "reason_code_pending_enrol": "X200",
    "reason_code_authorised": "X300",
    "reason_code_failed": "X303",
    "reason_code_failed_enrol": "X201",
}
# ---------------------------------------------USER ACCOUNTS ---------------------------------------------------- #
barclays_user_accounts = {
    "uid": "njames@bink.com",
    "pwd": "Password@200",
}

bink_user_accounts = {
    "uid": "pytest_sit@bink.com",
    "pwd": "Password1",
}
