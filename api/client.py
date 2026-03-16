import httpx
from typing import Optional, Dict, Any
from models.server import ServerProfile

class APIClient:
    def __init__(self, profile: ServerProfile):
        self.profile = profile
        self.client = httpx.AsyncClient(
            base_url=self.profile.get_base_url(), 
            timeout=30.0,
            follow_redirects=True
        )
        
        self._setup_auth()

    def _setup_auth(self):
        # Determine authentication method based on provided credentials
        if self.profile.bearer_token:
            self.client.headers.update({"Authorization": f"Bearer {self.profile.bearer_token}"})
        elif self.profile.username and self.profile.password:
            self.client.auth = httpx.BasicAuth(self.profile.username, self.profile.password)

    async def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> httpx.Response:
        return await self.client.get(endpoint, params=params)

    async def post(self, endpoint: str, json: Optional[Dict[str, Any]] = None) -> httpx.Response:
        return await self.client.post(endpoint, json=json)
        
    async def put(self, endpoint: str, json: Optional[Dict[str, Any]] = None) -> httpx.Response:
        return await self.client.put(endpoint, json=json)

    async def close(self):
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
