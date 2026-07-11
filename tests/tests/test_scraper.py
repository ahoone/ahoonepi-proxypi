import math
import threading
from time import sleep

import requests
from contract.Config import Config as ContractConfig
from contract.schemas.architecture import ScraperModel
from contract.schemas.get import ScraperGetRequest, ScraperGetResponse
from contract.schemas.kill import KillRequest
from contract.schemas.new_instance import NewInstanceRequest

from scraper.Config import Config as ScraperConfig
from tests.Config import Config
from tests.URLGenerator import URLGenerator

BASE = Config.ORIGIN_SCRAPER
TIMEOUT_GET = 60  # in seconds (long, as we are waiting for either "complete" or "interactive" status)
TIMEOUT_REQUESTS = 4  # seconds (small genetic)
TIMEOUT_TERMINATE = 8  # seconds (medium)

"""
To investigate:

INFO:     172.22.0.1:37020 - "POST /get HTTP/1.1" 200 OK
INFO:     172.22.0.1:37032 - "POST /get HTTP/1.1" 200 OK
INFO:     172.22.0.1:53606 - "GET /get_scraper_state HTTP/1.1" 200 OK
INFO:     172.22.0.1:53606 - "GET /get_scraper_state HTTP/1.1" 200 OK
INFO:     172.22.0.1:53606 - "GET /get_scraper_state HTTP/1.1" 200 OK
INFO:     172.22.0.1:53606 - "GET /get_scraper_state HTTP/1.1" 200 OK
INFO:     172.22.0.1:53606 - "GET /get_scraper_state HTTP/1.1" 200 OK
Could not send the close command when stopping the browser. Likely the browser is already gone. Closing the connection.
INFO:     172.22.0.1:56210 - "GET /get_scraper_state HTTP/1.1" 200 OK
INFO:     172.22.0.1:56222 - "POST /kill HTTP/1.1" 204 No Content
INFO:     172.22.0.1:56226 - "GET /get_scraper_state HTTP/1.1" 200 OK
INFO:     172.22.0.1:53606 - "GET /get_scraper_state HTTP/1.1" 200 OK
Could not send the close command when stopping the browser. Likely the browser is already gone. Closing the connection.
INFO:     172.22.0.1:56228 - "POST /new-instance HTTP/1.1" 201 Created
INFO:     172.22.0.1:56236 - "GET /get_scraper_state HTTP/1.1" 200 OK
INFO:     172.22.0.1:56334 - "POST /get HTTP/1.1" 500 Internal Server Error
INFO:     172.22.0.1:56278 - "POST /get HTTP/1.1" 500 Internal Server Error
INFO:     172.22.0.1:56250 - "POST /get HTTP/1.1" 500 Internal Server Error
INFO:     172.22.0.1:56306 - "POST /get HTTP/1.1" 500 Internal Server Error
INFO:     172.22.0.1:56294 - "POST /get HTTP/1.1" 500 Internal Server Error
INFO:     172.22.0.1:56266 - "POST /get HTTP/1.1" 500 Internal Server Error
INFO:     172.22.0.1:56320 - "POST /get HTTP/1.1" 500 Internal Server Error
INFO:     172.22.0.1:56290 - "POST /get HTTP/1.1" 500 Internal Server Error
INFO:     172.22.0.1:56362 - "POST /kill HTTP/1.1" 204 No Content
INFO:     172.22.0.1:56374 - "GET /get_scraper_state HTTP/1.1" 200 OK
INFO:     172.22.0.1:56388 - "POST /get HTTP/1.1" 409 Conflict
Could not send the close command when stopping the browser. Likely the browser is already gone. Closing the connection.
"""


