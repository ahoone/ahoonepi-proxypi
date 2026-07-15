import asyncio
import json
from time import sleep

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
LATENCY = 4  # seconds (time we give to the broker to handle requests)


def __clear_broker():
    url = BASE + "/clear"
    response = requests.post(url, timeout=TIMEOUT_REQUESTS)
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
    TEST_URL = "http://example.com"
    TEST_TAG = "test_endpoint_scrape"

    shared_data = {}

    @pytest.mark.dependency()
    def test_endpoint_scrape(self):
        url = BASE + "/scrape"
        payload = ScrapeRequest(
            url=self.TEST_URL,
            tag=self.TEST_TAG,
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
        pass

    # def test_scrape_multiple_urls(self):
    #     url = Config.ORIGIN_BROKER + "/scrape"
    #     payload = {
    #         "url": [URLGenerator.next() for _ in range(20)],
    #         "tag": "test_scrape_multiple_urls",
    #         "flag_lazy_loading": True,
    #     }
    #     response = requests.post(url, json=payload, timeout=TIMEOUT_REQUESTS)
    #     assert response.status_code == 202, response.content

    # def test_clear(self):
    #     url = Config.ORIGIN_BROKER + "/clear"
    #     payload = {
    #         "flag_cancel_running_tasks": True,
    #         "flag_kill_browsers": True,
    #         "flag_clear_unassigned_targets": True,
    #     }
    #     response = requests.post(url, json=payload, timeout=TIMEOUT_REQUESTS)
    #     assert response.status_code == 204, response.content

    # def test_no_targets(self):
    #     url = Config.ORIGIN_BROKER + "/get_unscraped_targets"
    #     response = requests.get(url, timeout=TIMEOUT_REQUESTS)
    #     assert response.status_code == 200, response.content
    #     assert len(json.loads(response.content)) == 0, response.content

    # def test_no_browsers(self):
    #     # need to wait a bit for the clear method to push to proxies and to retrieve the update
    #     sleep(5)
    #     url = Config.ORIGIN_BROKER + "/nodes"
    #     response = requests.get(url, timeout=TIMEOUT_REQUESTS)
    #     assert response.status_code == 200, response.content
    #     response_as_dict = json.loads(response.content)
    #     for node in response_as_dict:
    #         assert "browsers" in node, node
    #         assert len(node["browsers"]) == 0, node


# class TestBrokerIntense:
#     @pytest.mark.asyncio
#     async def test_no_freeze(self):
#         """
#         - sends sequentially 20 targets with a semaphore

#         silently fails, need to find the error swalloing
#         """

#         async def scrape_and_collect_one(sem: asyncio.Semaphore):
#             async with sem:
#                 url = Config.ORIGIN_BROKER + "/scrape"
#                 payload = {
#                     "url": URLGenerator.next(),
#                     "tag": "test_no_freeze",
#                     "flag_lazy_loading": True,
#                 }
#                 response = requests.post(url, json=payload, timeout=TIMEOUT_REQUESTS)
#                 assert response.status_code == 202, response.content
#                 response_as_dict = json.loads(response.text)
#                 assert "uuid" in response_as_dict, response_as_dict
#                 uuid = response_as_dict["uuid"]
#                 url = Config.ORIGIN_BROKER + "/collect"
#                 payload = {"uuid": uuid}
#                 response = requests.get(url, json=payload, timeout=TIMEOUT_REQUESTS)

#                 assert response.status_code in [200, 425], (
#                     f"unexpected status code {response.status_code}"
#                 )
#                 if response.status_code == 425:
#                     sleep(20)
#                     response = requests.get(url, json=payload, timeout=TIMEOUT_REQUESTS)

#                 assert response.status_code == 200, response

#         sem = asyncio.Semaphore(4)  # maximum number of browser instances per scraper
#         await asyncio.gather(*[scrape_and_collect_one(sem) for _ in range(20)])
