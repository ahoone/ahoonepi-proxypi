from ipaddress import IPv4Network
from pathlib import Path
from typing import override

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[4]


class Config(BaseSettings):
    """
    Should use generic types, because specific types
    defined in `proxypi.common.types` relies on values
    retrieved through configuration.
    """

    # TO DO: CHECK we are on the lighthouse
    # many functions accept port or None as an argument
    # the port identifying a proxy
    # and None means to run on the host

    model_config = SettingsConfigDict(
        extra="ignore",
        env_file=PROJECT_ROOT / "config.env",
        env_file_encoding="utf-8",
    )

    ssh_network_base: int
    wireguard_network: IPv4Network
    proxypi_user: str

    lighthouse_private_key_path: Path = Path.home() / ".ssh" / "id_proxy_access"
    lighthouse_public_key_path: Path = Path.home() / ".ssh" / "id_proxy_access.pub"

    tcp_connection_timeout: int = 8  # seconds
    concurrent_conn: int = 2
    lighthouse_id: int = 1

    @computed_field
    @property
    def network_size(self) -> int:
        return self.wireguard_network.num_addresses - 2

    @override
    def __str__(self) -> str:
        return "\n".join(f"{k}={v}" for k, v in self.model_dump().items())


config = Config()
