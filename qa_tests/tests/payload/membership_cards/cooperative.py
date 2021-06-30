import logging
import json
from faker import Faker

from tests.api.base import Endpoint
import tests.api as api
from tests.helpers.test_data_utils import TestDataUtils
import tests.helpers.constants as constants


class CoopCard:
    @staticmethod
    def add_membership_card_payload(invalid_data=None):
        if invalid_data:
            value = TestDataUtils.TEST_DATA.coop_invalid_data.get(constants.POSTCODE)
            logging.info("Invalid data is: " + value)
            data_type = "Invalid data"
        else:
            value = TestDataUtils.TEST_DATA.coop_membership_card.get(constants.POSTCODE)
            data_type = "Valid data"

        payload = {
            "account": {
                "add_fields": [
                    {
                        "column": "Membership card number",
                        "value": TestDataUtils.TEST_DATA.coop_membership_card.get(constants.CARD_NUM)
                    }
                ],
                "authorise_fields": [
                    {
                        "column": "Date of birth",
                        "value": TestDataUtils.TEST_DATA.coop_membership_card.get(constants.DOB)
                    },
                    {
                        "column": "Postcode",
                        "value": value
                    }
                ]
            },
            "membership_plan": TestDataUtils.TEST_DATA.membership_plan_id.get("coop"),
        }

        logging.info("The Request for Add Journey with " + data_type + " :\n\n"
                     + Endpoint.BASE_URL + api.ENDPOINT_MEMBERSHIP_CARDS + "\n\n" + json.dumps(payload, indent=4))
        return payload

    @staticmethod
    def enrol_membership_scheme_payload(email, env=None, channel=None, invalid_data=None):
        faker = Faker()

        if invalid_data:
            value = TestDataUtils.TEST_DATA.coop_invalid_data.get("email")
            logging.info("Invalid data is: " + value)
            data_type = "Invalid data"
        else:
            value = email
            data_type = "Valid data"
        payload = {
            "account": {
                "enrol_fields": [
                    {"column": "Date of birth", "value": constants.DATE_OF_BIRTH},
                    {"column": "Title", "value": constants.TITLE},
                    {"column": "First name", "value": faker.name()},
                    {"column": "Last name", "value": faker.name()},
                    {"column": "Email", "value": value},
                    {"column": "Address line 1", "value": faker.building_number()},
                    {"column": "Address line 2", "value": faker.street_address()},
                    {"column": "City", "value": faker.city()},
                    {"column": "Postcode", "value": faker.postcode()},
                ]
            },
            "membership_plan": TestDataUtils.TEST_DATA.membership_plan_id.get("coop"),
        }
        logging.info("The Request for Enrol Journey with " + data_type + " :\n\n"
                     + Endpoint.BASE_URL + api.ENDPOINT_MEMBERSHIP_CARDS + "\n\n" + json.dumps(payload, indent=4))
        return payload
