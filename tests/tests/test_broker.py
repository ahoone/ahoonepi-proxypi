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
        """
        Gives a target to the broker.
        The broker creates a browser instance.
        The result is collected in the time limit.
        The instance is left alive.
        """
        url = Config.ORIGIN_BROKER + "/scrape"
        payload = {
            "url": "https://example.com/",
            "tag": "test_broker_scrape_and_collect",
            "flag_lazy_loading": False,
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
            sleep(20)
            response = requests.get(url, json=payload, timeout=TIMEOUT_REQUESTS)

        assert response.status_code == 200, response
        response_as_dict = json.loads(response.text)
        assert (
            "This domain is for use in documentation examples without needing permission."
            in response_as_dict["content"]
        )

    def test_clear(self):
        """
        Uses the left browser instance from `test_scrape_and_collect` to:
            - cancel a running request,
            - clear the browser instance.
        Lazy loading triggers a wait period during which we can
        """
        url = Config.ORIGIN_BROKER + "/scrape"
        payload = {}

        url = Config.ORIGIN_BROKER + "/clear"
        payload = {
            "flag_cancel_running_tasks": True,
            "flag_kill_browsers": True,
            "flag_clear_unassigned_targets": True,
        }
        response = requests.post(url, json=payload, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 200, response.content

        # assert


# class TestBrokerIntense:
#     def test_scrape_intense(self):
#         assert True
