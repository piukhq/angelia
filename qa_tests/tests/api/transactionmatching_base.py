import json
import requests
import config


class TransactionMatching_Endpoint:
    TRANSACTION_MATCHING_BASE_URL = ""
    TRANSACTION_MATCHING_BASE_URL_ZEPHYRUS = ""

    @staticmethod
    def set_environment(env):
        TransactionMatching_Endpoint.TRANSACTION_MATCHING_BASE_URL = \
            getattr(config, env.upper()).transaction_matching_base_url
        TransactionMatching_Endpoint.TRANSACTION_MATCHING_BASE_URL_ZEPHYRUS = \
            getattr(config, env.upper()).transaction_matching_base_url_zephyrus

    @staticmethod
    def request_header_mastercard():
        header = {
            "Content-Type": "application/json",
            "Authorization": "token F616CE5C88744DD52DB628FAD8B3D"
        }
        return header

    @staticmethod
    def request_register_amex():
        header = {
            "Content-Type": "application/json",
            "Cookie": "sessionid=ir8ojeq2hssh0cjoihofyitctpt46dk7"
        }
        return header

    @staticmethod
    def request_header_amex(auth_token):
        header = {
            "Content-Type": "application/json",
            "Cookie": "sessionid=ir8ojeq2hssh0cjoihofyitctpt46dk7",
            "Authorization": "token " + auth_token
        }
        return header

    @staticmethod
    def call(url, headers, method="GET", body=None):
        return requests.request(method, url, headers=headers, data=json.dumps(body))
