from api.client import APIClient
from typing import Optional, Dict
from datetime import datetime, timezone

class ProgressionSync:
    def __init__(self, api_client: APIClient):
        self.api = api_client
        
    async def get_progression(self, endpoint: str) -> Optional[Dict]:
        try:
            resp = await self.api.get(endpoint)
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception as e:
            print(f"Error fetching progression: {e}")
            return None
            
    async def update_progression(self, endpoint: str, current: float, total: float):
        try:
            data = {
                "progression": current,
                "totalProgression": total,
                "modified": datetime.now(timezone.utc).isoformat()
            }
            await self.api.put(endpoint, json=data)
        except Exception as e:
            print(f"Failed to sync progression: {e}")
