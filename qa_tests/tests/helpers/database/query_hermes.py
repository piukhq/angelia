import logging
import datetime
from dataclasses import dataclass

import tests.helpers.database.setupdb as db
from tests.helpers.database.settings import LOCAL_AES_KEY
from shared_config_storage.credentials.encryption import AESCipher


@dataclass
class SchemeAccountRecord:
    id: int
    status: int
    scheme_id: int
    link_or_join_date: datetime.datetime
    main_answer: str


@dataclass
class PaymentAccountRecord:
    id: int
    activation_id: str
    status: int
    payment_card_account_id: str
    scheme_id: int


@dataclass
class CredentialAns:
    """sub- Set of credential answers
     All credential answers need not be captured as some of them are
     already verifying as apart of response"""

    card_number: int
    email: str
    last_name: str
    postcode: str
    merchant_identifier: str
    date_of_birth: str


class QueryHermes:
    @staticmethod
    def fetch_scheme_account(journey_type, scheme_account_id):
        """Fetch the scheme account details using scheme_account_id """
        connection = db.connect_db()
        record = db.execute_query_fetch_one(connection, get_query(journey_type, scheme_account_id))

        if record is None:
            raise Exception(f"'{scheme_account_id}' is an Invalid Scheme account id")
        else:
            scheme_account_record = SchemeAccountRecord(record[0],
                                                        record[1],
                                                        record[2],
                                                        record[3],
                                                        record[4])
        db.clear_db(connection)
        return scheme_account_record

    @staticmethod
    def get_vop_status(payment_card_account_id):
        connection = db.connect_db()

        query_payment_account = """SELECT * from hermes.public.ubiquity_vopactivation
                     where payment_card_account_id='%s'""" % payment_card_account_id
        record = db.execute_query_fetch_one(connection, query_payment_account)
        if record is None:
            raise Exception(f"'{payment_card_account_id}' is an Invalid Scheme account id")
        else:
            payment_account_record = PaymentAccountRecord(record[0], record[1], record[2], record[3], record[4])
        db.clear_db(connection)
        return payment_account_record

    @staticmethod
    def fetch_credential_ans(merchant, scheme_account_id):
        """Query all credential answers for the current scheme"""
        connection = db.connect_db()
        query_credential_ans = """SELECT * FROM hermes.public.scheme_schemeaccountcredentialanswer
             where scheme_account_id='%s'""" % scheme_account_id
        record = db.execute_query_fetch_all(connection, query_credential_ans)

        if record is None:
            raise Exception(f"Credential answers are not saved in DB for scheme account '{scheme_account_id}'")
        else:
            logging.info(merchant + " Scheme Account  Credential Answers are:"
                                    "\n..............................................................................")

            fields_to_verify = ("card_number", "email", "last_name", "postcode", "merchant_identifier", "date_of_birth")
            fields_to_decrypt = ("last_name", "postcode", "date_of_birth")

            for row in record:
                credential_qn_label = get_credential_qn_label(row[3], connection)
                question = credential_qn_label[0]
                answer = row[1]

                logging.info(f" '{question}' is '{answer}'")

                if question in fields_to_verify:
                    if question in fields_to_decrypt:
                        answer = decrypt(answer)
                        logging.info(f"Decrypted value of {question} is '{answer}'")

                setattr(CredentialAns, question, answer)

            logging.info("..............................................................................")

            db.clear_db(connection)
            return CredentialAns

    @staticmethod
    def fetch_payment_account_status(journey_type, payment_account_id):
        """Fetch the scheme account details using scheme_account_id """
        connection = db.connect_db()
        record = db.execute_query_fetch_one(connection, get_query(journey_type, payment_account_id))
        if record is None:
            raise Exception(f"'{payment_account_id}' is an Invalid Scheme account id")
        else:
            scheme_account_record = SchemeAccountRecord(record[0],
                                                        record[1],
                                                        record[2],
                                                        record[3],
                                                        record[4])
        db.clear_db(connection)
        return scheme_account_record


def get_credential_qn_label(qn_id, connection):
    """The label for each credential answer has been fetched using the unique question_id
    which is obtained from scheme_schemeaccountcredentialanswer table"""

    query_credential_qns = """SELECT type FROM
                           hermes.public.scheme_schemecredentialquestion
                           where id='%s'""" % qn_id
    return db.execute_query_fetch_one(connection, query_credential_qns)


def get_query(journey_type, scheme_account_id):
    """Differentiate query to scheme_schemeaccount table for Add & Enrol Journeys"""
    if journey_type == "Enrol":
        query_scheme_account = """SELECT id,status,scheme_id,join_date,main_answer
         FROM hermes.public.scheme_schemeaccount WHERE id='%s'""" % scheme_account_id
    elif journey_type == "Add":
        query_scheme_account = """SELECT id,status,scheme_id,link_date,main_answer
                 FROM hermes.public.scheme_schemeaccount WHERE id='%s'""" % scheme_account_id

    return query_scheme_account


def decrypt(val):
    """Decrypt the Scheme Credential answers"""
    return AESCipher(LOCAL_AES_KEY.encode()).decrypt(val)
