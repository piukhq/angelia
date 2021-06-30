class TestTransactionMatchingContext:
    """ Transaction matching """
    amex_token = ""
    transaction_matching_id = ""
    transaction_matching_uuid = ""
    transaction_matching_amount = ""
    transaction_matching_currentTimeStamp = ""
    transaction_matching_amexTimeStamp = ""
    container_name = "harmonia-imports"
    file_name = ""

    iceland_file_header = ['TransactionCardFirst6', 'TransactionCardLast4', 'TransactionCardExpiry',
                           'TransactionCardSchemeId', 'TransactionCardScheme', 'TransactionStore_Id',
                           'TransactionTimestamp', 'TransactionAmountValue', 'TransactionAmountUnit',
                           'TransactionCashbackValue', 'TransactionCashbackUnit', 'TransactionId',
                           'TransactionAuthCode']
