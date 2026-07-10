from ipaddress import IPv6Address

from broker.core.models.BrowserImage import BrowserImageModel
from broker.core.models.NodeIdentifier import NodeIdentifierModel
from pydantic import BaseModel


class ScraperImageModel(BaseModel):
    online: bool
    hostname: str
    node_id: int
    passport: NodeIdentifierModel
    ram_specs: str | None
    ram_usage: str | None
    ipv6: IPv6Address
    browsers: dict[str, BrowserImageModel]
