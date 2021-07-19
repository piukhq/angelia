import json

from app.report import automation_tests_logger
from tests_qa.tests.helpers.test_data_utils import TestDataUtils
import tests_qa.tests.helpers.constants as constants


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
        automation_tests_logger.info("Request body for POST Login" + json.dumps(payload, indent=4))
        return payload