import atexit
import logging
import socket
from time import sleep

from kombu import Connection, Exchange, Producer, Queue, Consumer


class BaseMessaging:
    def __init__(self, user: str, password: str, host: str, port: int):
        self.conn = None
        self.producer = {}
        atexit.register(self.close)
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.connect()

    def connect(self):
        if self.conn:
            self.close()
        self.conn = Connection(
            f"amqp://{self.password}:{self.user}@{self.host}:{self.port}/"
        )

    def close(self):
        if self.conn:
            self.conn.release()
            self.conn = None


class SendingService(BaseMessaging):
    def __init__(
        self, user: str, password: str, host: str, port: int, log_to: logging = None
    ):
        super().__init__(user, password, host, port)
        self.conn = None
        self.producer = {}
        self.queue = {}
        self.exchange = {}
        self.connect()
        self.consumer = None
        if log_to is None:
            self.logger = logging.getLogger("Send_Messaging")
        else:
            self.logger = log_to

    def _pub(self, queue_name: str, kwargs: dict):
        producer = self.producer.get(queue_name, None)
        if producer is None:
            exchange = self.exchange.get(queue_name, None)
            if exchange is None:
                self.exchange[queue_name] = Exchange(
                    f"{queue_name}_exchange", type="direct", durable=True
                )
            self.queue[queue_name] = Queue(
                queue_name, exchange=self.exchange[queue_name], routing_key=queue_name
            )
            self.queue[queue_name].maybe_bind(self.conn)
            self.queue[queue_name].declare()

            self.producer[queue_name] = producer = Producer(
                exchange=self.exchange[queue_name],
                channel=self.conn.channel(),
                routing_key=queue_name,
                serializer="json",
            )
        producer.publish(**kwargs)

    def send(self, message: dict, headers: dict, queue_name: str):
        headers["destination-type"] = "ANYCAST"
        message = {"body": message, "headers": headers}

        try:
            self._pub(queue_name, message)
        except Exception as e:
            self.logger.warning(
                f"Exception on connecting to Message Broker - time out? {e} retry send"
            )
            self.close()
            self.connect()
            self._pub(queue_name, message)

    def close(self):
        if self.conn:
            self.conn.release()
            self.conn = None

        self.producer = {}
        self.queue = {}
        self.exchange = {}


class ReceivingService(BaseMessaging):
    def __init__(
        self,
        user: str,
        password: str,
        queue_name: str,
        host: str,
        port: int,
        callbacks: list,
        on_time_out=None,
        heartbeat: int = 10,
        timeout: int = 2,
        continue_exceptions=None,
        log_to: logging = None,
    ):
        super().__init__(user, password, host, port)

        self.queue_name = queue_name
        self.connect()
        self.exchange = None
        self.exchange = Exchange(
            f"{self.queue_name}_exchange", type="direct", durable=True
        )
        self.queue = Queue(
            self.queue_name, exchange=self.exchange, routing_key=queue_name
        )
        self.consumer = None
        self.heartbeat = heartbeat
        self.timeout = timeout
        self.callbacks = callbacks
        self.on_time_out = on_time_out
        if log_to is None:
            self.logger = logging.getLogger("Receive_Messaging")
        else:
            self.logger = log_to
        logging.getLogger("amqp").setLevel(logging.WARNING)
        if continue_exceptions is not None:
            self.continue_exceptions = continue_exceptions
        else:
            self.continue_exceptions = ConnectionError
        self.dispatch_loop()

    def setup_consumer(self):
        if not self.conn:
            self.connect()
        self.consumer = Consumer(
            self.conn,
            queues=self.queue,
            callbacks=self.callbacks,
            accept=["application/json"],
        )
        self.consumer.consume()

    def dispatch_loop(self):
        while True:
            if not self.consumer or not self.conn:
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
