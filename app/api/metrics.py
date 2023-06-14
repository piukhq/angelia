from contextlib import suppress
from typing import TYPE_CHECKING

from prometheus_client import Counter

if TYPE_CHECKING:
    from falcon import Request

# Define metrics to capture here
labels = ["endpoint", "method", "channel", "response_status"]

# Encryption label
encrypt_labels = ["endpoint", "channel", "encryption"]

loyalty_plans_counter = Counter("loyalty_plans_requests", "Total loyal plan requests.", labels)
loyalty_card_counter = Counter("loyalty_cards_requests", "Total loyal card requests.", labels)
payment_account_counter = Counter("payment_account_requests", "Total payment account requests.", labels)
users_counter = Counter("user_requests", "Total user requests.", labels)
wallet_counter = Counter("wallet_requests", "Total wallet requests.", labels)
encrypt_counter = Counter("encryption_requests", "Encryption requests", encrypt_labels)


class Metric:
    def __init__(  # noqa: PLR0913
        self,
        request: "Request | None" = None,
        method: str | None = None,
        status: int | type[Exception] | None = None,
        path: str | None = None,
        resource_id: int | None = None,
        resource: object | None = None,
    ) -> None:
        self.request = request
        self.status = status

        self.path = request.path if request else path
        self.method = request.method if request else method
        self.resource_id = resource_id
        self.resource = resource
        self.endpoint = None

        # Define which metric to use for path
        self.route = {
            "email_update": users_counter,
            "me": users_counter,
            "loyalty_plans": loyalty_plans_counter,
            "loyalty_plans_overview": loyalty_plans_counter,
            "loyalty_cards": loyalty_card_counter,
            "payment_accounts": payment_account_counter,
            "token": users_counter,
            "wallet": wallet_counter,
            "wallet_overview": wallet_counter,
        }

    def check_channel(self) -> str:
        channel = ""
        with suppress(AttributeError):
            channel = self.request.context.auth_instance.auth_data.get("channel", "")  # type: ignore [union-attr]

        return channel

    def replace_resource_id(self) -> str:
        if self.resource:
            return self.path.replace(str(self.resource_id), f"{{{self.resource}}}")

        return self.path

    def route_metric(self) -> None:
        with suppress(IndexError):
            if self.route.get(self.path.split("/")[2], None):
                self.route[self.path.split("/")[2]].labels(
                    endpoint=self.replace_resource_id(),
                    method=self.method,
                    channel=self.check_channel() if self.request else "",
                    response_status=self.status,
                ).inc()
