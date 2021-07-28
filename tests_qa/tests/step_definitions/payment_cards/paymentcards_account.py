from pytest_bdd import when, scenarios

scenarios("payment_cards/")

"""Step definitions - Add Payment Card """


@when('I perform POST request to add a new "<payment_card_provider>" payment card to wallet')
def step_impl():
    pass
