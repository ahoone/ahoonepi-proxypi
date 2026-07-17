import asyncio
import json
from time import sleep

import httpx
import pytest
import requests

from broker.api.schemas.collect import CollectRequest, CollectResponse
from broker.api.schemas.scrape import ScrapeRequest, ScrapeResponse
from broker.core.models.Broker import BrokerModel
from tests.Config import Config
from tests.URLGenerator import URLGenerator

BASE = Config.ORIGIN_BROKER
TIMEOUT_GET = 60  # in seconds (long, as we are waiting for either "complete" or "interactive" status)
TIMEOUT_REQUESTS = 4  # seconds (small genetic)
TIMEOUT_CLEAR = 20  # seconds (needs sometime to kill instances)
LATENCY = 4  # seconds (time we give to the broker to handle requests)


def __clear_broker():
    url = BASE + "/clear"
    response = requests.post(url, timeout=TIMEOUT_CLEAR)
    assert response.status_code == 204, response.content


def __assert_one_scraper_no_requests_no_targets():
    url = BASE + "/get_broker_state"
    response = requests.get(url, timeout=TIMEOUT_REQUESTS)
    assert response.status_code == 200, response.content
    broker = BrokerModel.model_validate(response.json())
    assert broker.is_running_as_root
    assert len(broker.nodes) >= 1
    assert not broker.running_requests
    assert not broker.unscraped_targets


@pytest.fixture(scope="class", autouse=True)
def prep():
    __clear_broker()
    __assert_one_scraper_no_requests_no_targets()


class TestBrokerCore:
    shared_data = {}

    @pytest.mark.dependency()
    def test_endpoint_scrape(self):
        url = BASE + "/scrape"
        payload = ScrapeRequest(
            url="http://example.com",
            tag="test_endpoint_scrape",
            flag_lazy_loading=False,
        )
        response = requests.post(
            url, json=payload.model_dump(mode="json"), timeout=TIMEOUT_REQUESTS
        )
        assert response.status_code == 202, response.content
        model = ScrapeResponse.model_validate(response.json())
        assert model.uuid
        TestBrokerCore.shared_data["uuid"] = model.uuid

    @pytest.mark.dependency(depends=["TestBrokerCore::test_endpoint_scrape"])
    def test_browser_created(self):
        """
        For now, we consider fine that the broker creates
        more than 1 browser for the first request.
        It is more of a feature than a bug (we want to have
        a browser as fast as possible.)
        """
        sleep(LATENCY)
        url = BASE + "/get_broker_state"
        response = requests.get(url, timeout=TIMEOUT_REQUESTS)
        assert response.status_code == 200, response.content
        broker = BrokerModel.model_validate(response.json())
        assert len(broker.nodes) >= 1, broker.nodes
        assert sum([len(node.browsers) for node in broker.nodes]) >= 1, broker.nodes

    @pytest.mark.dependency(depends=["TestBrokerCore::test_browser_created"])
    def test_endpoint_collect(self):
        sleep(TIMEOUT_GET)
        url = BASE + "/collect"
        payload = CollectRequest(uuid=self.shared_data["uuid"])
        response = requests.get(
            url, json=payload.model_dump(mode="json"), timeout=TIMEOUT_REQUESTS
        )
        assert response.status_code == 200, response.content
        collect_object = CollectResponse.model_validate(response.json())
        assert collect_object.content
        assert (
            "This domain is for use in documentation examples without needing permission. Avoid use in operations."
            in collect_object.content
        )

    def test_endpoint_scrape_multiple_urls(self):
        MULTIPLIER = 20
        url = BASE + "/scrape"
        payload = ScrapeRequest(
            url=[URLGenerator.next() for _ in range(MULTIPLIER)],
            tag="test_endpoint_scrape_multiple_urls",
            flag_lazy_loading=True,
        )
        response = requests.post(url, json=payload.model_dump(mode="json"))
        assert response.status_code == 202, response.content


class TestBrokerCloudflare:
    shared_data = {}

    URL = "https://httpx.readthedocs.io/en/latest/"

    @pytest.mark.dependency()
    def test_cloudflare_challenge_bypass(self):
        url = BASE + "/scrape"
        payload = ScrapeRequest(
            url=self.URL,
            tag="test_cloudflare_challenge_bypass",
            flag_lazy_loading=False,
        )
        response = requests.post(
            url, json=payload.model_dump(mode="json"), timeout=TIMEOUT_REQUESTS
        )
        assert response.status_code == 202, response.content
        model = ScrapeResponse.model_validate(response.json())
        assert model.uuid
        TestBrokerCore.shared_data["uuid"] = model.uuid

    @pytest.mark.dependency(
        depends=["TestBrokerCloudflare::test_cloudflare_challenge_bypass"]
    )
    def test_endpoint_collect(self):
        sleep(TIMEOUT_GET)
        url = BASE + "/collect"
        payload = CollectRequest(uuid=self.shared_data["uuid"])
        response = requests.get(
            url, json=payload.model_dump(mode="json"), timeout=TIMEOUT_REQUESTS
        )
        assert response.status_code == 200, response.content
        collect_object = CollectResponse.model_validate(response.json())
        assert collect_object.content
        assert "Welcome to Read the Doc" in collect_object.content


class TestBrokerIntense:
    client = httpx.AsyncClient()

    @pytest.mark.asyncio
    async def test_no_freeze(self):
        """
        - sends sequentially 20 targets with a semaphore

        silently fails, need to find the error swalloing
        """
        MULTIPLIER = 8
        SEMAPHORE = 8

        async def scrape_and_collect_one(sem: asyncio.Semaphore):
            url = Config.ORIGIN_BROKER + "/scrape"
            payload = ScrapeRequest(
                url=URLGenerator.next(),
                tag="test_no_freeze",
                flag_lazy_loading=True,
            )
            response = await self.client.request(
                "POST",
                url,
                json=payload.model_dump(mode="json"),
                timeout=TIMEOUT_REQUESTS,
            )
            assert response.status_code == 202, response.content
            uuid = ScrapeResponse.model_validate(response.json()).uuid
            assert uuid
            url = Config.ORIGIN_BROKER + "/collect"
            payload = CollectRequest(uuid=uuid)
            response = await self.client.request(
                "GET",
                url,
                json=payload.model_dump(mode="json"),
                timeout=TIMEOUT_REQUESTS,
            )

            assert response.status_code in [200, 425], (
                response.status_code,
                response.content,
            )
            if response.status_code == 425:
                # this timeout applies to the entire BATCH
                await asyncio.sleep(2 * TIMEOUT_GET)
                response = await self.client.request(
                    "GET",
                    url,
                    json=payload.model_dump(mode="json"),
                    timeout=TIMEOUT_REQUESTS,
                )

            assert response.status_code == 200, response

        sem = asyncio.Semaphore(SEMAPHORE)
        await asyncio.gather(*[scrape_and_collect_one(sem) for _ in range(MULTIPLIER)])
