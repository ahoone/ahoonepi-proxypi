from fastapi import Request

from scraper.core.Scraper import Scraper


def get_scraper(request: Request) -> Scraper:
    return request.app.state.scraper
