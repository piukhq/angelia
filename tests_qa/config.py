from os import environ

from tests_qa.tests_resources.test_data import testdata_staging
from tests_qa.tests_resources.test_data import testdata_dev


class EnvironmentDetails:
    def __init__(self, base_url, test_data, transaction_matching_base_url, transaction_matching_base_url_zephyrus):
        self.base_url = base_url
        self.test_data = test_data
        self.transaction_matching_base_url = transaction_matching_base_url
        self.transaction_matching_base_url_zephyrus = transaction_matching_base_url_zephyrus


if "KUBERNETES_SERVICE_HOST" in environ:
    DEV = EnvironmentDetails(
        base_url="http://hermes-api",
        test_data=testdata_dev,
        transaction_matching_base_url="http://skiron-api",
        transaction_matching_base_url_zephyrus="http://zephyrus-api",
    )
    STAGING = EnvironmentDetails(
        base_url="http://hermes-api",
        test_data=testdata_staging,
        transaction_matching_base_url="http://skiron-api",
        transaction_matching_base_url_zephyrus="http://zephyrus-api",
    )
else:
    DEV = EnvironmentDetails(
        base_url="https://api.dev.gb.bink.com",
        test_data=testdata_dev,
        transaction_matching_base_url="https://api.dev.gb.bink.com",
        transaction_matching_base_url_zephyrus="https://api.dev.gb.bink.com",
    )
    STAGING = EnvironmentDetails(
        base_url="https://api.staging.gb.bink.com",
        test_data=testdata_staging,
        transaction_matching_base_url="https://api.staging.gb.bink.com",
        transaction_matching_base_url_zephyrus="https://api.staging.gb.bink.com",
    )


class ChannelDetails:
    def __init__(self, channel_name, bundle_id, client_id, organisation_id):
        self.channel_name = channel_name
        self.bundle_id = bundle_id
        self.client_id = client_id
        self.organisation_id = organisation_id


BINK = ChannelDetails(
    channel_name="bink",
    bundle_id="com.bink.wallet",
    client_id="MKd3FfDGBi1CIUQwtahmPap64lneCa2R6GvVWKg6dNg4w9Jnpd",
    organisation_id="",
)

