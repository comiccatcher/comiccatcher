# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

from comiccatcher.api.client import APIClient
from typing import Optional, Dict, List
from datetime import datetime, timezone
from comiccatcher.logger import get_logger

logger = get_logger("api.progression")

class ProgressionSync:
    def __init__(self, api_client: APIClient, device_id: str):
        self.api = api_client
        self.device_id = device_id
        
    async def get_progression(self, endpoint: str) -> Optional[Dict]:
        try:
            resp = await self.api.get(endpoint)
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception as e:
            logger.error(f"Error fetching progression: {e}")
            return None
            
    async def update_progression(self, endpoint: str, fraction: float, title: str = None, href: str = None, position: int = None, content_type: str = None):
        """
        Sync progression based on the Readium Locator object specification 
        (used by Codex and LibrarySimplified).
        """
        try:
            # Use +00:00 instead of Z for better compatibility with strict servers like Stump
            now_iso = datetime.now(timezone.utc).isoformat()
            
            # Make the device name unique per installation to avoid DB constraint failures
            short_id = self.device_id[:8]
            device_name = f"ComicCatcher PyQt6 ({short_id})"
            
            data = {
                "modified": now_iso,
                "device": {
                    "id": f"urn:uuid:{self.device_id}",
                    "name": device_name
                },
                "locator": {
                    "locations": {
                        "progression": fraction,
                        "totalProgression": fraction,  # Spec-compliant (Stump)
                        "total_progression": fraction  # Compatibility (Codex/Legacy)
                    }
                }
            }
            
            if position is not None:
                data["locator"]["locations"]["position"] = position
            if title:
                data["locator"]["title"] = title
            if href:
                data["locator"]["href"] = href
            if content_type:
                data["locator"]["type"] = content_type
            
            resp = await self.api.put(endpoint, json=data)
            if resp.status_code not in [200, 201, 204]:
                logger.error(f"Failed to sync progression to {endpoint}. Status: {resp.status_code}")
                
        except Exception as e:
            logger.error(f"Failed to sync progression: {e}")

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
