from time import sleep
import math

import pytest
import requests
from contract.schemas.architecture import ScraperModel
from contract.schemas.new_instance import NewInstanceRequest
from contract.schemas.get import ScraperGetRequest, ScraperGetResponse
from contract.Config import Config as ContractConfig
from Config import Config
from URLGenerator import URLGenerator


BASE = Config.ORIGIN_SCRAPER
TIMEOUT_GET = 60 # in seconds (long, as we are waiting for either "complete" or "interactive" status)
TIMEOUT_REQUESTS = 4  # seconds (small genetic)
TIMEOUT_TERMINATE = 8  # seconds (medium)

class TestScraperPrep:
    def test_endpoint_terminate(self):
        """
        Test the endpoint and clear the browsers for the following tests.
        """
        url = BASE + "/terminate"
        response = requests.post(url, timeout=TIMEOUT_TERMINATE)
        assert response.status_code == 204

    def test_no_instance_running(self):
        url = BASE + "/get_scraper_state"
        response = requests.get(url, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 200
        scraper_model = ScraperModel.model_validate(response.json())
        assert not scraper_model.browsers

    def test_health(self):
        url = BASE + "/get_scraper_state"
        response = requests.get(url, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 200
        scraper_model = ScraperModel.model_validate(response.json())
        assert not scraper_model.is_running_as_root
        assert scraper_model.can_create_browser
        assert scraper_model.ram_specs
        assert scraper_model.ram_usage

class TestScraperCore:

    BROWSER_EXPLICIT_ID = "explicit"
    BROWSER_EXPLICIT_LIFESPAN = 10
    BROWSER_EXPLICIT_WINDOW = (1024, 768)

    def test_default_new_instance(self):
        url = BASE + "/new-instance"
        response = requests.post(url, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 201, response.content

    def test_default_instance(self):
        url = BASE + "/get_scraper_state"
        response = requests.get(url, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 200, response.content
        scraper_model = ScraperModel.model_validate(response.json())
        assert ContractConfig.BROWSER_DEFAULT_ID in scraper_model.browsers
        browser_model = scraper_model.browsers[ContractConfig.BROWSER_DEFAULT_ID]
        assert browser_model.window_size == ContractConfig.BROWSER_DEFAULT_WINDOW
        assert math.isclose(browser_model.remaining_lifespan.total_seconds(), ContractConfig.BROWSER_DEFAULT_LIFESPAN, rel_tol=.05)
        assert browser_model.status == "idle"
        assert not browser_model.browsing_history

    def test_just_one_instance(self):
        url = BASE + "/get_scraper_state"
        response = requests.get(url, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 200, response.content
        scraper_model = ScraperModel.model_validate(response.json())
        assert len(scraper_model.browsers) == 1

    def test_explicit_new_instance(self):
        url = BASE + "/new-instance"
        payload = NewInstanceRequest(
            instance_id=self.BROWSER_EXPLICIT_ID,
            lifespan_in_seconds=self.BROWSER_EXPLICIT_LIFESPAN,
            window_size=self.BROWSER_EXPLICIT_WINDOW,
        )
        response = requests.post(url, json=payload.model_dump(), timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 201, response.content

    @pytest.fixture(scope="class")
    def test_explicit_instance(self):
        url = BASE + "/get_scraper_state"
        response = requests.get(url, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 200, response.content
        scraper_model = ScraperModel.model_validate(response.json())
        assert self.BROWSER_EXPLICIT_ID in scraper_model.browsers
        browser_model = scraper_model.browsers[self.BROWSER_EXPLICIT_ID]
        assert browser_model.window_size == self.BROWSER_EXPLICIT_WINDOW
        assert math.isclose(browser_model.remaining_lifespan.total_seconds(), self.BROWSER_EXPLICIT_LIFESPAN, rel_tol=.05)
        assert browser_model.status == "idle"
        assert not browser_model.browsing_history

    def test_just_two_instances(self):
        url = BASE + "/get_scraper_state"
        response = requests.get(url, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 200, response.content
        scraper_model = ScraperModel.model_validate(response.json())
        assert len(scraper_model.browsers) == 2

    def test_get_page_explicit_instance(self):
        url = BASE + "/get"
        payload = ScraperGetRequest(
            instance_id=self.BROWSER_EXPLICIT_ID,
            url=URLGenerator.next(),
            flag_lazy_loading=False,
        )
        response = requests.post(url, json=payload.model_dump(mode="json"), timeout=TIMEOUT_GET)
        assert response.status_code == 200, response.content
        scraper_get_response = ScraperGetResponse.model_validate(response.json())
        assert scraper_get_response.html_content

    def test_get_page_default_instance(self):
        url = BASE + "/get"
        payload = ScraperGetRequest(
            instance_id=ContractConfig.BROWSER_DEFAULT_ID,
            url=URLGenerator.next(),
            flag_lazy_loading=False,
        )
        response = requests.post(url, json=payload.model_dump(mode="json"), timeout=TIMEOUT_GET)
        assert response.status_code == 200, response.content
        scraper_get_response = ScraperGetResponse.model_validate(response.json())
        assert scraper_get_response.html_content

    def test_get_explicit_instance_dead(self):
        sleep(self.BROWSER_EXPLICIT_LIFESPAN)
        url = BASE + "/get_scraper_state"
        response = requests.get(url, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 200, response.content
        scraper_model = ScraperModel.model_validate(response.json())
        assert len(scraper_model.browsers) == 1
        assert self.BROWSER_EXPLICIT_ID not in scraper_model.browsers

    # def test_get_page_explicit_instance(self):
    #     url = BASE + "/get_scraper_state"
    #     response = requests.get(url, timeout=TIMEOUT_REQUESTS)
    #     assert response.status_code == 200, response.content
    #     browsers = json.loads(response.text)
    #     if self.BROWSER_EXPLICIT_ID in browsers:
    #         url = BASE + "/get"
    #         payload = {
    #             "instance_id": "default",
    #             "url": URLGenerator.next(),
    #             "flag_lazy_loading": False,
    #         }
    #         response = requests.post(url, json=payload, timeout=TIMEOUT_REQUESTS)
    #         assert response.status_code == 200, response.content

    # def test_get_page_default_instance(self):
    #     url = BASE + "/get"
    #     payload = {
    #         "instance_id": "default",
    #         "url": URLGenerator.next(),
    #         "flag_lazy_loading": False,
    #     }
    #     response = requests.post(url, json=payload, timeout=TIMEOUT_REQUESTS)
    #     assert response.status_code == 200, response.content

    # def test_kill_default_instance(self):
    #     url = BASE + "/kill"
    #     payload = {"instance_id": "default"}
    #     response = requests.post(url, json=payload, timeout=TIMEOUT_REQUESTS)
    #     assert response.status_code == 200, response.content

    # def test_explicit_instance_dead(self):
    #     sleep(EXPLICIT_NEW_INSTANCE_LIFESPAN)
    #     url = BASE + "/get_scraper_state"
    #     response = requests.get(url, timeout=TIMEOUT_REQUESTS)
    #     assert response.status_code == 200, response.content
    #     browsers = json.loads(response.text)
    #     assert EXPLICIT_NEW_INSTANCE_ID not in browsers


class TestScraperIntense:
    def create_the_same_browser_instance_twice(self):
        pass

# should test use after death of an instance
# recreating the instance with same data

# should stack a bunch of requests
#

class TestScraperFeatures:
    pass


# should implement a test on playin for lazy loading
"""
Found: it is because the browser returns an empty string if the getting task fails
And the error code is swallowed
It is also the source of the broker getting empty responses without an error code

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
        url = BASE + "/new-instance"
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
