import logging
import json
import config
from faker import Faker

import tests.api as api
import tests.helpers.constants as constants
from tests.api.base import Endpoint
from tests.helpers.vault import channel_vault
from tests.helpers.vault.channel_vault import KeyType
from tests.helpers.test_context import TestContext
from tests.helpers.test_data_utils import TestDataUtils
from shared_config_storage.credentials.encryption import RSACipher


class HarveyNicholsCard:
    @staticmethod
    def add_membership_card_payload(invalid_data=None):
        if invalid_data:
            value = TestDataUtils.TEST_DATA.harvey_nichols_invalid_data.get(constants.ID)
            logging.info("Invalid data is: " + value)
            data_type = "Invalid data"
        else:
            value = TestDataUtils.TEST_DATA.harvey_nichols_membership_card.get(constants.ID)
            data_type = "Valid data"

        sensitive_value = TestDataUtils.TEST_DATA.harvey_nichols_membership_card.get(constants.PASSWORD)

        if TestContext.flag_encrypt == "true":
            if TestContext.channel_name == config.BINK.channel_name:
                pub_key = channel_vault.get_key(config.BINK.bundle_id, KeyType.PUBLIC_KEY)
            elif TestContext.channel_name == config.BARCLAYS.channel_name:
                pub_key = channel_vault.get_key(config.BARCLAYS.bundle_id, KeyType.PUBLIC_KEY)

            password = RSACipher().encrypt(sensitive_value, pub_key)

        elif TestContext.flag_encrypt == "false":
            password = sensitive_value

        payload = {
            "account": {
                "authorise_fields": [
                    {"column": "Email",
                     "value": value
                     },
                    {
                        "column": "Password",
                        "value": password
                    }
                ]
            },
            "membership_plan": TestDataUtils.TEST_DATA.membership_plan_id.get("harvey_nichols"),
        }
        logging.info("The Request for Add Journey with " + data_type + " :\n\n"
                     + Endpoint.BASE_URL + api.ENDPOINT_MEMBERSHIP_CARDS + "\n\n" + json.dumps(payload, indent=4))
        return payload

    @staticmethod
    def add_membership_card_2_payload():
        if TestContext.channel_name == config.BINK.channel_name:
            pub_key = channel_vault.get_key(config.BINK.bundle_id, KeyType.PUBLIC_KEY)
        elif TestContext.channel_name == config.BARCLAYS.channel_name:
            pub_key = channel_vault.get_key(config.BARCLAYS.bundle_id, KeyType.PUBLIC_KEY)
        sensitive_value = TestDataUtils.TEST_DATA.harvey_nichols_membership_card.get(constants.PASSWORD)

        payload = {
            "account": {
                "authorise_fields": [
                    {"column": "Email",
                     "value": TestDataUtils.TEST_DATA.harvey_nichols_membership_card_2.get(constants.ID)
                     },
                    {
                        "column": "Password",
                        "value": RSACipher().encrypt(sensitive_value, pub_key)
                    }
                ]
            },
            "membership_plan": TestDataUtils.TEST_DATA.membership_plan_id.get("harvey_nichols"),
        }
        logging.info("The Request for Add Journey membership_card_2 :\n\n"
                     + Endpoint.BASE_URL + api.ENDPOINT_MEMBERSHIP_CARDS + "\n\n" + json.dumps(payload, indent=4))
        return payload

    @staticmethod
    def enrol_membership_scheme_payload(email, env=None, channel=None, invalid_data=None):
        faker = Faker()

        if invalid_data:
            value = TestDataUtils.TEST_DATA.harvey_nichols_invalid_data.get("id")
            logging.info("Invalid data is: " + value)
            data_type = "Invalid data"
        else:
            value = email
            data_type = "Valid data"
        sensitive_value = constants.PASSWORD_ENROL
        pub_key = channel_vault.get_key(config.BARCLAYS.bundle_id, KeyType.PUBLIC_KEY)
        payload = {
            "account": {
                "enrol_fields": [
                    {"column": "Title", "value": constants.TITLE},
                    {"column": "First name", "value": faker.name()},
                    {"column": "Last name", "value": faker.name()},
                    {"column": "Email", "value": value},
                    {"column": "Password", "value": RSACipher().encrypt(sensitive_value, pub_key)},
                    {"column": "Mobile number", "value": faker.phone_number()},
                    {"column": "Consent 1", "value": constants.CONSENT},
                ]
            },
            "membership_plan": TestDataUtils.TEST_DATA.membership_plan_id.get("harvey_nichols"),
        }
        logging.info("The Request for Enrol Journey with " + data_type + " :\n\n"
                     + Endpoint.BASE_URL + api.ENDPOINT_MEMBERSHIP_CARDS + "\n\n" + json.dumps(payload, indent=4))
        return payload
