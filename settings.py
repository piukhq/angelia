import logging
from environment import read_env, getenv, to_bool


def to_log_level(s: str) -> int:
    VALID_LOG_LEVELS = ["NOTSET", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    s = s.upper()
    if s not in VALID_LOG_LEVELS:
        raise ValueError(
            f"'{s}' is not a valid log level. Must be one of {', '.join(VALID_LOG_LEVELS)}"
        )
    return getattr(logging, s.upper())


def postgres_dsn(host, port):
    return "".join(
        [
            "postgresql+psycopg2://",
            POSTGRES_USER,
            f":{POSTGRES_PASS}" if POSTGRES_PASS else "",
            "@",
            host,
            ":",
            str(port),
            "/",
            POSTGRES_DB,
        ]
    )


read_env()

# Logging configuration.
LOG_LEVEL = getenv("LOG_LEVEL", default="DEBUG", conv=to_log_level)
LOG_FORMAT = getenv(
    "LOG_FORMAT", default="%(asctime)s | %(name)18s | %(levelname)8s | %(funcName)s:%(lineno)s - %(message)s"
)

JSON_LOGGING = getenv('JSON_LOGGING', "True", conv=to_bool)

POSTGRES_READ_HOST = getenv("POSTGRES_READ_HOST", "127.0.0.1")
POSTGRES_READ_PORT = getenv("POSTGRES_READ_PORT", "5432")
POSTGRES_WRITE_HOST = getenv("POSTGRES_WRITE_HOST", "127.0.0.1")
POSTGRES_WRITE_PORT = getenv("POSTGRES_WRITE_PORT", "5432")
POSTGRES_USER = getenv("POSTGRES_USER", "postgres")
POSTGRES_PASS = getenv("POSTGRES_PASS", "")
POSTGRES_DB = getenv("POSTGRES_DB", "hermes")

POSTGRES_READ_DSN = postgres_dsn(POSTGRES_READ_HOST, POSTGRES_READ_PORT)
POSTGRES_WRITE_DSN = postgres_dsn(POSTGRES_WRITE_HOST, POSTGRES_WRITE_PORT)

RABBIT_USER = getenv("RABBIT_USER", '')  # eg 'guest'
RABBIT_PASSWORD = getenv("RABBIT_PASSWORD", '')
RABBIT_HOST = getenv("RABBIT_HOST", '')
RABBIT_PORT = getenv("RABBIT_PORT", '0', conv=int)
TO_HERMES_QUEUE = getenv("TO_HERMES_QUEUE", 'from_api2')  # eg 'from_api2'


URL_PREFIX = getenv('URL_PREFIX', '/api2')

# Metrics
METRICS_SIDECAR_DOMAIN = getenv('METRICS_SIDECAR_DOMAIN', 'localhost', required=False)
METRICS_PORT = getenv('METRICS_PORT', '4000', required=False, conv=int)
PERFORMANCE_METRICS = getenv('PERFORMANCE_METRICS', "0", required=True, conv=int)
