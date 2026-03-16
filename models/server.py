from typing import Optional
from pydantic import BaseModel, HttpUrl

class ServerProfile(BaseModel):
    id: str
    name: str
    url: str
    username: Optional[str] = None
    password: Optional[str] = None
    bearer_token: Optional[str] = None

    def get_base_url(self) -> str:
        return self.url.rstrip('/')
