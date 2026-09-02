from ipaddress import IPv4Network, IPv6Network
from pathlib import Path

from pydantic_settings import BaseSettings


class Config(BaseSettings):
    ALLOWED_NETWORKS: list[IPv4Network | IPv6Network] = [
        IPv4Network("127.0.0.0/8"),  # localhost
        # ipaddress.ip_network("10.0.0.0/24"),   # VPN network
        IPv4Network("10.0.0.1/32"),  # Lighthouse through VPN
        IPv4Network(
            "172.16.0.0/12"
        ),  # Docker bridge networks (for dev) (and includes 172.23.0.1 ie localnetwork)
        IPv4Network(
            "192.168.0.0/16"
        ),  # Docker compose networks (for the proxypi socket)
        IPv6Network("::1/128"),  # IPv6 localhost
    ]

    SCRAPER_LOGS: Path = Path("/data/scraper.log")
    SCRAPER_DATABASE: Path = Path("/data/scraper.db")
    DB_TABLE_PROFILES: str = "profiles"
    DB_TABLE_BROWSING_HISTORY: str = "browsing_history"

    RECOVERY_PERIOD_MINIMUM: float = 2000  # milliseconds
    RECOVERY_PERIOD_MEAN: float = 5000  # milliseconds
    RECOVERY_PERIOD_SPREAD: float = 0.5  # variance

    REFRESH_RATE_SCRAPER: float = 0.01  # seconds

    TIME_LIMIT_LAZY_LOADING: float = 10  # seconds


config = Config()
