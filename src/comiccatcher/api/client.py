# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

import httpx
import locale
import platform
from typing import Optional, Dict, Any
from comiccatcher import __version__
from comiccatcher.models.feed import FeedProfile
from comiccatcher.config import NETWORK_TIMEOUT

class APIClient:
    def __init__(self, profile: FeedProfile):
        self.profile = profile
        self.client = httpx.AsyncClient(
            base_url=self.profile.get_base_url(), 
            timeout=NETWORK_TIMEOUT,
            follow_redirects=True
        )

        self._setup_headers()
        self._setup_auth()

    def _setup_headers(self):
        """Sets up default headers, including system language and User-Agent."""
        # 1. User-Agent
        ua = f"comiccatcher/{__version__} ({platform.system()}; Desktop)"
        self.client.headers.update({"User-Agent": ua})

        # 2. Accept-Language
        try:
            # Try to get the system's preferred language/region (e.g. ('en_US', 'UTF-8'))
            lang, encoding = locale.getlocale()
            if lang:
                # Standardize to RFC 2616 format: primary-subtag (e.g. en-US)
                accept_lang = lang.replace('_', '-')
                self.client.headers.update({"Accept-Language": f"{accept_lang}, *;q=0.5"})
        except Exception:
            # Fallback if locale detection fails
            pass

        # 3. Apply custom headers from profile (highest priority)
        if self.profile.custom_headers:
            self.client.headers.update(self.profile.custom_headers)

    def _setup_auth(self):
        # Determine authentication method based on provided credentials
        mode = self.profile.auth_type
        
        if mode == "apikey" and self.profile.api_key:
            self.client.headers.update({"X-API-Key": self.profile.api_key})
        elif mode == "bearer" and self.profile.bearer_token:
            self.client.headers.update({"Authorization": f"Bearer {self.profile.bearer_token}"})
        elif mode == "basic" and self.profile.username and self.profile.password:
            self.client.auth = httpx.BasicAuth(self.profile.username, self.profile.password)
        
        # Legacy fallback if auth_type is not set (e.g. older config files)
        if mode == "none":
            if self.profile.bearer_token:
                self.client.headers.update({"Authorization": f"Bearer {self.profile.bearer_token}"})
            elif self.profile.username and self.profile.password:
                self.client.auth = httpx.BasicAuth(self.profile.username, self.profile.password)

    async def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None, timeout: Optional[float] = None) -> httpx.Response:
        return await self.client.get(endpoint, params=params, timeout=timeout)

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
