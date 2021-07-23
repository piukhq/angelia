import logging
import sys

from environment import getenv, read_env, to_bool


def to_log_level(s: str) -> int:
    VALID_LOG_LEVELS = ["NOTSET", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    s = s.upper()
    if s not in VALID_LOG_LEVELS:
        raise ValueError(f"'{s}' is not a valid log level. Must be one of {', '.join(VALID_LOG_LEVELS)}")
    return getattr(logging, s.upper())


read_env()

TESTING = (len(sys.argv) > 1 and sys.argv[1] == "test") or any("pytest" in arg for arg in sys.argv)

# Logging configuration.
DEFAULT_LOG_FORMAT = "%(asctime)s | %(name)18s | %(levelname)8s | %(funcName)s:%(lineno)s - %(message)s"
LOG_LEVEL = getenv("LOG_LEVEL", default="DEBUG", conv=to_log_level)
LOG_FORMAT = getenv("LOG_FORMAT", default=DEFAULT_LOG_FORMAT)

JSON_LOGGING = getenv("JSON_LOGGING", "True", conv=to_bool)

POSTGRES_READ_DSN = getenv("POSTGRES_READ_DSN", "postgresql://postgres@127.0.0.1:5432/hermes")
POSTGRES_WRITE_DSN = getenv("POSTGRES_WRITE_DSN", "postgresql://postgres@127.0.0.1:5432/hermes")

if TESTING:
    POSTGRES_WRITE_DSN = f"{POSTGRES_WRITE_DSN}_test"

RABBIT_USER = getenv("RABBIT_USER", "")  # eg 'guest'
RABBIT_PASSWORD = getenv("RABBIT_PASSWORD", "")
RABBIT_HOST = getenv("RABBIT_HOST", "")
RABBIT_PORT = getenv("RABBIT_PORT", "0", conv=int)
RABBIT_DSN = getenv("RABBIT_DSN", f"amqp://{RABBIT_USER}:{RABBIT_PASSWORD}@{RABBIT_HOST}:{RABBIT_PORT}/")
TO_HERMES_QUEUE = getenv("TO_HERMES_QUEUE", "from_angelia")

URL_PREFIX = getenv("URL_PREFIX", "/v2")

# Metrics
METRICS_SIDECAR_DOMAIN = getenv("METRICS_SIDECAR_DOMAIN", "localhost", required=False)
METRICS_PORT = getenv("METRICS_PORT", "4000", required=False, conv=int)
PERFORMANCE_METRICS = getenv("PERFORMANCE_METRICS", "0", required=True, conv=int)

# QA settings
LOCAL_CHANNELS = getenv("LOCAL_CHANNELS", "False", conv=to_bool)
LOCAL_SECRETS_PATH = getenv("LOCAL_SECRETS_PATH", "tests/helpers/vault/local_channels.json")
VAULT_URL = getenv("VAULT_URL", "https://bink-uksouth-staging-com.vault.azure.net")
CHANNEL_SECRET_NAME = getenv("CHANNEL_SECRET_NAME", "channels")
BLOB_STORAGE_DSN = getenv("BLOB_STORAGE_DSN", required=False)

vault_access_secret = {"access-secret-1": "my_secret_1"}
