import logging
from dataclasses import dataclass
import tests.helpers.database.setupdb as db


@dataclass
class MatchedTransactionRecord:
    count: int


class QueryHarmonia:
    @staticmethod
    def fetch_match_transaction_count(transaction_id, amount):
        """Fetch the matched account details using matched_transaction_id and amount """
        connection = db.connect_harmonia_db()
        record = db.execute_query_fetch_one(connection, get_matched_query(transaction_id, amount))
        if record is None:
            raise Exception(f"'{transaction_id}' is an Invalid transaction_id")
        else:
            matched_transaction_record = MatchedTransactionRecord(record[0])
        db.clear_db(connection)
        return matched_transaction_record


def get_matched_query(transaction_id, amount):
    transaction_query_account = "SELECT count(*) FROM harmonia.public.matched_transaction WHERE transaction_id='{}' " \
                                "and spend_amount={}".format(transaction_id, amount)
    logging.info(transaction_query_account)
    return transaction_query_account
