import sys

import sentry_sdk
from decouple import Choices, config
from sentry_sdk.integrations.falcon import FalconIntegration
from sentry_sdk.integrations.loguru import LoguruIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from app.version import __version__

VALID_LOG_LEVELS = Choices(("NOTSET", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"))


# For generating image urls
CUSTOM_DOMAIN = config("CUSTOM_DOMAIN", "https://api.dev.gb.bink.com/content/media/hermes")

TESTING = (len(sys.argv) > 1 and sys.argv[1] == "test") or any("pytest" in arg for arg in sys.argv)

DEBUG = config("DEV_HOST", False, cast=bool)
RELOADER = config("RELOADER", False, cast=bool)
DEV_PORT = config("DEV_PORT", 6502, cast=int)
DEV_HOST = config("DEV_HOST", "127.0.0.1")

# Logging configuration.
DEFAULT_LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <cyan>{extra[logger_type]}</cyan> | <level>{level}</level> "
    "| {name} | {function}:{line} - <level>{message}</level>"
)
LOG_LEVEL = config("LOG_LEVEL", default="DEBUG", cast=VALID_LOG_LEVELS)
LOG_FORMAT = config("LOG_FORMAT", default=DEFAULT_LOG_FORMAT)

JSON_LOGGING = config("JSON_LOGGING", True, cast=bool)
QUERY_LOGGING = config("QUERY_LOGGING", False, cast=bool)

POSTGRES_DSN = config("POSTGRES_DSN", "postgresql://postgres@127.0.0.1:5432/hermes")
POSTGRES_CONNECT_ARGS = {"application_name": "angelia"}

RABBIT_USER = config("RABBIT_USER", "")  # eg 'guest'
RABBIT_PASSWORD = config("RABBIT_PASSWORD", "")
RABBIT_HOST = config("RABBIT_HOST", "")
RABBIT_PORT = config("RABBIT_PORT", 0, cast=int)
RABBIT_DSN = config("RABBIT_DSN", f"amqp://{RABBIT_USER}:{RABBIT_PASSWORD}@{RABBIT_HOST}:{RABBIT_PORT}/")
TO_HERMES_QUEUE = config("TO_HERMES_QUEUE", "from_angelia")

URL_PREFIX = config("URL_PREFIX", "/v2")

# Metrics
METRICS_SIDECAR_DOMAIN = config("METRICS_SIDECAR_DOMAIN", "localhost")
METRICS_PORT = config("METRICS_PORT", 4000, cast=int)
PERFORMANCE_METRICS = config("PERFORMANCE_METRICS", 0, cast=int)

VAULT_CONFIG = dict(
    # Access to vault same format as Hermes but Angelia does not require everything
    VAULT_URL=config("VAULT_URL", ""),
    # For deployment set LOCAL_SECRETS to False and set up Vault envs
    # For local use without Vault Set LOCAL_CHANNEL_SECRETS to False to True
    # and set LOCAL_SECRETS_PATH to your json file. See example_local_secrets.json for format
    # (Do not commit your local_secrets json which might contain real secrets or edit example_local_secrets.json)
    LOCAL_SECRETS=config("LOCAL_SECRETS", False, cast=bool),
    LOCAL_SECRETS_PATH=config("LOCAL_SECRETS_PATH", "example_local_secrets.json"),
    AES_KEYS_VAULT_NAME=config("AES_KEYS_VAULT_NAME", "aes-keys"),
    API2_ACCESS_SECRETS_NAME=config("API2_ACCESS_SECRETS_NAME", "api2-access-secrets"),
    API2_B2B_SECRETS_BASE_NAME=config("API2_B2B_SECRETS_BASE_NAME", "api2-b2b-secrets-"),
    API2_B2B_TOKEN_KEYS_BASE_NAME=config("API2_B2B_TOKEN_KEYS_BASE_NAME", "api2-b2b-token-key-"),
)

# Sentry
SENTRY_DSN = config("SENTRY_DSN", None)
SENTRY_ENVIRONMENT = config("SENTRY_ENVIRONMENT", "local_test").lower()
SENTRY_SAMPLE_RATE = config("SENTRY_SAMPLE_RATE", 0.0, cast=float)

if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        release=__version__,
        environment=SENTRY_ENVIRONMENT,
        integrations=[
            FalconIntegration(),
            SqlalchemyIntegration(),
            LoguruIntegration(),
        ],
        traces_sample_rate=SENTRY_SAMPLE_RATE,
    )

PENDING_VOUCHERS_FLAG = config("PENDING_VOUCHERS_FLAG", False, cast=bool)
