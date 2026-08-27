MODULE_ORDER = [
    "test_scraper",
    "test_broker",
]


def pytest_collection_modifyitems(items):
    module_mapping = {value: index for index, value in enumerate(MODULE_ORDER)}
    items.sort(key=lambda item: module_mapping.get(item.module.__name__, 999))
