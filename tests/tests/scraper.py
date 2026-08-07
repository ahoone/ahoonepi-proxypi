import math
from uuid import UUID

import requests
from contract.schemas.architecture import BrowsingRecord, ScraperModel
from contract.schemas.close_browser import CloseBrowserRequest
from contract.schemas.scrape import ScraperScrapeRequest

from tests.Config import Config


def terminate_scraper():
    url = Config.ORIGIN_SCRAPER + "/terminate"
    response = requests.post(url, timeout=Config.TIMEOUT_TERMINATE)
    assert response.status_code == 204, response.content


def assert_health():
    url = Config.ORIGIN_SCRAPER + "/get_scraper_state"
    response = requests.get(url, timeout=Config.TIMEOUT_REQUESTS)
    assert response.status_code == 200, response.content
    scraper_model = ScraperModel.model_validate(response.json())
    assert not scraper_model.is_running_as_root
    assert scraper_model.can_create_browser
    assert scraper_model.ram_specs
    assert scraper_model.ram_usage


def assert_instances_count(count: int):
    url = Config.ORIGIN_SCRAPER + "/get_scraper_state"
    response = requests.get(url, timeout=Config.TIMEOUT_REQUESTS)
    assert response.status_code == 200, response.content
    scraper_model = ScraperModel.model_validate(response.json())
    assert len(scraper_model.browsers) == count


def assert_instance_health(instance_uuid: UUID, lifespan_in_seconds: int):
    url = Config.ORIGIN_SCRAPER + "/get_scraper_state"
    response = requests.get(url, timeout=Config.TIMEOUT_REQUESTS)
    assert response.status_code == 200, response.content
    scraper_model = ScraperModel.model_validate(response.json())
    assert instance_uuid in scraper_model.browsers
    browser_model = scraper_model.browsers[instance_uuid]
    assert math.isclose(
        browser_model.remaining_lifespan.total_seconds(),
        lifespan_in_seconds,
        rel_tol=0.1,
    )
    assert browser_model.status == "idle"


def assert_get_page(payload: ScraperScrapeRequest):
    url = Config.ORIGIN_SCRAPER + "/scrape"
    response = requests.post(
        url, json=payload.model_dump(mode="json"), timeout=Config.TIMEOUT_GET
    )
    assert response.status_code == 200, response.content
    scraper_get_response = BrowsingRecord.model_validate(response.json())
    assert scraper_get_response.html


def close_instance(instance_uuid: UUID):
    url = Config.ORIGIN_SCRAPER + "/close_browser"
    payload = CloseBrowserRequest(profile_uuid=instance_uuid)
    response = requests.post(
        url, json=payload.model_dump(mode="json"), timeout=Config.TIMEOUT_GET
    )
    assert response.status_code == 204, response.content


def assert_instance_closing(instance_uuid: UUID):
    url = Config.ORIGIN_SCRAPER + "/get_scraper_state"
    response = requests.get(url, timeout=Config.TIMEOUT_REQUESTS)
    assert response.status_code == 200, response.content
    scraper_model = ScraperModel.model_validate(response.json())
    assert scraper_model.browsers[instance_uuid].status == "closing"
