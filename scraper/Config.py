import ipaddress
import os


class Config:
    try:
        NODE_ROLE = os.getenv("NODE_ROLE").split(",")
    except Exception:
        pass

    ALLOWED_NETWORKS = [
        ipaddress.ip_network("127.0.0.0/8"),  # localhost
        # ipaddress.ip_network("10.0.0.0/24"),   # VPN network
        ipaddress.ip_network("10.0.0.1/32"),  # Lighthouse through VPN
        ipaddress.ip_network(
            "172.16.0.0/12"
        ),  # Docker bridge networks (for dev) (and includes 172.23.0.1 ie localnetwork)
        ipaddress.ip_network(
            "192.168.0.0/16"
        ),  # Docker compose networks (for the proxypi socket)
        ipaddress.ip_network("::1/128"),  # IPv6 localhost
    ]

    SCRAPER_DATABASE = "/data/scraper.db"

    RECOVERY_PERIOD_MINIMUM = 2000  # milliseconds
    RECOVERY_PERIOD_MEAN = 5000  # milliseconds
    RECOVERY_PERIOD_SPREAD = 0.5  # variance

    REFRESH_RATE_SCRAPER = 0.01  # seconds

    TIME_LIMIT_LAZY_LOADING = 10  # seconds
