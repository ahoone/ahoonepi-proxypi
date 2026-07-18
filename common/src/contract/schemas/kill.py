from pydantic import BaseModel


class KillRequest(BaseModel):
    instance_id: str
