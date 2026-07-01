import ipaddress
import os


class Config:
    MAX_INSTANCES_PER_SCRAPER = int(os.getenv("MAX_INSTANCES_PER_SCRAPER"))
    NODE_ROLE = os.getenv("NODE_ROLE").split(",")
    if "SCRAPER" not in NODE_ROLE:
        raise ValueError("the node should be a scraper to launch this image")

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

    BROWSER_DEFAULT_ID = "default"
    BROWSER_DEFAULT_LIFESPAN = 3600  # 1 hour in seconds
    BROWSER_DEFAULT_WINDOW = [1920, 1080]

    ERHOLUNGSZEIT_MINIMUM = 2000  # milliseconds
    ERHOLUNGSZEIT_MEAN = 5000  # milliseconds
    ERHOLUNGSZEIT_SPREAD = 0.5  # variance

    REFRESH_RATE_SCRAPER = 0.1  # seconds

    TIME_LIMIT_LAZY_LOADING = 10  # seconds
