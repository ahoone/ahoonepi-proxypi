from time import sleep

import pytest

MODULE_ORDER = [
    "test_scraper",
    "test_broker",
]
TIME_BETWEEN_TESTS = 0.5  # in seconds


def pytest_collection_modifyitems(items):
    module_mapping = {value: index for index, value in enumerate(MODULE_ORDER)}
    items.sort(key=lambda item: module_mapping.get(item.module.__name__, 999))


# @pytest.fixture(autouse=True)
# def wait_between_tests():
#     yield
#     sleep(TIME_BETWEEN_TESTS)
