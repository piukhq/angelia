from tests_qa import config
from tests_qa.tests import api
from tests_qa.tests.api.base import Endpoint
from tests_qa.tests.helpers.test_context import TestContext
from tests_qa.tests.payload.service.customer_accounts import UserDetails


class CustomerAccount:
    """Functions used to Create a new user, Service consent and Delete a user
    and
    Login using an existing user(User Login credentials are kept in test_data_sheet based in environment)"""

    @staticmethod
    def login_bink_user():
        url = Endpoint.BASE_URL + api.ENDPOINT_LOGIN
        headers = Endpoint.request_header()
        client_id = config.BINK.client_id
        payload = UserDetails.bink_login_user_payload(client_id, config.BINK.bundle_id)
        response = Endpoint.call(url, headers, "POST", payload)
        TestContext.token = response.json().get("api_key")
        return response
