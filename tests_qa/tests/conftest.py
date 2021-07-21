import logging

import pytest
from faker import Faker
from pytest_bdd import given

from tests_qa import config
from tests_qa.tests.api.base import Endpoint
from tests_qa.tests.helpers import constants
from tests_qa.tests.helpers.test_context import TestContext
from tests_qa.tests.helpers.test_data_utils import TestDataUtils
from tests_qa.tests.requests.service import CustomerAccount


def pytest_bdd_step_error(request, feature, scenario, step, step_func, step_func_args, exception):
    """This function will log the failed BDD-Step at the end of logs"""
    logging.info(f"Step failed: {step}")


def pytest_html_report_title(report):
    """Customized title for html report"""
    report.title = "Automation Result_PytestBDD API2.0"


@pytest.fixture(scope="session", autouse=True)
def configure_html_report_env(request, env, channel):
    """Delete existing data in the test report and add bink api execution details"""
    for ele in list(request.config._metadata.keys()):
        del request.config._metadata[ele]
    # if re.search(r'^(GITLAB_|CI_)', k): for git lab related extra table contents
    request.config._metadata.update({"Test Environment": env.upper(), "Channel": channel.upper()})


"""Reading inputs from terminal"""


def pytest_addoption(parser):
    parser.addoption("--channel", action="store", default="bink", help="Channel: can be bink or barclays should pass")
    parser.addoption("--env", action="store", default="dev", help="env : can be dev or staging or prod")
    parser.addoption("--encryption", action="store", default="false", help="encryption : can be true or false")


"""Terminal parameter Fixtures"""


@pytest.fixture(scope="session")
def channel(pytestconfig):
    """Returns current channel"""
    return pytestconfig.getoption("channel")


@pytest.fixture(scope="session")
def env(pytestconfig):
    """Returns current environment"""
    return pytestconfig.getoption("env")


@pytest.fixture(scope="session")
def encryption(pytestconfig):
    """Returns the choice: with/without encryption"""
    return pytestconfig.getoption("encryption")


@pytest.fixture(scope="session", autouse=True)
def set_environment(env):
    Endpoint.set_environment(env)
    logging.info("Environment Setup ready")
    TestDataUtils.set_test_data(env)


@pytest.fixture(scope="session", autouse=True)
def handle_optional_encryption(encryption):
    TestContext.flag_encrypt = encryption


@pytest.fixture()
def test_email():
    faker = Faker()
    return constants.EMAIL_TEMPLATE.replace("email", str(faker.random_int(100, 999999)))


@given("I am a Bink user")
def login_user(channel, env):
    TestContext.channel_name = channel
    if channel == config.BINK.channel_name:
        response = CustomerAccount.login_bink_user()
        if response is not None:
            try:
                logging.info(f"POST Login response: {response.json()} ")
                assert response.status_code == 200 and response.json().get(
                    "email"
                ) == TestDataUtils.TEST_DATA.bink_user_accounts.get(
                    constants.USER_ID
                ), "User login in Bink Channel is not successful"
                return TestContext.token
            except Exception as e:
                logging.info(f"Gateway Timeout error :{e}")
