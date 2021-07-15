import json
import logging

import qa_tests.tests.api as api
from qa_tests import config
from qa_tests.tests.api.base import Endpoint
from qa_tests.tests.helpers.test_context import TestContext
from qa_tests.tests.helpers.vault import channel_vault
from qa_tests.tests.helpers.vault.channel_vault import KeyType


class PaymentCardDetails:
    FIELDS_TO_ENCRYPT = ("first_six_digits", "last_four_digits", "month", "year", "hash")

    @staticmethod
    def enrol_payment_card_payload_encrypted(card_provider):

        payment_card = PaymentCardDetails.enrol_payment_card_payload_unencrypted(card_provider)
        if TestContext.channel_name == config.BINK.channel_name:
            pub_key = channel_vault.get_key(config.BINK.bundle_id, KeyType.PUBLIC_KEY)
        elif TestContext.channel_name == config.BARCLAYS.channel_name:
            pub_key = channel_vault.get_key(config.BARCLAYS.bundle_id, KeyType.PUBLIC_KEY)
        payload = PaymentCardDetails.encrypt(payment_card, pub_key)
        logging.info(
            "The Request to enrol encrypted new payment card is : \n\n"
            + Endpoint.BASE_URL
            + api.ENDPOINT_PAYMENT_CARDS
            + "\n\n"
            + json.dumps(payload, indent=4)
        )

    @staticmethod
    def encrypt(payment_card, pub_key):
        # for field in PaymentCardDetails.FIELDS_TO_ENCRYPT:
        #     cred = payment_card["card"].get(field)
        #     if not cred:
        #         raise ValueError(f"Missing credential {field}")
        #     try:
        #         encrypted_val = RSACipher().encrypt(cred, pub_key=pub_key)
        #     except Exception as e:
        #         raise ValueError(f"Value: {cred}") from e
        #     payment_card["card"][field] = encrypted_val

        return payment_card

    @staticmethod
    def enrol_payment_card_payload_unencrypted(card_provider):
        return card_provider
