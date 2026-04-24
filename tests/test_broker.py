import os
import pytest
import random
import requests
from time import sleep

HTTP_PORT_BROKER = os.getenv("HTTP_PORT_BROKER")
WIREGUARD_NETWORK_PREFIX = os.getenv("WIREGUARD_NETWORK_PREFIX")
WIREGUARD_LIGHTHOUSE_ID = os.getenv("WIREGUARD_LIGHTHOUSE_ID")
ADDRESS = f"{WIREGUARD_NETWORK_PREFIX}.{WIREGUARD_LIGHTHOUSE_ID}:{HTTP_PORT_BROKER}"

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

def test_broker_receive_scrape_request():
    url = f"http://{ADDRESS}/scrape"
    payload = {
        "url": "http://example.com",
        "antwortzeit": "2019-08-24T14:15:22Z",
        "tag": "string"
    }
    response = requests.post(url, json=payload, timeout=TIMEOUT_REQUESTS)
    assert response.status_code == 202, response.content


