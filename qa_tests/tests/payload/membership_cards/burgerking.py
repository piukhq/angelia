import logging
import json
from faker import Faker

from tests.api.base import Endpoint
import tests.api as api
from tests.helpers.test_data_utils import TestDataUtils
import tests.helpers.constants as constants
from tests.helpers.test_context import TestContext


class BurgerKingCard:
    @staticmethod
    def add_membership_card_payload(invalid_data=None):
        if invalid_data:
            value = TestDataUtils.TEST_DATA.burger_king_invalid_data.get(constants.CARD_NUM)
            logging.info("Invalid data is: " + value)
            data_type = "Invalid data"
        else:
            value = TestDataUtils.TEST_DATA.burger_king_membership_card.get(constants.CARD_NUM)
            data_type = "Valid data"

        payload = {
            "account": {
                "authorise_fields": [
                    {"column": "Rewards number",
                        "value": value
                     }
                ]
            },
            "membership_plan": TestDataUtils.TEST_DATA.membership_plan_id.get("burger_king"),
        }

        logging.info("The Request for Add Journey with " + data_type + " :\n\n"
                     + Endpoint.BASE_URL + api.ENDPOINT_MEMBERSHIP_CARDS + "\n\n" + json.dumps(payload, indent=4))
        return payload

    @staticmethod
    def enrol_membership_scheme_payload(email, env=None, channel=None, invalid_data=None):
        faker = Faker()

        if invalid_data:
            value = TestDataUtils.TEST_DATA.burger_king_invalid_data.get(constants.EMAIL)
            logging.info("Invalid data is: " + value)
            data_type = "Invalid data"
        else:
            value = email
            data_type = "Valid data"
        payload = {
            "account": {
                "enrol_fields": [
                    {"column": "Email", "value": value},
                    {"column": "First name", "value": faker.name()},
                    {"column": "Last name", "value": faker.name()},
                    {"column": "Postcode", "value": faker.postcode()},
                    {"column": "Phone", "value": faker.phone_number()},
                ]
            },
            "membership_plan": TestDataUtils.TEST_DATA.membership_plan_id.get("burger_king"),
        }
        logging.info("The Request for Enrol Journey with " + data_type + " :\n\n"
                     + Endpoint.BASE_URL + api.ENDPOINT_MEMBERSHIP_CARDS + "\n\n" + json.dumps(payload, indent=4))
        return payload

    @staticmethod
    def enrol_delete_add_membership_card_payload(email=None):
        payload = {
            "account": {
                "authorise_fields": [
                    {"column": "Rewards number",
                     "value": TestContext.card_number
                     }
                ]
            },
            "membership_plan": TestDataUtils.TEST_DATA.membership_plan_id.get("burger_king"),
        }
        logging.info("The Request for Add Journey with " + TestContext.card_number + " :\n\n"
                     + Endpoint.BASE_URL + api.ENDPOINT_MEMBERSHIP_CARDS + "\n\n" + json.dumps(payload, indent=4))
        return payload
