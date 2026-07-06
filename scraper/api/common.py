from core.Scraper import Scraper
from fastapi import Request


def get_scraper(request: Request) -> Scraper:
    return request.app.state.scraper
