import os


class Config:
    HTTP_PORT_BROKER = os.getenv("HTTP_PORT_BROKER")
    HTTP_PORT_SCRAPER = os.getenv("HTTP_PORT_SCRAPER")
    WIREGUARD_NETWORK_PREFIX = os.getenv("WIREGUARD_NETWORK_PREFIX")
    NODE_ID = 1

    ORIGIN_BROKER = f"http://{WIREGUARD_NETWORK_PREFIX}.{NODE_ID}:{HTTP_PORT_BROKER}"
    ORIGIN_SCRAPER = f"http://{WIREGUARD_NETWORK_PREFIX}.{NODE_ID}:{HTTP_PORT_SCRAPER}"

    TIMEOUT_GET = 60  # in seconds (long, as we are waiting for either "complete" or "interactive" status)
    TIMEOUT_REQUESTS = 4  # seconds (small generic)
    TIMEOUT_TERMINATE = 8  # seconds (medium)
    TIMEOUT_CLEAR = 20  # seconds (needs sometime to kill instances)
    LATENCY = 4  # seconds (time we give to the broker to handle requests)
