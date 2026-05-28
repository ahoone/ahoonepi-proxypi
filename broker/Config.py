import os
import ipaddress


class Config:

    HTTP_PORT_SCRAPER = os.environ["HTTP_PORT_SCRAPER"]
    NODE_ROLE = os.environ["NODE_ROLE"].split(",")
    SSH_NETWORK_BASE = os.environ["SSH_NETWORK_BASE"]
    WIREGUARD_NETWORK_PREFIX = os.environ["WIREGUARD_NETWORK_PREFIX"]

    if "LIGHTHOUSE" not in NODE_ROLE:
        raise ValueError("the node should be a lighthouse to launch this image")

    ALLOWED_NETWORKS = [
        ipaddress.ip_network("127.0.0.0/8"),  # localhost
        # ipaddress.ip_network("10.0.0.0/24"),      # VPN network
        ipaddress.ip_network("10.0.0.1/32"),  # Lighthouse through VPN
        ipaddress.ip_network("172.16.0.0/12"),  # Docker bridge networks (for dev)
        ipaddress.ip_network(
            "192.168.0.0/16"
        ),  # Docker compose networks (for the proxypi socket)
        ipaddress.ip_network("::1/128"),  # IPv6 localhost
    ]

    BROKER_DATABASE = "/tmp/broker.db"
    BROKER_CLEAR_DB_ON_STARTUP = True
    DB_TABLE_TARGETS = "targets"
    DB_TABLE_REQUESTS = "requests"
    BUFFER_LOGGER_SIZE = 10
    BUFFER_SCRAPING_LIST = 200
    REFRESH_PERIOD_BROKER = 1  # seconds
    THRESHOLD_SCORE = 300
