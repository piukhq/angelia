import atexit
import logging
import socket
from collections.abc import Callable
from time import sleep
from typing import TYPE_CHECKING

from kombu import Connection, Consumer, Exchange, Producer, Queue
from loguru import logger

from app.report import send_logger

if TYPE_CHECKING:
    from loguru import Logger


class BaseMessaging:
    def __init__(self, dsn: str) -> None:
        self._conn: Connection | None = None
        self.producer: dict[str, Producer] = {}
        atexit.register(self.close)
        self.dsn = dsn
        self.connect()

        # Check connection on startup
        err_msg = "Failed to connect to messaging service. Please check the configuration."
        if self._conn:
            try:
                self._conn.connect()
                self._conn.release()
            except ConnectionRefusedError:
                send_logger.exception(err_msg)
                raise
        else:
            raise ConnectionError(err_msg)

    @property
    def conn(self) -> Connection:
        if not self._conn:
            raise ValueError("conn is unexpectedly None")

        return self._conn

    def connect(self) -> None:
        if self._conn:
            self.close()
        self._conn = Connection(self.dsn)

    def close(self) -> None:
        if self._conn:
            self._conn.release()
            self._conn = None


class SendingService(BaseMessaging):
    def __init__(self, dsn: str, log_to: "Logger | None" = None) -> None:
        super().__init__(dsn)
        self._conn = None
        self.producer = {}
        self.queue: dict[str, Queue] = {}
        self.exchange: dict[str, Exchange] = {}
        self.connect()
        self.consumer = None
        if log_to is None:
            self.logger = logger.bind(logger_type="Send_Messaging")
        else:
            self.logger = log_to

    def _pub(self, queue_name: str, kwargs: dict) -> None:
        producer = self.producer.get(queue_name, None)
        if producer is None:
            exchange = self.exchange.get(queue_name, None)
            if exchange is None:
                self.exchange[queue_name] = Exchange(f"{queue_name}_exchange", type="direct", durable=True)
            self.queue[queue_name] = Queue(queue_name, exchange=self.exchange[queue_name], routing_key=queue_name)
            self.queue[queue_name].maybe_bind(self.conn)
            self.queue[queue_name].declare()

            self.producer[queue_name] = producer = Producer(
                exchange=self.exchange[queue_name],
                channel=self.conn.channel(),
                routing_key=queue_name,
                serializer="json",
            )
        producer.publish(**kwargs)

    def send(self, message: dict | None, headers: dict, queue_name: str) -> None:
        headers["destination-type"] = "ANYCAST"
        message = {"body": message, "headers": headers}

        try:
            self._pub(queue_name, message)
        except Exception as e:
            self.logger.warning(f"Exception on connecting to Message Broker - time out? {e} retry send")
            self.close()
            self.connect()
            self._pub(queue_name, message)

    def close(self) -> None:
        if self._conn:
            self._conn.release()
            self._conn = None

        self.producer = {}
        self.queue = {}
        self.exchange = {}


class ReceivingService(BaseMessaging):
    def __init__(  # noqa: PLR0913
        self,
        dsn: str,
        queue_name: str,
        callbacks: list,
        on_time_out: Callable | None = None,
        heartbeat: int = 10,
        timeout: int = 2,
        continue_exceptions: type[Exception] | None = None,
        log_to: "Logger | None" = None,
    ) -> None:
        super().__init__(dsn)

        self.queue_name = queue_name
        self.connect()
        self.exchange = None
        self.exchange = Exchange(f"{self.queue_name}_exchange", type="direct", durable=True)
        self.queue = Queue(self.queue_name, exchange=self.exchange, routing_key=queue_name)
        self.consumer: Consumer | None = None
        self.heartbeat = heartbeat
        self.timeout = timeout
        self.callbacks = callbacks
        self.on_time_out = on_time_out
        if log_to is None:
            self.logger = logger.bind(logger_type="Receive_Messaging")
        else:
            self.logger = log_to

        logging.getLogger("amqp").setLevel(logging.WARNING)
        if continue_exceptions is not None:
            self.continue_exceptions = continue_exceptions
        else:
            self.continue_exceptions = ConnectionError
        self.dispatch_loop()

    def setup_consumer(self) -> None:
        if not self._conn:
            self.connect()
        self.consumer = Consumer(
            self._conn,
            queues=self.queue,
            callbacks=self.callbacks,
            accept=["application/json"],
        )
        self.consumer.consume()

    def dispatch_loop(self) -> None:
        while True:
            if not self.consumer or not self._conn:
                self.setup_consumer()
            try:
                while True:
                    try:
                        self.conn.drain_events(timeout=self.timeout)
                    except socket.timeout:
                        self.conn.heartbeat_check()
                        if self.on_time_out is not None:
                            self.on_time_out()
            except self.continue_exceptions as e:
                self.logger.debug(f"Message Queue Reading Loop Error: {e}")
                sleep(1)
                self.close()
