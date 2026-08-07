import requests

from broker.core.models.Broker import BrokerModel
from tests.Config import Config


def clear_broker():
    url = Config.ORIGIN_BROKER + "/clear"
    response = requests.post(url, timeout=Config.TIMEOUT_CLEAR)
    assert response.status_code == 204, response.content


def assert_one_scraper_no_requests_no_targets():
    url = Config.ORIGIN_BROKER + "/get_broker_state"
    response = requests.get(url, timeout=Config.TIMEOUT_REQUESTS)
    assert response.status_code == 200, response.content
    broker = BrokerModel.model_validate(response.json())
    assert broker.is_running_as_root
    assert len(broker.nodes) >= 1
    assert not broker.running_requests
    assert not broker.unscraped_targets
