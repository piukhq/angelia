from prometheus_client import Counter

# Define metrics to capture here
labels = ["endpoint", "method", "channel", "response_status"]

loyalty_plans_counter = Counter("loyalty_plans_requests", "Total loyal plan requests.", labels)
loyalty_card_counter = Counter("loyalty_cards_requests", "Total loyal card requests.", labels)
payment_account_counter = Counter("payment_account_requests", "Total payment account requests.", labels)
users_counter = Counter("user_requests", "Total user requests.", ["endpoint", "method", "channel", "response_status"])
wallet_counter = Counter("wallet_requests", "Total wallet requests.", labels)


class Metric:
    def __init__(self, request=None, method=None, status=None, path=None):
        self.request = request
        self.status = status

        self.path = request.path if request else path
        self.method = request.method if request else method

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

    def check_channel(self):
        channel = ""
        try:
            channel = self.request.context.auth_instance.auth_data.get("channel", "")
        except AttributeError:
            pass

        return channel

    def route_metric(self):
        try:
            if self.route.get(self.path.split("/")[2], None):
                self.route[self.path.split("/")[2]].labels(
                    endpoint=self.path,
                    method=self.method,
                    channel=self.check_channel() if self.request else "",
                    response_status=self.status,
                ).inc()
        except IndexError:
            pass
