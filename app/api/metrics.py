from prometheus_client import Counter

# Define metrics to capture here
loyalty_plan_get_counter = Counter(
    "loyalty_plan_get_requests", "Total loyal plan get requests.", ["endpoint", "channel", "response_status"]
)

loyalty_card_counter = Counter(
    "loyalty_card_requests", "Total loyal card requests.", ["endpoint", "channel", "response_status"]
)
