from typing import List, Optional, Dict
from pydantic import BaseModel, Field

class AuthLink(BaseModel):
    rel: str
    href: str
    type: Optional[str] = None

class AuthFlow(BaseModel):
    type: str
    labels: Optional[Dict[str, str]] = None
    links: List[AuthLink] = Field(default_factory=list)

class AuthDocument(BaseModel):
    id: str
    title: Optional[str] = None
    description: Optional[str] = None
    links: List[AuthLink] = Field(default_factory=list)
    authentication: List[AuthFlow] = Field(default_factory=list)
