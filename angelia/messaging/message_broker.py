from enum import Enum

from message_lib.producer import MessageProducer, QueueParams

from angelia.report import send_logger
from angelia.settings import settings


class ProducerQueues(Enum):
    HERMES = settings.TO_HERMES_QUEUE


sending_service = MessageProducer(
    rabbitmq_dsn=settings.RABBIT_DSN,
    queues_name_and_params={
        ProducerQueues.HERMES.name: QueueParams(
            exchange_name=f"{ProducerQueues.HERMES.value}-exchange",
            queue_name=ProducerQueues.HERMES.value,
            routing_key=settings.TO_HERMES_QUEUE_ROUTING_KEY,
        )
    },
    custom_log=send_logger,
)
sending_service.queues[ProducerQueues.HERMES.name].retry_policy = {
    "interval_start": 0,  # First retry immediately,
    "interval_step": settings.PUBLISH_RETRY_BACKOFF_FACTOR,  # then increase by n seconds for every retry.
    "interval_max": 1,  # but don't exceed 1s between retries.
    "max_retries": settings.PUBLISH_MAX_RETRIES,  # give up after n tries.
}
