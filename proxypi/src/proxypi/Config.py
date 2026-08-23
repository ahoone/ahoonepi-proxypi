from ipaddress import IPv4Network
from pathlib import Path

from pydantic import FilePath, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from proxypi.common.types import Port


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
        env_file="config.env",
        env_file_encoding="utf-8",
    )

    ssh_network_base: Port
    wireguard_network: IPv4Network
    proxypi_user: str

    lighthouse_private_key_path: FilePath = Path.home() / ".ssh" / "id_proxy_access"
    tcp_connection_timeout: int = 8  # seconds

    @computed_field
    @property
    def network_size(self) -> int:
        return self.wireguard_network.num_addresses - 2

    def __str__(self) -> str:
        return "\n".join(f"{k}={v}" for k, v in self.model_dump().items())


config = Config()
