from ipaddress import IPv6Address
from typing import Dict, Optional

from core.models.BrowserImage import BrowserImageModel
from core.models.NodeIdentifier import NodeIdentifierModel
from pydantic import BaseModel


class ScraperImageModel(BaseModel):
    online: bool
    hostname: str
    node_id: int
    passport: NodeIdentifierModel
    ram_specs: Optional[str]
    ram_usage: Optional[str]
    ipv6: IPv6Address
    browsers: Dict[str, BrowserImageModel]
