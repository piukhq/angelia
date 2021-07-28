# Created by rupalpatel at 16/07/2021
@paymentcard_account
Feature: As a Bink User
  I want to be able to add my Payment Account to my bink account
  So that I can start to earn rewards when I use my payment card


  @enrol_new_paymentcard
  Scenario Outline: Enrol new payment card and link to harvey_nichols

    Given I am a Bink user
    When I perform POST request to add a new "<payment_card_provider>" payment card to wallet
    And I perform the GET request to verify the new payment card "<payment_card_provider>" has been added successfully to the wallet

    Examples:
      | payment_card_provider |
      | master                |


#  Scenario Outline : Add new card to single wallet as a new customer
#
    Given I am a Bink user
    And I don't have any payment cards in my wallet
    When I perform a POST request to add a new "<payment_card_provider>" payment card to my wallet
    And I perform the GET request to verify the new payment card "<payment_card_provider>" has been added successfully to the wallet
    Then I see a new payment account created in the body response
    And I see a "<status_code_returned>" status code
    And I see the "<card_ID>" in the response body
    And I see "<card_auth_status_returned>" status
    And I see the expiry month "<expiry_month>"
    And I see the expiry_year "<expiry_year>"
    And I see the card name "<card_name>"
    And I see the card nickname "<card_nickname>"
    And I see the issuer "<bank>"


    Examples:
      | payment_card_provider | status_code_returned | card_ID | card_auth_status_returned | loyalty_ID | expiry_month | expiry_year | card_name | card_nickname | bank |
      |                       | 201                  |         |                           |            |              |             |           |               |      |


  Scenario Outline : Add new card to single wallet as an existing customer

    Given I am a Bink user
    And I don't have any payment cards in my wallet
    When I perform a POST request to add "<payment_card_provider>" payment card
    Then I see a new payment account created in the body response
    And I see a "<status_code_returned>" status code
    And I see the "<card_ID>" in the response body
    And I see "<card_auth_status_returned>" status
    And I see the expiry month "<expiry_month>"
    And I see the expiry_year "<expiry_year>"
    And I see the card name "<card_name>"
    And I see the card nickname "<card_nickname>"
    And I see the issuer "<bank>"


    Examples:
      | payment_card_provider | status_code_returned | card_ID | card_auth_status_returned | loyalty_ID | expiry_month | expiry_year | card_name | card_nickname | bank |
      |                       | 200                  |         |                           |            |              |             |           |               |      |


  Scenario Outline : Add new card to single wallet without entering a card name

    Given I am a Bink user
    And I don't have any payment cards in my wallet
    When I perform a POST request to add "<payment_card_provider>" payment card without the card name field
    Then I see a "<status_code_returned>" status code
    And I see "<error_message>" in the display message field in the response
    And I see "<error_slug>" in the error field in the response

    Examples:
      | payment_card_provider | status_code_returned | error_message | error_slug |
      |                       | 400                  |               |            |

  Scenario Outline : Add new card to single wallet without entering an expiry date

    Given I am a Bink user
    And I don't have any payment cards in my wallet
    When I perform a POST request to add "<payment_card_provider>" payment card without the card expiry field
    Then I see a "<status_code_returned>" status code
    And I see "<error_message>" in the display message field in the response
    And I see "<error_slug>" in the error field in the response

    Examples:
      | payment_card_provider | status_code_returned | error_message | error_slug |
      |                       | 400                  |               |            |


  Scenario Outline : Add new card to single wallet as a new customer with an invalid Token

    Given I am a Bink user
    And I don't have any payment cards in my wallet
    And I have an invalid "<authorisation_token>"
    When I perform a POST request to add "<payment_card_provider>" payment card
    Then I see a "<status_code_returned>" status code
    And I see "<error_message>" in the error message field in the response
    And I see "<error_slug>" in the error slug field in the response


    Examples:
      | authorisation_token | payment_card_provider | status_code_returned | error_message | error_slug |
      |                     | 401                   |                      |               |            |


  Scenario Outline : Add new card to single wallet as a new customer without the expiry month field

    Given I am a Bink user
    And I don't have any payment cards in my wallet
    When I perform a POST request to add "<payment_card_provider>" payment card without the expiry month field
    Then I see a "<status_code_returned>" status code
    And I see "<error_message>" in the error message field in the response
    And I see "<error_slug>" in the error slug field in the response
    And I see "<missing_fields>" in the fields section in the response


    Examples:
      | payment_card_provider | status_code_returned | error_message | error_slug |
      |                       | 422                  |               |            |


