import threading
from time import sleep

import pytest
import requests
from contract.Config import Config as ContractConfig
from contract.schemas.close_browser import CloseBrowserRequest
from contract.schemas.new_instance import NewInstanceRequest, NewInstanceResponse
from contract.schemas.scrape import ScraperScrapeRequest

from tests.Config import Config
from tests.tests.helper_scraper import (
    assert_get_page,
    assert_health,
    assert_instance_closing,
    assert_instance_health,
    assert_instances_count,
    close_instance,
    terminate_scraper,
)
from tests.URLGenerator import URLGenerator

BASE = Config.ORIGIN_SCRAPER


@pytest.fixture(scope="class", autouse=True)
def prep():
    terminate_scraper()
    assert_instances_count(0)
    assert_health()


class TestScraperCore:
    BROWSER_EXPLICIT_LIFESPAN = 10
    shared_values = {
        "default": None,
        "explicit": None,
    }

    def test_default_new_instance(self):
        url = BASE + "/new-instance"
        response = requests.post(url, timeout=Config.TIMEOUT_REQUESTS)
        assert response.status_code == 201, response.content
        uuid = NewInstanceResponse.model_validate(response.json()).profile_uuid
        TestScraperCore.shared_values["default"] = uuid

    def test_default_instance(self):
        assert_instance_health(
            TestScraperCore.shared_values["default"],
            ContractConfig.BROWSER_DEFAULT_LIFESPAN,
        )

    def test_just_one_instance(self):
        assert_instances_count(1)

    def test_explicit_new_instance(self):
        sleep(10)
        url = BASE + "/new-instance"
        payload = NewInstanceRequest(
            profile_uuid=None,
            profile_name="explicit",
            lifespan_in_seconds=self.BROWSER_EXPLICIT_LIFESPAN,
            is_temporary=False,
        )
        response = requests.post(
            url, json=payload.model_dump(mode="json"), timeout=Config.TIMEOUT_REQUESTS
        )
        assert response.status_code == 201, response.content
        uuid = NewInstanceResponse.model_validate(response.json()).profile_uuid
        TestScraperCore.shared_values["explicit"] = uuid

    def test_explicit_instance(self):
        assert_instance_health(
            TestScraperCore.shared_values["explicit"],
            TestScraperCore.BROWSER_EXPLICIT_LIFESPAN,
        )

    def test_just_two_instances(self):
        assert_instances_count(2)

    def test_get_page_explicit_instance(self):
        payload = ScraperScrapeRequest(
            profile_uuid=TestScraperCore.shared_values["explicit"],
            url=URLGenerator.next(),
            flag_lazy_loading=False,
        )
        assert_get_page(payload)

    def test_get_page_default_instance(self):
        payload = ScraperScrapeRequest(
            profile_uuid=TestScraperCore.shared_values["default"],
            url=URLGenerator.next(),
            flag_lazy_loading=False,
        )
        assert_get_page(payload)

    def test_explicit_instance_closing(self):
        assert_instance_closing(TestScraperCore.shared_values["explicit"])

    def test_close_default_instance(self):
        close_instance(TestScraperCore.shared_values["default"])

    def test_default_instance_closing(self):
        assert_instance_closing(TestScraperCore.shared_values["default"])

    def test_both_instances_closed(self):
        sleep(10)
        assert_instances_count(0)

    def test_recreate_explicit_instance(self):
        url = BASE + "/new-instance"
        payload = NewInstanceRequest(
            profile_uuid=None,
            profile_name="explicit",
            lifespan_in_seconds=self.BROWSER_EXPLICIT_LIFESPAN,
            is_temporary=False,
        )
        response = requests.post(
            url, json=payload.model_dump(mode="json"), timeout=Config.TIMEOUT_REQUESTS
        )
        assert response.status_code == 201, response.content
        uuid = NewInstanceResponse.model_validate(response.json()).profile_uuid
        TestScraperCore.shared_values["explicit"] = uuid

    def test_recreated_explicit_instance(self):
        assert_instance_health(
            TestScraperCore.shared_values["explicit"],
            TestScraperCore.BROWSER_EXPLICIT_LIFESPAN,
        )

    def test_get_page_recreated_explicit_instance(self):
        payload = ScraperScrapeRequest(
            profile_uuid=TestScraperCore.shared_values["explicit"],
            url=URLGenerator.next(),
            flag_lazy_loading=False,
        )
        assert_get_page(payload)

    def test_close_recreated_explicit_instance(self):
        close_instance(TestScraperCore.shared_values["explicit"])

    def test_recreated_explicit_instance_closing(self):
        assert_instance_closing(TestScraperCore.shared_values["explicit"])

    def test_recreated_explicit_instance_dead(self):
        sleep(10)
        assert_instances_count(0)


class TestScraperIntense:
    SIMULTANEOUS_REQUESTS = 10
    shared_values = {
        "default": None,
    }

    def test_default_new_instance(self):
        url = BASE + "/new-instance"
        response = requests.post(url, timeout=Config.TIMEOUT_REQUESTS)
        assert response.status_code == 201, response.content
        uuid = NewInstanceResponse.model_validate(response.json()).profile_uuid
        TestScraperIntense.shared_values["default"] = uuid

    def test_default_instance(self):
        assert_instance_health(
            TestScraperIntense.shared_values["default"],
            ContractConfig.BROWSER_DEFAULT_LIFESPAN,
        )

    def test_simultaneous_get_page(self):

        def get_one_page():
            url = BASE + "/scrape"
            payload = ScraperScrapeRequest(
                profile_uuid=TestScraperIntense.shared_values["default"],
                url=URLGenerator.next(),
                flag_lazy_loading=False,
            )
            response = requests.post(
                url, json=payload.model_dump(mode="json"), timeout=Config.TIMEOUT_GET
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

        for _ in range(self.SIMULTANEOUS_REQUESTS):
            threading.Thread(target=get_one_page, daemon=True).start()

    def test_cancelling_tasks(self):
        url = BASE + "/close_browser"
        payload = CloseBrowserRequest(
            profile_uuid=TestScraperIntense.shared_values["default"]
        )
        response = requests.post(
            url, json=payload.model_dump(mode="json"), timeout=Config.TIMEOUT_GET
        )
        assert response.status_code == 204, response.content

    def test_default_instance_dead(self):
        sleep(10)
        assert_instances_count(0)

    def test_get_page_after_instance_dead(self):
        url = BASE + "/scrape"
        payload = ScraperScrapeRequest(
            profile_uuid=TestScraperIntense.shared_values["default"],
            url=URLGenerator.next(),
            flag_lazy_loading=False,
        )
        response = requests.post(
            url, json=payload.model_dump(mode="json"), timeout=Config.TIMEOUT_GET
        )
        assert response.status_code == 409, response.content


# class TestScraperFeatures:
#     # should test lazy loading (on playin)
#     pass
