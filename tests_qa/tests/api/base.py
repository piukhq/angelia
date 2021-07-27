import json

import requests

from tests_qa import config


class Endpoint:
    BASE_URL = ""

    @staticmethod
    def set_environment(env):
        Endpoint.BASE_URL = getattr(config, env.upper()).base_url

    @staticmethod
    def request_header(token=None, version="1.2"):

        if version:
            accept = "application/json;v={}".format(version)
        else:
            accept = "application/json"

        headers = {
            "Accept": accept,
            "Content-Type": "application/json",
        }

        if token:
            if "bearer" in token:
                headers["Authorization"] = token
            else:
                headers["Authorization"] = "token " + token

        return headers

    @staticmethod
    def call(url, headers, method="GET", body=None):
        return requests.request(method, url, headers=headers, data=json.dumps(body))
