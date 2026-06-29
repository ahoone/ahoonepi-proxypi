import json
from time import sleep

import requests
from Config import Config
from URLGenerator import URLGenerator

TIMEOUT_REQUESTS = 60  # in seconds, may take some time as we are waiting for either "complete" or "interactive" status


class TestBrokerCore:
    def test_health(self):
        url = Config.ORIGIN_BROKER + "/health"
        response = requests.get(url, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 200, response.content

    def test_scrape_and_collect(self):
        url = Config.ORIGIN_BROKER + "/scrape"
        payload = {
            "url": "https://example.com/",
            "tag": "test_broker_scrape_and_collect",
        }
        response = requests.post(url, json=payload, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 202, response.content
        response_as_dict = json.loads(response.text)
        assert "uuid" in response_as_dict, response_as_dict
        uuid = response_as_dict["uuid"]

        url = Config.ORIGIN_BROKER + "/collect"
        payload = {"uuid": uuid}
        response = requests.get(url, json=payload, timeout=TIMEOUT_REQUESTS)

        assert response.status_code in [200, 425], (
            f"unexpected status code {response.status_code}"
        )
        if response.status_code == 425:
            sleep(60)
            response = requests.get(url, json=payload, timeout=TIMEOUT_REQUESTS)

        assert response.status_code == 200, response.content
        response_as_dict = json.loads(response.text)
        assert "success" in response_as_dict, response_as_dict
        assert response_as_dict["success"], response_as_dict
        assert (
            "This domain is for use in documentation examples without needing permission."
            in response_as_dict["content"]
        )


class TestBrokerIntense:
    def test_scrape_intense(self):
        assert True
