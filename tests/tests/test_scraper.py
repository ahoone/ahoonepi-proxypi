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
        url = Config.ORIGIN_SCRAPER + "/get_scraper_state"
        response = requests.get(url, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 200, response.content

    def test_default_new_instance(self):
        url = Config.ORIGIN_SCRAPER + "/new-instance"
        response = requests.post(url, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 201, response.content

    def test_explicit_new_instance(self):
        """
        BUG ! This function does not fail despite no explicit instance existing
        ============================= test session starts ==============================
        platform linux -- Python 3.10.20, pytest-9.0.3, pluggy-1.6.0 -- /usr/local/bin/python3.10
        cachedir: .pytest_cache
        rootdir: /app
        plugins: asyncio-1.4.0
        asyncio: mode=strict, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
        collecting ... collected 14 items

        tests/test_scraper.py::TestScraperCore::test_scraper_health PASSED
        tests/test_scraper.py::TestScraperCore::test_default_new_instance PASSED
        tests/test_scraper.py::TestScraperCore::test_explicit_new_instance FAILED
        tests/test_scraper.py::TestScraperCore::test_get_page_explicit_instance PASSED
        tests/test_scraper.py::TestScraperCore::test_get_page_default_instance PASSED
        tests/test_scraper.py::TestScraperCore::test_kill_default_instance PASSED
        tests/test_scraper.py::TestScraperCore::test_explicit_instance_dead PASSED
        tests/test_broker.py::TestBrokerCore::test_health PASSED
        tests/test_broker.py::TestBrokerCore::test_broker_creates_browser PASSED
        tests/test_broker.py::TestBrokerCore::test_scrape_and_collect FAILED
        tests/test_broker.py::TestBrokerCore::test_scrape_multiple_urls PASSED
        tests/test_broker.py::TestBrokerCore::test_clear PASSED
        tests/test_broker.py::TestBrokerCore::test_no_targets PASSED
        tests/test_broker.py::TestBrokerCore::test_no_browsers PASSED

        =================================== FAILURES ===================================
        __________________ TestScraperCore.test_explicit_new_instance __________________

        self = <test_scraper.TestScraperCore object at 0x7fff8c274730>

            def test_explicit_new_instance(self):
                url = Config.ORIGIN_SCRAPER + "/new-instance"
                payload = {
                    "instance_id": EXPLICIT_NEW_INSTANCE_ID,
                    "lifespan_in_seconds": EXPLICIT_NEW_INSTANCE_LIFESPAN,
                    "window_size": EXPLICIT_NEW_INSTANCE_WINDOW_SIZE,
                }
                response = requests.post(url, json=payload, timeout=TIMEOUT_REQUESTS)
        >       assert response.status_code == 201, response.content
        E       AssertionError: b'{"detail":"Already too many opened instances 4"}'
        E       assert 409 == 201
        E        +  where 409 = <Response [409]>.status_code

        tests/test_scraper.py:33: AssertionError

        """
        url = Config.ORIGIN_SCRAPER + "/new-instance"
        payload = {
            "instance_id": EXPLICIT_NEW_INSTANCE_ID,
            "lifespan_in_seconds": EXPLICIT_NEW_INSTANCE_LIFESPAN,
            "window_size": EXPLICIT_NEW_INSTANCE_WINDOW_SIZE,
        }
        response = requests.post(url, json=payload, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 201, response.content

    def test_get_page_explicit_instance(self):
        url = Config.ORIGIN_SCRAPER + "/get_scraper_state"
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
        url = Config.ORIGIN_SCRAPER + "/get_scraper_state"
        response = requests.get(url, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 200, response.content
        browsers = json.loads(response.text)
        assert EXPLICIT_NEW_INSTANCE_ID not in browsers


class TestScraperIntense:
    def create_the_same_browser_instance_twice(self):
        pass


class TestScraperFeatures:
    pass


# should implement a test on playin for lazy loading
