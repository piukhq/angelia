import json
import logging

from tests_qa.tests.helpers import constants
from tests_qa.tests.helpers.test_data_utils import TestDataUtils


class UserDetails:
    @staticmethod
    def bink_login_user_payload(client_id, bundle_id):
        """Login for Bink user"""
        payload = {
            "email": TestDataUtils.TEST_DATA.bink_user_accounts.get(constants.USER_ID),
            "password": TestDataUtils.TEST_DATA.bink_user_accounts.get(constants.PWD),
            "client_id": client_id,
            "bundle_id": bundle_id,
        }
        logging.info("Request body for POST Login" + json.dumps(payload, indent=4))
        return payload
