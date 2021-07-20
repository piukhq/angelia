from os import environ

from tests_qa.tests_resources.test_data import testdata_dev, testdata_staging


class EnvironmentDetails:
    def __init__(self, base_url, test_data):
        self.base_url = base_url
        self.test_data = test_data


if "KUBERNETES_SERVICE_HOST" in environ:
    DEV = EnvironmentDetails(base_url="http://hermes-api", test_data=testdata_dev)
    STAGING = EnvironmentDetails(base_url="http://hermes-api", test_data=testdata_staging)
else:
    DEV = EnvironmentDetails(base_url="https://api.dev.gb.bink.com", test_data=testdata_dev)
    STAGING = EnvironmentDetails(base_url="https://api.staging.gb.bink.com", test_data=testdata_staging)


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
