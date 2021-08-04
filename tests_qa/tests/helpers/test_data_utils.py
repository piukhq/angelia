from tests_qa import config


class TestDataUtils:
    """Setting the test data sheet based on the environment"""

    @staticmethod
    def set_test_data(env):
        TestDataUtils.TEST_DATA = getattr(config, env.upper()).test_data
