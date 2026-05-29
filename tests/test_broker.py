import json
import os
import pytest
import random
import requests
from time import sleep

HTTP_PORT_BROKER = os.getenv("HTTP_PORT_BROKER")
WIREGUARD_NETWORK_PREFIX = os.getenv("WIREGUARD_NETWORK_PREFIX")
ADDRESS = f"{WIREGUARD_NETWORK_PREFIX}.1:{HTTP_PORT_BROKER}"

TIMEOUT_REQUESTS = 10  # in seconds, may take some time as we are waiting for either "complete" or "interactive" status
TIME_BETWEEN_TESTS = 0.5  # in seconds


with open("urls.txt", "r", encoding="utf-8") as f:
    TEST_URL = [line.strip() for line in f]


@pytest.fixture(autouse=True)
def wait_between_tests():
    yield
    sleep(TIME_BETWEEN_TESTS)


def test_broker_available():
    url = f"http://{ADDRESS}/health"
    response = requests.get(url, timeout=TIMEOUT_REQUESTS)
    assert response.status_code == 200, response.content


def test_broker_scrape_and_collect():
    url = f"http://{ADDRESS}/scrape"
    payload = {
        "url": "http://example.com",
        "tag": "test_sending_scraping_request",
    }
    response = requests.post(url, json=payload, timeout=TIMEOUT_REQUESTS)
    assert response.status_code == 202, response.content
    response_as_dict = json.loads(response.text)
    assert "uuid" in response_as_dict, response_as_dict
    uuid = response_as_dict["uuid"]

    url = f"http://{ADDRESS}/collect"
    payload = {"uuid": uuid}
    response = requests.get(url, json=payload, timeout=TIMEOUT_REQUESTS)
    assert response.status_code == 425, response.content

    sleep(2)

    response = requests.get(url, json=payload, timeout=TIMEOUT_REQUESTS)
    assert response.status_code == 200, response.content
    response_as_dict = json.loads(response.text)
    assert "success" in response_as_dict, response_as_dict
    assert response_as_dict["success"] == True, response_as_dict
    assert (
        "This domain is for use in documentation examples without needing permission."
        in response_as_dict["content"]
    )
