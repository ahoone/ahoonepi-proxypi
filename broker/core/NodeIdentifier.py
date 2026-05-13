import asyncio
import exrex
from ping3 import ping
from typing import Set

from Config import Config

SEMAPHORE_UPDATE_REACHABLE_NODES = 200
TIMEOUT_SCRAPER_PING = 0.1  # seconds


class NodeIdentifier:

    node_ids: Set[int] = {
        int(x)
        for x in exrex.generate(
            Config.NODE_ID_RANGE_REGEX, limit=exrex.count(Config.NODE_ID_RANGE_REGEX)
        )
    }
    reachable_nodes: Set[int] = None

    @staticmethod
    async def ping(
        host: str,
        port: int,
        sem: asyncio.Semaphore,
    ) -> bool:
        async with sem:
            try:
                conn = asyncio.open_connection(host, port)
                reader, writer = await asyncio.wait_for(conn, TIMEOUT_SCRAPER_PING)
                writer.close()
                await writer.wait_closed()
                return True
            except ConnectionRefusedError:
                return True
            except asyncio.TimeoutError:
                return False
            except OSError:
                return False

    @classmethod
    async def update_reachable_nodes(cls) -> None:
        """
        Only checks if the nodes is accessible,
        independently of the remote scraper container running properly.
        Change ping(..., None, ...) to the desired port (HTTP_PORT_SCRAPER).
        """
        sem = asyncio.Semaphore(SEMAPHORE_UPDATE_REACHABLE_NODES)
        pings = [
            cls.ping(f"{Config.WIREGUARD_NETWORK_PREFIX}.{node_id}", None, sem)
            for node_id in cls.node_ids
        ]
        ping_results = await asyncio.gather(*pings)
        cls.reachable_nodes = {
            node_id
            for node_id, ping_result in zip(cls.node_ids, ping_results)
            if ping_result
        }

    def __init__(self, node_id: int) -> None:
        """
        This method should check for already used node_id.
        """
        if node_id not in NodeIdentifier.node_ids:
            raise ValueError("Invalid node_id")
        self.node_id: int = node_id
        self.vpn_address: str = f"{Config.WIREGUARD_NETWORK_PREFIX}.{node_id}"
        self.ssh_port: int = int(
            f"{Config.SSH_NETWORK_PREFIX}{str(node_id).zfill(len(str(max(NodeIdentifier.node_ids))))}"
        )

    async def available(self) -> bool:
        """
        deprecated, classmethod update reachable nodes is more powerful
        """
        response = await asyncio.to_thread(
            ping,
            self.vpn_address,
            timeout=TIMEOUT_SCRAPER_PING,
        )
        return response is not None
