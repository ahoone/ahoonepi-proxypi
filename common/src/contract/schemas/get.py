from pydantic import BaseModel, HttpUrl


class ScraperGetRequest(BaseModel):
    instance_id: str
    url: HttpUrl
    flag_lazy_loading: bool
