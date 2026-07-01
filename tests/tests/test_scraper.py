import json
from time import sleep

import requests
from Config import Config
from URLGenerator import URLGenerator

TIMEOUT_REQUESTS = 60  # in seconds, may take some time as we are waiting for either "complete" or "interactive" status
EXPLICIT_NEW_INSTANCE_ID = "explicit"
EXPLICIT_NEW_INSTANCE_LIFESPAN = 10  # in seconds
EXPLICIT_NEW_INSTANCE_WINDOW_SIZE = [1280, 720]


class TestScraperCore:
    def test_scraper_health(self):
        url = Config.ORIGIN_SCRAPER + "/health"
        response = requests.get(url, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 200, response.content

    def test_default_new_instance(self):
        url = Config.ORIGIN_SCRAPER + "/new-instance"
        response = requests.post(url, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 201, response.content

    def test_explicit_new_instance(self):
        url = Config.ORIGIN_SCRAPER + "/new-instance"
        payload = {
            "instance_id": EXPLICIT_NEW_INSTANCE_ID,
            "lifespan_in_seconds": EXPLICIT_NEW_INSTANCE_LIFESPAN,
            "window_size": EXPLICIT_NEW_INSTANCE_WINDOW_SIZE,
        }
        response = requests.post(url, json=payload, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 201, response.content

    def test_get_page_explicit_instance(self):
        url = Config.ORIGIN_SCRAPER + "/browsers"
        response = requests.get(url, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 200, response.content
        browsers = json.loads(response.text)
        if EXPLICIT_NEW_INSTANCE_ID in browsers:
            url = Config.ORIGIN_SCRAPER + "/get"
            payload = {
                "instance_id": "default",
                "url": URLGenerator.next(),
                "flag_lazy_loading": False,
            }
            response = requests.post(url, json=payload, timeout=TIMEOUT_REQUESTS)
            assert response.status_code == 200, response.content

    def test_get_page_default_instance(self):
        url = Config.ORIGIN_SCRAPER + "/get"
        payload = {
            "instance_id": "default",
            "url": URLGenerator.next(),
            "flag_lazy_loading": False,
        }
        response = requests.post(url, json=payload, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 200, response.content

    def test_kill_default_instance(self):
        url = Config.ORIGIN_SCRAPER + "/kill"
        payload = {"instance_id": "default"}
        response = requests.post(url, json=payload, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 200, response.content

    def test_explicit_instance_dead(self):
        sleep(EXPLICIT_NEW_INSTANCE_LIFESPAN)
        url = Config.ORIGIN_SCRAPER + "/browsers"
        response = requests.get(url, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 200, response.content
        browsers = json.loads(response.text)
        assert EXPLICIT_NEW_INSTANCE_ID not in browsers


class TestScraperFeatures:
    pass


# should implement a test on playin for lazy loading
