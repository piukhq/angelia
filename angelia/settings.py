import sys
from typing import ClassVar, Literal

import sentry_sdk
from pydantic import BaseConfig, BaseSettings, Extra, validator
from sentry_sdk.integrations.falcon import FalconIntegration
from sentry_sdk.integrations.loguru import LoguruIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from angelia.version import __version__

LogLevelType = Literal["NOTSET", "DEBUG", "INFO", "WARNING", "ERROR"]


class SettingsConfig(BaseConfig):
    extras = Extra.ignore
    case_sensitive = True
    # env var settings priority ie priority 1 will override priority 2:
    # 1 - env vars already loaded (ie the one passed in by kubernetes)
    # 2 - env vars read from .env file
    # 3 - values assigned directly in the Settings class
    env_file = ".env"
    env_file_encoding = "utf-8"


class VaultConfig(BaseSettings):
    VAULT_URL: str = ""
    # For deployment set LOCAL_SECRETS to False and set up Vault envs
    # For local use without Vault Set LOCAL_CHANNEL_SECRETS to False to True
    # and set LOCAL_SECRETS_PATH to your json file. See example_local_secrets.json for format
    # (Do not commit your local_secrets json which might contain real secrets or edit example_local_secrets.json)
    LOCAL_SECRETS: bool = False
    LOCAL_SECRETS_PATH: str = "example_local_secrets.json"
    AES_KEYS_VAULT_NAME: str = "aes-keys"
    API2_ACCESS_SECRETS_NAME: str = "api2-access-secrets"
    API2_B2B_SECRETS_BASE_NAME: str = "api2-b2b-secrets-"
    API2_B2B_TOKEN_KEYS_BASE_NAME: str = "api2-b2b-token-key-"

    Config = SettingsConfig


class Settings(BaseSettings):
    # For generating image urls
    CUSTOM_DOMAIN: str = "https://api.dev.gb.bink.com/content/media/hermes"

    TESTING: bool = False

    @validator("TESTING", pre=False)
    @classmethod
    def testing_validator(cls, value: bool) -> bool:
        return value or (len(sys.argv) > 1 and sys.argv[1] == "test") or any("pytest" in arg for arg in sys.argv)

    DEBUG: bool = False
    RELOADER: bool = False
    DEV_PORT: int = 6502
    DEV_HOST: str = "127.0.0.1"

    # Logging configuration.
    DEFAULT_LOG_FORMAT: ClassVar[str] = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <cyan>{extra[logger_type]}</cyan> | <level>{level}</level> "
        "| <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )

    LOG_LEVEL: LogLevelType = "DEBUG"
    LOG_FORMAT: str = DEFAULT_LOG_FORMAT

    JSON_LOGGING: bool = True
    QUERY_LOGGING: bool = False

    POSTGRES_DSN: str = "postgresql://postgres@127.0.0.1:5432/hermes"
    POSTGRES_CONNECT_ARGS: ClassVar[dict[str, str]] = {"application_name": "angelia"}

    RABBIT_USER: str = ""  # eg 'guest'
    RABBIT_PASSWORD: str = ""
    RABBIT_HOST: str = ""
    RABBIT_PORT: int = 0
    RABBIT_DSN: str = f"amqp://{RABBIT_USER}:{RABBIT_PASSWORD}@{RABBIT_HOST}:{RABBIT_PORT}/"
    TO_HERMES_QUEUE: str = "angelia-hermes-bridge"
    TO_HERMES_QUEUE_ROUTING_KEY: str = "angelia"
    PUBLISH_MAX_RETRIES: int = 3
    PUBLISH_RETRY_BACKOFF_FACTOR: float = 0.25

    URL_PREFIX: str = "/v2"

    # Metrics
    METRICS_SIDECAR_DOMAIN: str = "localhost"
    METRICS_PORT: int = 4000
    PERFORMANCE_METRICS: int = 0

    VAULT_CONFIG: VaultConfig = VaultConfig()

    # Sentry
    SENTRY_DSN: str | None = None
    SENTRY_ENVIRONMENT: str = "local_test"

    @validator("SENTRY_ENVIRONMENT", pre=False)
    @classmethod
    def sentry_env_validator(cls, value: str) -> str:
        return value.lower()

    SENTRY_SAMPLE_RATE: float = 0.0

    Config = SettingsConfig


settings = Settings()

if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        release=__version__,
        environment=settings.SENTRY_ENVIRONMENT,
        integrations=[
            FalconIntegration(),
            SqlalchemyIntegration(),
            LoguruIntegration(),
        ],
        traces_sample_rate=settings.SENTRY_SAMPLE_RATE,
    )
