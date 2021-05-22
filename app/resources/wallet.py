import falcon


class Wallet:
    def on_get(self, req: falcon.Request, resp: falcon.Response) -> None:
        reply = [
              {
                "joins": [
                  {
                    "id": 51,
                    "plan_id": 21,
                    "status": "pending"
                  },
                  {
                    "id": 89,
                    "plan_id": 43,
                    "status": "failed",
                    "errors": [
                      {
                        "error_code": "X202",
                        "error_message": "An account with those details already exists"
                      }
                    ]
                  }
                ]
              },
              {
                "adds": [
                  {
                    "id": 12,
                    "plan_id": 24,
                    "status": "failed",
                    "errors": [
                      {
                        "error_code": "X105",
                        "error_message": "Card is not registered"
                      }
                    ],
                    "capabilities": [
                      "register"
                    ]
                  }
                ]
              },
              {
                "loyalty_cards": [
                  {
                    "id": 81,
                    "loyalty_plan": 201,
                    "authorisation": {
                      "id": 55,
                      "plan_id": 26,
                      "status": "complete"
                    },
                    "balances": [
                      {
                        "value": 100,
                        "currency": "GBP",
                        "prefix": "£",
                        "updated_at": 1515697663
                      }
                    ],
                    "card": {
                      "barcode": 633174911234568000,
                      "barcode_type": 0,
                      "loyalty_id": 633174911234568000,
                      "colour": "#FFFFFF"
                    }
                  },
                  {
                    "id": 85,
                    "loyalty_plan": 222,
                    "authorisation": {
                      "id": 55,
                      "plan_id": 26,
                      "status": "failed",
                      "errors": [
                        {
                          "error_code": "X303",
                          "error_message": "Authorisation data rejected by merchant"
                        }
                      ],
                      "date_status": 1517549941
                    },
                    "capabilities": [
                      "authorise"
                    ]
                  },
                  {
                    "id": 97,
                    "loyalty_plan": 766,
                    "join": {
                      "id": 44,
                      "status": "complete",
                      "date_status": 1517549941
                    },
                    "capabilities": [
                      "authorise"
                    ]
                  }
                ]
              },
              {
                "payment_accounts": [
                  {
                    "id": 432,
                    "status": "authorised",
                    "month": 12,
                    "year": 24,
                    "name_on_card": "Jeff Jeffries",
                    "consents": [
                      {
                        "type": 0,
                        "timestamp": 1517549941
                      }
                    ]
                  }
                ]
              },
              {
                "pll_links": [
                  {
                    "payment_account": {
                      "payment_account_id": 555,
                      "payment_scheme": "VISA"
                    },
                    "loyalty_card": {
                      "loyalty_card_id": 543,
                      "loyalty_scheme": "iceland"
                    },
                    "status": "active",
                    "id": 68686
                  }
                ]
              }
            ]

        resp.media = reply


def wallet_urls(app, prefix):
    app.add_route(f"{prefix}/wallets", Wallet())
