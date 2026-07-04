import asyncio
import os
from typing import Set

import httpx
from Config import Config
from core.models.NodeIdentifier import NodeIdentifierModel
from ping3 import ping

SEMAPHORE_UPDATE_REACHABLE_NODES = 200
TIMEOUT_SCRAPER_PING = 0.1  # seconds


class NodeIdentifier:
    WIREGUARD_CIDR_PREFIX = int(os.getenv("WIREGUARD_CIDR_PREFIX"))
    if WIREGUARD_CIDR_PREFIX == 24:
        node_ids: Set[int] = set(range(255))
    else:
        raise ValueError(f"CIDR prefix {WIREGUARD_CIDR_PREFIX} not implemented")

    reachable_nodes: Set[int] = set()

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
        self.ssh_port: int = int(Config.SSH_NETWORK_BASE) + node_id - 2
        self.client: httpx.AsyncClient = httpx.AsyncClient()

    def to_model(self) -> NodeIdentifierModel:
        return NodeIdentifierModel(
            node_id=self.node_id,
            vpn_address=self.vpn_address,
            ssh_port=self.ssh_port,
        )

    async def close_client(self) -> None:
        await self.client.aclose()

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
