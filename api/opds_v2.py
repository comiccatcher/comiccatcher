import asyncio
from typing import Optional, Dict, Any
from api.client import APIClient
from models.opds import OPDSFeed, Publication
from logger import get_logger

logger = get_logger("api.opds")

class OPDS2Client:
    """
    Client for OPDS 2.0 servers.
    Supports task tracking for safe cancellation during navigation.
    """
    def __init__(self, api_client: APIClient):
        self.api = api_client
        self._cache = {}
        self._pending_tasks: Dict[str, asyncio.Task] = {}

    async def get_feed(self, url: str, force_refresh: bool = False) -> OPDSFeed:
        if not force_refresh and url in self._cache:
            return self._cache[url]
            
        # If already fetching this URL, return that task
        if url in self._pending_tasks:
            return await self._pending_tasks[url]
            
        task = asyncio.create_task(self._fetch_feed(url))
        self._pending_tasks[url] = task
        try:
            feed = await task
            self._cache[url] = feed
            return feed
        finally:
            self._pending_tasks.pop(url, None)

    async def _fetch_feed(self, url: str) -> OPDSFeed:
        logger.debug(f"Fetching feed: {url}")
        resp = await self.api.get(url)
        data = resp.json()
        return OPDSFeed(**data)

    async def get_publication(self, url: str, force_refresh: bool = False) -> Publication:
        if not force_refresh and url in self._cache:
            return self._cache[url]
            
        # If already fetching this URL, return that task
        if url in self._pending_tasks:
            return await self._pending_tasks[url]
            
        task = asyncio.create_task(self._fetch_publication(url))
        self._pending_tasks[url] = task
        try:
            pub = await task
            self._cache[url] = pub
            return pub
        finally:
            self._pending_tasks.pop(url, None)

    async def _fetch_publication(self, url: str) -> Publication:
        logger.debug(f"Fetching publication manifest: {url}")
        resp = await self.api.get(url)
        data = resp.json()
        return Publication(**data)

    def cancel_all(self):
        """Aborts all pending network requests."""
        count = len(self._pending_tasks)
        for url, task in self._pending_tasks.items():
            task.cancel()
        self._pending_tasks.clear()
        if count > 0:
            logger.info(f"OPDSClient: Cancelled {count} pending tasks.")

    def clear_cache(self, url: str = None):
        if url:
            self._cache.pop(url, None)
        else:
            self._cache.clear()
