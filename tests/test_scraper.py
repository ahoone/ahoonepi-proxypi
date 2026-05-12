import json
import os
import pytest
import random
import requests
from time import sleep

HTTP_PORT_SCRAPER = os.getenv("HTTP_PORT_SCRAPER")
WIREGUARD_NETWORK_PREFIX = os.getenv("WIREGUARD_NETWORK_PREFIX")
WIREGUARD_LIGHTHOUSE_ID = os.getenv("WIREGUARD_LIGHTHOUSE_ID")
ADDRESS = f"{WIREGUARD_NETWORK_PREFIX}.{WIREGUARD_LIGHTHOUSE_ID}:{HTTP_PORT_SCRAPER}"

TIMEOUT_REQUESTS = 20  # in seconds, may take some time as we are waiting for either "complete" or "interactive" status
TIME_BETWEEN_TESTS = 0.5  # in seconds
EXPLICIT_NEW_INSTANCE_ID = "explicit"
EXPLICIT_NEW_INSTANCE_LIFESPAN = 10  # in seconds
EXPLICIT_NEW_INSTANCE_WINDOW_SIZE = [1280, 720]

with open("urls.txt", "r", encoding="utf-8") as f:
    TEST_URL = [line.strip() for line in f]


@pytest.fixture(autouse=True)
def wait_between_tests():
    yield
    sleep(TIME_BETWEEN_TESTS)


def test_scraper_available():
    url = f"http://{ADDRESS}/health"
    response = requests.get(url, timeout=TIMEOUT_REQUESTS)
    assert response.status_code == 200, response.content


def test_default_new_instance():
    url = f"http://{ADDRESS}/new-instance"
    response = requests.post(url, timeout=TIMEOUT_REQUESTS)
    assert response.status_code == 201, response.content


def test_explicit_new_instance():
    url = f"http://{ADDRESS}/new-instance"
    payload = {
        "instance_id": EXPLICIT_NEW_INSTANCE_ID,
        "lifespan_in_seconds": EXPLICIT_NEW_INSTANCE_LIFESPAN,
        "window_size": EXPLICIT_NEW_INSTANCE_WINDOW_SIZE,
    }
    response = requests.post(url, json=payload, timeout=TIMEOUT_REQUESTS)
    assert response.status_code == 201, response.content


def test_get_page_explicit_instance():
    url = f"http://{ADDRESS}/browsers"
    response = requests.get(url, timeout=TIMEOUT_REQUESTS)
    assert response.status_code == 200, response.content
    browsers = json.loads(response.text)
    if EXPLICIT_NEW_INSTANCE_ID in browsers:
        url = f"http://{ADDRESS}/get"
        payload = {
            "instance_id": "default",
            "url": random.choice(TEST_URL),
        }
        response = requests.post(url, json=payload, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 200, response.content


def test_get_page_default_instance():
    url = f"http://{ADDRESS}/get"
    payload = {
        "instance_id": "default",
        "url": random.choice(TEST_URL),
    }
    response = requests.post(url, json=payload, timeout=TIMEOUT_REQUESTS)
    assert response.status_code == 200, response.content


def test_kill_default_instance():
    url = f"http://{ADDRESS}/kill"
    payload = {"instance_id": "default"}
    response = requests.post(url, json=payload, timeout=TIMEOUT_REQUESTS)
    assert response.status_code == 200, response.content


def test_explicit_instance_dead():
    sleep(EXPLICIT_NEW_INSTANCE_LIFESPAN)
    url = f"http://{ADDRESS}/browsers"
    response = requests.get(url, timeout=TIMEOUT_REQUESTS)
    assert response.status_code == 200, response.content
    browsers = json.loads(response.text)
    assert EXPLICIT_NEW_INSTANCE_ID not in browsers
