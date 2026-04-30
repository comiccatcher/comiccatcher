# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

import asyncio
from typing import Optional, Dict, Any
from pydantic import ValidationError
from comiccatcher.api.client import APIClient
from comiccatcher.models.opds import OPDSFeed, Publication
from comiccatcher.logger import get_logger

logger = get_logger("api.opds")

class OPDSClientError(Exception):
    """Base exception for OPDS client errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, server_message: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.server_message = server_message

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
        try:
            resp = await self.api.get(url)
            resp.raise_for_status()
        except Exception as e:
            status = getattr(e.response, "status_code", None) if hasattr(e, "response") else None
            # Try to extract server message if available
            server_msg = None
            try:
                data = e.response.json()
                if isinstance(data, dict):
                    server_msg = data.get("message") or data.get("error")
            except: pass
            
            msg = f"HTTP Error {status}" if status else str(e)
            if server_msg:
                msg = f"{msg}: {server_msg}"
            raise OPDSClientError(msg, status_code=status, server_message=server_msg) from e

        content_type = resp.headers.get("content-type", "").lower()
        is_xml = "xml" in content_type or "atom" in content_type
        
        if is_xml:
            from comiccatcher.api.opds12_parser import parse_opds12
            try:
                return await parse_opds12(resp.text, self.api, url)
            except Exception as e:
                logger.error(f"OPDS 1.2 parsing error for feed at {url}: {e}")
                raise OPDSClientError(f"Failed to parse OPDS 1.2 XML: {e}") from e

        try:
            data = resp.json()
        except Exception as e:
            # Fallback if json fails and not explicitly xml
            from comiccatcher.api.opds12_parser import parse_opds12
            try:
                return await parse_opds12(resp.text, self.api, url)
            except Exception as xml_e:
                raise OPDSClientError("Invalid feed format. Failed as JSON and XML.") from e

        try:
            return OPDSFeed(**data)
        except ValidationError as e:
            logger.error(f"Schema validation error for feed at {url}: {e}")
            server_msg = data.get("message") if isinstance(data, dict) else None
            msg = "Invalid OPDS feed format"
            if server_msg:
                msg = f"Server Error: {server_msg}"
            raise OPDSClientError(msg, server_message=server_msg) from e

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
        try:
            resp = await self.api.get(url)
            resp.raise_for_status()
        except Exception as e:
            status = getattr(e.response, "status_code", None) if hasattr(e, "response") else None
            server_msg = None
            try:
                data = e.response.json()
                if isinstance(data, dict):
                    server_msg = data.get("message") or data.get("error")
            except: pass
            msg = f"HTTP Error {status}" if status else str(e)
            if server_msg: msg = f"{msg}: {server_msg}"
            raise OPDSClientError(msg, status_code=status, server_message=server_msg) from e

        data = resp.json()
        try:
            return Publication(**data)
        except ValidationError as e:
            logger.error(f"Schema validation error for publication at {url}: {e}")
            server_msg = data.get("message") if isinstance(data, dict) else None
            msg = "Invalid publication manifest"
            if server_msg:
                msg = f"Server Error: {server_msg}"
            raise OPDSClientError(msg, server_message=server_msg) from e

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
