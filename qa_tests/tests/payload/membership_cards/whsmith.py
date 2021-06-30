import logging
import json

from faker import Faker
from tests.helpers.test_data_utils import TestDataUtils
import tests.helpers.constants as constants


class WHSmithCard:
    @staticmethod
    def add_membership_card_payload(invalid_data=None):
        if invalid_data:
            value = TestDataUtils.TEST_DATA.whsmith_invalid_data.get(constants.CARD_NUM)
            logging.info("Invalid data is: " + value)
        else:
            value = TestDataUtils.TEST_DATA.whsmith_membership_card.get(constants.CARD_NUM)

        payload = {
            "account": {
                "authorise_fields": [
                    {
                        "column": "Rewards number",
                        "value": value
                    }
                ]
            },
            "membership_plan": TestDataUtils.TEST_DATA.membership_plan_id.get("whsmith")
        }
        logging.info("The Request for Add Journey : \n" + json.dumps(payload, indent=4))
        return payload

    @staticmethod
    def enrol_membership_scheme_payload(email, env=None, channel=None, invalid_data=None):
        faker = Faker()

        if invalid_data:
            value = TestDataUtils.TEST_DATA.whsmith_invalid_data.get(constants.EMAIL)
            logging.info("Invalid data is: " + value)
        else:
            value = email

        payload = {
            "account": {
                "enrol_fields": [
                    {"column": "Email", "value": value},
                    {"column": "Title", "value": constants.TITLE},
                    {"column": "First name", "value": faker.name()},
                    {"column": "Last name", "value": faker.name()},
                    {"column": "Mobile number", "value": faker.phone_number()},
                    {"column": "Address line 1", "value": faker.building_number()},
                    {"column": "City", "value": faker.city()},
                    {"column": "Postcode", "value": faker.postcode()},
                    {"column": "Consent 1", "value": constants.CONSENT},
                ]
            },
            "membership_plan": TestDataUtils.TEST_DATA.membership_plan_id.get("whsmith"),
        }
        logging.info("The Request for Enrol Journey : \n" + json.dumps(payload, indent=4))
        return payload
