from uuid import UUID

from pydantic import BaseModel, HttpUrl


class ScraperGetRequest(BaseModel):
    profile_uuid: UUID
    url: HttpUrl
    flag_lazy_loading: bool
