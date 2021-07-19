# Created by rupalpatel at 16/07/2021
@paymentcard_account
Feature: Ensure a customer can add their payment card

  @enrol_new_paymentcard
  Scenario Outline: Enrol new paymentcard and link to harvey_nichols

    Given I am a Bink user
#    When I perform POST request to enrol new "<payment_card_provider>" payment card to wallet
#    And I perform the GET request to verify the new payment card "<payment_card_provider>" has been added successfully to the wallet

    Examples:
      | payment_card_provider |
      | master                |