import json
import logging

import arrow
from faker import Faker
from shared_config_storage.credentials.encryption import RSACipher


import qa_tests.config
import qa_tests.tests.api as api
import qa_tests.tests.helpers.constants as constants
from qa_tests.tests.api.base import Endpoint
from qa_tests.tests.helpers.test_context import TestContext
from qa_tests.tests.helpers.test_helpers import PaymentCardTestData
from qa_tests.tests.helpers.vault import channel_vault
from qa_tests.tests.helpers.vault.channel_vault import KeyType


class PaymentCardDetails:
    FIELDS_TO_ENCRYPT = (
        'first_six_digits',
        'last_four_digits',
        'month',
        'year',
        'hash'
    )

    @staticmethod
    def add_payment_card_payload_encrypted(card_provider):

        payment_card = PaymentCardDetails.get_card(card_provider)
        if TestContext.channel_name == qa_tests.config.BINK.channel_name:
            pub_key = channel_vault.get_key(qa_tests.config.BINK.bundle_id, KeyType.PUBLIC_KEY)
        elif TestContext.channel_name == qa_tests.config.BARCLAYS.channel_name:
            pub_key = channel_vault.get_key(qa_tests.config.BARCLAYS.bundle_id, KeyType.PUBLIC_KEY)
        payload = PaymentCardDetails.encrypt(payment_card, pub_key)
        logging.info("The Request to add encrypted payment card is : \n\n"
                     + Endpoint.BASE_URL + api.ENDPOINT_PAYMENT_CARDS + "\n\n" + json.dumps(payload, indent=4))
        return payload

    @staticmethod
    def get_card(card_provider):
        faker = Faker()
        TestContext.payment_card_hash = \
            PaymentCardTestData.get_data(card_provider).get(constants.HASH) + str(faker.random_int())
        return {
            "card": {
                "hash": TestContext.payment_card_hash,
                "token": PaymentCardTestData.get_data(card_provider).get(constants.TOKEN),
                "last_four_digits": PaymentCardTestData.get_data(card_provider).get(constants.LAST_FOUR_DIGITS),
                "first_six_digits": PaymentCardTestData.get_data(card_provider).get(constants.FIRST_SIX_DIGITS),
                "name_on_card": PaymentCardTestData.get_data(card_provider).get(constants.NAME_ON_CARD),
                "month": PaymentCardTestData.get_data(card_provider).get(constants.MONTH),
                "year": PaymentCardTestData.get_data(card_provider).get(constants.YEAR),
                "fingerprint": PaymentCardTestData.get_data(card_provider).get(constants.FINGERPRINT),
            },
            "account": {
                "consents": [{"latitude": 51.405372, "longitude": -0.678357, "timestamp": arrow.utcnow().timestamp,
                              "type": 1}]
            },
        }

    @staticmethod
    def encrypt(payment_card, pub_key):
        for field in PaymentCardDetails.FIELDS_TO_ENCRYPT:
            cred = payment_card['card'].get(field)
            if not cred:
                raise ValueError(f"Missing credential {field}")
            try:
                encrypted_val = RSACipher().encrypt(cred, pub_key=pub_key)
            except Exception as e:
                raise ValueError(f"Value: {cred}") from e
            payment_card['card'][field] = encrypted_val

        return payment_card

    @staticmethod
    def add_payment_card_payload_unencrypted(card_provider):
        faker = Faker()
        TestContext.payment_card_hash = \
            PaymentCardTestData.get_data(card_provider).get(constants.HASH) + str(faker.random_int())
        payload = {
            "card": {
                "hash": TestContext.payment_card_hash,
                "token": PaymentCardTestData.get_data(card_provider).get(constants.TOKEN),
                "last_four_digits": PaymentCardTestData.get_data(card_provider).get(constants.LAST_FOUR_DIGITS),
                "first_six_digits": PaymentCardTestData.get_data(card_provider).get(constants.FIRST_SIX_DIGITS),
                "name_on_card": PaymentCardTestData.get_data(card_provider).get(constants.NAME_ON_CARD),
                "month": PaymentCardTestData.get_data(card_provider).get(constants.MONTH),
                "year": PaymentCardTestData.get_data(card_provider).get(constants.YEAR),
                "fingerprint": PaymentCardTestData.get_data(card_provider).get(constants.FINGERPRINT),
            },
            "account": {
                "consents": [{"latitude": 51.405372, "longitude": -0.678357, "timestamp": arrow.utcnow().timestamp,
                              "type": 1}]
            }
        }

        logging.info("The Request to add payment card is : \n\n"
                     + Endpoint.BASE_URL + api.ENDPOINT_PAYMENT_CARDS + "\n\n" + json.dumps(payload, indent=4))
        return payload
