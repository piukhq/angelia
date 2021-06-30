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


harvey_nichols_membership_card = {
    "id": "andyjameshill@gmail.com",
    "password": "BinkTest",
    "password_encrypted": "pCgQ7bkUK12JaexMoKGtPjJAg6JazmUg4HHygjwUzT/2pEx9g4H3ps0wYa6koNBGkz1+mDmMsT5n/Ju8uAXRY+FVTxFJAfKNpANv2P52CEHLnKopK/z3E5dSSKRXiTo4jn66uaXByGOz5f12igYj+k84opM8lgsOVwIySWyqveRONGUFk/cA6xz38LldZL+WWxskFEbXMDsuJzlr1DV9lwNK153r+2Rc0IbRJTPnJfchgj9qxVBQhBZzPsDajOJHEs9gcUjHq1MZqtPPcMueQuuxr3OWnnWgAv2Rp8rJ59HoV+3MRX+FKVZEOs/0ImYmebrtrw0/TbdcyWqx4pTXMp+iUDD/AocTxwh8+hwG1VUjNXdNLZPtmxWWq7/3u/uUt+wzJowil/mjxqeX0f4U/YKL20Q/Le92XsZpA54BzDL/IhEuiPuMMC0ix9UAYD/y1y+a5mxrrHYuYzuPQ3iltqYpQP1n24RntBP+siYllNdXnQ74lUhK5hbgF4bgroku0AnsCert79FBEtRTYYDvWuGRdxl0TDkf0ADUsmYpTbvU6sbNEGgpfmB37GcK9dvJDkY00R5l0uq1dA1q/CqydBTVb9YpRm13rSqx6t5U/GHAps50uZx7/jzSET1fk3kG+2PzKsHHFPSaizzEeWtv/tjobtkVsqcl2qqEE1hVvrs=", # noqa
    # noqa
    "card_num": "1000000962497",
    "barcode": "1000000962497",
    "points": 64,
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
    # "card_num": "6332040030555532506",
    # 6332040030541927281
    "card_num": "6332040030555532506",
    "barcode": "633204003055553250600085",
    "last_name": "Armstrong",
    "postcode": "SW18 4HH",
    "points": 5,
    "currency": "GBP",
    "description": "Placeholder Balance Description",
    "transactions": "5",
    "transaction_status": "active",
    "transaction_currency": "GBP",
}

iceland_invalid_data = {
    "email": "fail@unknown.com",
    "postcode": "fail",
}

wasabi_membership_card = {
    "card_num": "",
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
    "burger_king": 279,
    "coop": 243,
    "fat_face": 246,
    "harvey_nichols": 124,
    "iceland": 105,
    "whsmith": 280,
    "wasabi": 281,
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

# bink_user_accounts = {
#     "uid": "drtesting_qa@testbink.com",
#     "pwd": "Password01",
# }

bink_user_accounts = {
    "uid": "njames@bink.com",
    "pwd": "Password01",
}

barclays_user_accounts = {
    "uid": "bmb_qatest@bink.com",
    "pwd": "Bmbtest1",
}
