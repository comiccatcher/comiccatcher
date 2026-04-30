# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

from typing import Optional, List, Dict
from pydantic import BaseModel, HttpUrl, Field

class FeedProfile(BaseModel):
    id: str
    name: str
    url: str
    auth_type: str = "none" # "none", "basic", "bearer", "apikey"
    username: Optional[str] = None
    password: Optional[str] = None
    bearer_token: Optional[str] = None
    api_key: Optional[str] = None
    icon_url: Optional[str] = None
    
    custom_headers: Dict[str, str] = Field(default_factory=dict)
    
    search_history: List[str] = Field(default_factory=list)
    pinned_searches: List[str] = Field(default_factory=list)
    paging_mode: str = "scrolled" # "scrolled" or "paged"
    skip_detail_view: bool = False

    def get_base_url(self) -> str:
        return self.url.rstrip('/')
