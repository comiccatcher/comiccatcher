from typing import Optional, Dict
from api.client import APIClient
from models.opds import OPDSFeed, Publication
from logger import get_logger

logger = get_logger("api.opds")

class OPDS2Client:
    def __init__(self, api_client: APIClient):
        self.api = api_client
        self._cache: Dict[str, dict] = {} # URL -> JSON Data

    async def get_feed(self, url: str, force_refresh: bool = False) -> OPDSFeed:
        if not force_refresh and url in self._cache:
            logger.debug(f"JSON Cache hit for feed: {url}")
            return OPDSFeed(**self._cache[url])

        logger.debug(f"Fetching feed (force={force_refresh}): {url}")
        response = await self.api.get(url)
        response.raise_for_status()
        data = response.json()
        self._cache[url] = data
        try:
            return OPDSFeed(**data)
        except Exception as e:
            logger.error(f"Failed to parse OPDS feed from {url}: {e}")
            raise

    async def get_publication(self, url: str, force_refresh: bool = False) -> Publication:
        if not force_refresh and url in self._cache:
            logger.debug(f"JSON Cache hit for manifest: {url}")
            return Publication(**self._cache[url])

        logger.debug(f"Fetching publication manifest (force={force_refresh}): {url}")
        response = await self.api.get(url)
        response.raise_for_status()
        data = response.json()
        self._cache[url] = data
        try:
            return Publication(**data)
        except Exception as e:
            logger.error(f"Failed to parse publication manifest from {url}: {e}")
            raise

    def clear_cache(self, url: str = None):
        if url:
            self._cache.pop(url, None)
            logger.debug(f"Cleared JSON cache for: {url}")
        else:
            self._cache.clear()
            logger.debug("Cleared all JSON cache.")
