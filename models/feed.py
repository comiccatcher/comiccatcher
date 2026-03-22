from typing import Optional, List
from pydantic import BaseModel, HttpUrl, Field

class FeedProfile(BaseModel):
    id: str
    name: str
    url: str
    username: Optional[str] = None
    password: Optional[str] = None
    bearer_token: Optional[str] = None
    icon_url: Optional[str] = None
    
    search_history: List[str] = Field(default_factory=list)
    pinned_searches: List[str] = Field(default_factory=list)
    paging_mode: str = "scrolled" # "scrolled" or "paged"

    def get_base_url(self) -> str:
        return self.url.rstrip('/')
