from pydantic_settings import BaseSettings


class Config(BaseSettings):
    MAX_INSTANCES_PER_SCRAPER: int = 4
    BROWSER_DEFAULT_LIFESPAN: int = 3600  # 1 hour in seconds


config = Config()
