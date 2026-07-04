from pydantic import BaseModel


class NodeIdentifierModel(BaseModel):
    node_id: int
    vpn_address: str
    ssh_port: int