class TestScraperPrep:
    def test_endpoint_terminate(self):
        """
        Test the endpoint and clear the browsers for the following tests.
        """
        url = BASE + "/terminate"
        response = requests.post(url, timeout=TIMEOUT_TERMINATE)
        assert response.status_code == 204, response.content

    def test_no_instance_running(self):
        url = BASE + "/get_scraper_state"
        response = requests.get(url, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 200, response.content
        scraper_model = ScraperModel.model_validate(response.json())
        assert not scraper_model.browsers

    def test_health(self):
        url = BASE + "/get_scraper_state"
        response = requests.get(url, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 200, response.content
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
        assert math.isclose(
            browser_model.remaining_lifespan.total_seconds(),
            ContractConfig.BROWSER_DEFAULT_LIFESPAN,
            rel_tol=0.05,
        )
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
        response = requests.post(
            url, json=payload.model_dump(), timeout=TIMEOUT_REQUESTS
        )
        assert response.status_code == 201, response.content

    def test_explicit_instance(self):
        url = BASE + "/get_scraper_state"
        response = requests.get(url, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 200, response.content
        scraper_model = ScraperModel.model_validate(response.json())
        assert self.BROWSER_EXPLICIT_ID in scraper_model.browsers
        browser_model = scraper_model.browsers[self.BROWSER_EXPLICIT_ID]
        assert browser_model.window_size == self.BROWSER_EXPLICIT_WINDOW
        assert math.isclose(
            browser_model.remaining_lifespan.total_seconds(),
            self.BROWSER_EXPLICIT_LIFESPAN,
            rel_tol=0.05,
        )
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
        response = requests.post(
            url, json=payload.model_dump(mode="json"), timeout=TIMEOUT_GET
        )
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
        response = requests.post(
            url, json=payload.model_dump(mode="json"), timeout=TIMEOUT_GET
        )
        assert response.status_code == 200, response.content
        scraper_get_response = ScraperGetResponse.model_validate(response.json())
        assert scraper_get_response.html_content

    def test_explicit_instance_dead(self):
        """
        we need to account for:
            - the lifespan of the browser
            - the time for the loop to spot the expiration
            - the time for the kill method to be done (let's say 1 seconds)
        """
        sleep(self.BROWSER_EXPLICIT_LIFESPAN + ScraperConfig.REFRESH_RATE_SCRAPER + 1)
        url = BASE + "/get_scraper_state"
        response = requests.get(url, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 200, response.content
        scraper_model = ScraperModel.model_validate(response.json())
        assert len(scraper_model.browsers) == 1
        assert self.BROWSER_EXPLICIT_ID not in scraper_model.browsers

    def test_kill_default_instance(self):
        url = BASE + "/kill"
        payload = KillRequest(instance_id=ContractConfig.BROWSER_DEFAULT_ID)
        response = requests.post(
            url, json=payload.model_dump(mode="json"), timeout=TIMEOUT_GET
        )
        assert response.status_code == 204, response.content

    def test_default_instance_dead(self):
        url = BASE + "/get_scraper_state"
        response = requests.get(url, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 200, response.content
        scraper_model = ScraperModel.model_validate(response.json())
        assert len(scraper_model.browsers) == 0


class TestScraperIntense:
    SIMULTANEOUS_REQUESTS = 10

    def test_recreate_default_instance(self):
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
        assert math.isclose(
            browser_model.remaining_lifespan.total_seconds(),
            ContractConfig.BROWSER_DEFAULT_LIFESPAN,
            rel_tol=0.05,
        )
        assert browser_model.status == "idle"
        assert not browser_model.browsing_history

    def test_simultaneous_get_page(self):

        def get_one_page():
            url = BASE + "/get"
            payload = ScraperGetRequest(
                instance_id=ContractConfig.BROWSER_DEFAULT_ID,
                url=URLGenerator.next(),
                flag_lazy_loading=False,
            )
            response = requests.post(
                url, json=payload.model_dump(mode="json"), timeout=TIMEOUT_GET
            )
            if response.status_code == 500:
                return
                # not expected: race condition
                # - the broker was existing when the check was done in the api route
                # - the broker had been deleted when the route called the scraper method
            elif response.status_code == 503:
                return  # expected: request was killed mid-flight by the next test
            elif response.status_code == 409:
                return  # expected: request was received after the scraper killed the instance
            assert response.status_code == 200, response.content
            scraper_get_response = ScraperGetResponse.model_validate(response.json())
            assert scraper_get_response.html_content

        for _ in range(self.SIMULTANEOUS_REQUESTS):
            threading.Thread(target=get_one_page, daemon=True).start()

    def test_cancelling_tasks(self):
        url = BASE + "/kill"
        payload = KillRequest(instance_id=ContractConfig.BROWSER_DEFAULT_ID)
        response = requests.post(
            url, json=payload.model_dump(mode="json"), timeout=TIMEOUT_GET
        )
        assert response.status_code == 204, response.content

    def test_default_instance_dead(self):
        url = BASE + "/get_scraper_state"
        response = requests.get(url, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 200, response.content
        scraper_model = ScraperModel.model_validate(response.json())
        assert len(scraper_model.browsers) == 0

    def test_get_page_after_instance_dead(self):
        url = BASE + "/get"
        payload = ScraperGetRequest(
            instance_id=ContractConfig.BROWSER_DEFAULT_ID,
            url=URLGenerator.next(),
            flag_lazy_loading=False,
        )
        response = requests.post(
            url, json=payload.model_dump(mode="json"), timeout=TIMEOUT_GET
        )
        assert response.status_code == 409, response.content


class TestScraperFeatures:
    # should test lazy loading (on playin)
    pass
