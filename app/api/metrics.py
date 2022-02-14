from prometheus_client import Counter

# Define metrics to capture here
loyalty_plans_counter = Counter(
    "loyalty_plans_requests", "Total loyal plan requests.", ["endpoint", "channel", "response_status"]
)

loyalty_card_counter = Counter(
    "loyalty_cards_requests", "Total loyal card requests.", ["endpoint", "channel", "response_status"]
)

users_counter = Counter("user_requests", "Total user requests.", ["endpoint", "channel", "response_status"])


class Metric:
    def __init__(self, request=None, status=None, path=None):
        self.request = request
        self.status = status

        self.path = request.path if request else path

        # Define which metric to use for path
        self.route = {
            "loyalty_plans": loyalty_plans_counter,
            "loyalty_plans_overview": loyalty_plans_counter,
            "loyalty_cards": loyalty_card_counter,
            "token": users_counter,
            "email_update": users_counter,
            "me": users_counter,
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
                    channel=self.check_channel() if self.request else "",
                    response_status=self.status,
                ).inc()
        except IndexError:
            pass
