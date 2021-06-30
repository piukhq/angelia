class TestContext:
    current_scheme_account_id = ""
    current_payment_card_id = ""
    token = ""
    transaction_id = ""
    response = ""
    payment_card_hash = ""
    card_number = ""
    """Below variables are used to ensure complete execution
     and deletion of membership& payment cards after ubiquity scenarios"""

    channel_name = ""
    token_channel_1 = ""
    scheme_account_id1 = ""

    """when multiple payment cards are added to wallet, delete them at the end of execution"""
    payment_card_1 = ""
    payment_card_2 = ""
    payment_card_3 = ""

    """Variable that decides encryption is required / not"""
    flag_encrypt = ""
