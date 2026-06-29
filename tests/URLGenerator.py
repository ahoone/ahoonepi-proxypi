import random
from collections.abc import Iterator
from itertools import cycle

URLS = [
    "https://fastapi.tiangolo.com/",
    "https://github.com/cdpdriver/zendriver/tree/main",
    "https://fr.wikipedia.org/wiki/Sp%C3%A9cial:Page_au_hasard",
    "https://www.lemonde.fr/",
    "https://docs.pytest.org/en/stable/",
]


class URLGenerator:
    URLS = URLS

    __cycle: Iterator[str] = cycle(URLS)

    @classmethod
    def next(cls) -> str:
        return next(cls.__cycle)

    @classmethod
    def rand(cls) -> str:
        return random.choice(cls.URLS)
