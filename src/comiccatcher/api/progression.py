# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

import asyncio
from comiccatcher.api.client import APIClient
from typing import Optional, Dict, List
from datetime import datetime, timezone
from http import HTTPStatus
from comiccatcher.logger import get_logger

logger = get_logger("net.progression")

FORMAT_LOCATOR = "locator"
FORMAT_FLAT = "flat"

class ProgressionSync:
    SYNC_DEBOUNCE_SEC = 1.0

    def __init__(self, api_client: APIClient, device_id: str):
        self.api = api_client
        self.device_id = device_id
        self._tasks: Dict[str, asyncio.Task] = {}
        self._formats: Dict[str, str] = {}
        
    async def get_progression(self, endpoint: str) -> Optional[Dict]:
        try:
            resp = await self.api.get(endpoint)
            if resp.status_code == HTTPStatus.OK:
                data = resp.json()
                logger.debug(f"Fetched progression from {endpoint}: {data}")
                if data:
                    if "locator" in data:
                        self._formats[endpoint] = FORMAT_LOCATOR
                    elif "progression" in data:
                        self._formats[endpoint] = FORMAT_FLAT
                return data
            elif resp.status_code != HTTPStatus.NOT_FOUND:
                logger.warning(f"Unexpected status fetching progression from {endpoint}: {resp.status_code}")
            return None
        except Exception as e:
            logger.error(f"Error fetching progression from {endpoint}: {e}")
            return None
            
    async def update_progression(self, endpoint: str, fraction: float, title: str = None, href: str = None, position: int = None, content_type: str = None, rel: str = None):
        """
        Sync progression based on the Readium Locator object specification 
        (used by Codex and LibrarySimplified).
        
        Includes a debounce to prevent server flooding (409 Conflicts) 
        during rapid page turns.
        """
        # Cancel any pending update for this specific endpoint
        current_task = asyncio.current_task()
        if endpoint in self._tasks:
            self._tasks[endpoint].cancel()
        self._tasks[endpoint] = current_task

        try:
            # Wait for a quiet period before syncing
            await asyncio.sleep(self.SYNC_DEBOUNCE_SEC)
            
            # Use +00:00 instead of Z for better compatibility with strict servers like Stump
            now_iso = datetime.now(timezone.utc).isoformat()
            
            # Make the device name unique per installation to avoid DB constraint failures
            short_id = self.device_id[:8]
            device_name = f"ComicCatcher PyQt6 ({short_id})"
            
            def build_payload(fmt: str) -> Dict:
                if fmt == FORMAT_FLAT:
                    payload = {
                        "modified": now_iso,
                        "device": {
                            "id": f"urn:uuid:{self.device_id}",
                            "name": device_name
                        },
                        "progression": fraction
                    }
                    if position is not None:
                        payload["position"] = position
                    if title:
                        payload["title"] = title
                    return payload
                else:
                    payload = {
                        "modified": now_iso,
                        "device": {
                            "id": f"urn:uuid:{self.device_id}",
                            "name": device_name
                        },
                        "locator": {
                            "locations": {
                                "progression": fraction,
                                "totalProgression": fraction,
                                "total_progression": fraction
                            }
                        }
                    }
                    if position is not None:
                        payload["locator"]["locations"]["position"] = position
                    if title:
                        payload["locator"]["title"] = title
                    if href:
                        payload["locator"]["href"] = href
                    if content_type:
                        payload["locator"]["type"] = content_type
                    return payload

            # Initialize format from relation link if not cached
            if endpoint not in self._formats and rel:
                if rel == "http://opds-spec.org/progression":
                    self._formats[endpoint] = FORMAT_FLAT
                else:
                    self._formats[endpoint] = FORMAT_LOCATOR

            fmt = self._formats.get(endpoint)
            if fmt is None:
                # Try legacy locator format first
                data = build_payload(FORMAT_LOCATOR)
                logger.debug(f"Syncing progression to {endpoint} using guess FORMAT_LOCATOR format. Payload: {data}")
                resp = await self.api.put(endpoint, json=data)
                logger.debug(f"Sync response from {endpoint}: Status={resp.status_code}, Body={resp.text}")
                if resp.status_code == HTTPStatus.BAD_REQUEST:
                    # Fallback to flat format
                    logger.info(f"Locator format rejected with 400. Falling back to flat format for {endpoint}.")
                    fmt = FORMAT_FLAT
                    self._formats[endpoint] = FORMAT_FLAT
                    data = build_payload(FORMAT_FLAT)
                    logger.debug(f"Syncing progression to {endpoint} using fallback FORMAT_FLAT format. Payload: {data}")
                    resp = await self.api.put(endpoint, json=data)
                    logger.debug(f"Sync response from {endpoint}: Status={resp.status_code}, Body={resp.text}")
                elif resp.status_code in [HTTPStatus.OK, HTTPStatus.CREATED, HTTPStatus.NO_CONTENT, HTTPStatus.CONFLICT]:
                    self._formats[endpoint] = FORMAT_LOCATOR
            else:
                data = build_payload(fmt)
                logger.debug(f"Syncing progression to {endpoint} using cached {fmt} format. Payload: {data}")
                resp = await self.api.put(endpoint, json=data)
                logger.debug(f"Sync response from {endpoint}: Status={resp.status_code}, Body={resp.text}")

            if resp.status_code not in [HTTPStatus.OK, HTTPStatus.CREATED, HTTPStatus.NO_CONTENT, HTTPStatus.CONFLICT]:
                body = resp.text
                logger.error(
                    f"Failed to sync progression to {endpoint}. "
                    f"Status: {resp.status_code}, Attempted: fraction={fraction}, pos={position}, "
                    f"Response: {body}"
                )
                
        except asyncio.CancelledError:
            # This update was superseded by a newer one
            pass
        except Exception as e:
            logger.error(f"Failed to sync progression: {e}")
        finally:
            if self._tasks.get(endpoint) == current_task:
                del self._tasks[endpoint]

    @staticmethod
    def extract_locations(data: Dict) -> tuple[Optional[float], Optional[int]]:
        """
        Extracts (progression_fraction, position) from a Readium Locator or flat object.
        Handles: position, totalProgression, total_progression, and progression.
        """
        if not data:
            return None, None
            
        loc = data.get("locator", {}).get("locations", {})
        
        # 1. Try position (most precise for comics)
        pos = loc.get("position")
        if pos is None:
            pos = data.get("position")
            
        # 2. Try global progression variants (Readium spec + variants)
        pct = loc.get("totalProgression")
        if pct is None:
            pct = loc.get("total_progression")
        if pct is None:
            pct = loc.get("progression")
            
        # 3. Fallback to flat structure
        if pct is None:
            pct = data.get("totalProgression") or data.get("total_progression") or data.get("progression")
            
        return (float(pct) if pct is not None else None), (int(pos) if pos is not None else None)
