import os
import hashlib
import base64
import httpx
from pathlib import Path
from typing import Optional
from comiccatcher.api.client import APIClient
from comiccatcher.config import CACHE_DIR
from comiccatcher.logger import get_logger

logger = get_logger("api.image_manager")

class ImageManager:
    def __init__(self, api_client: APIClient):
        self.api_client = api_client
        self._memory_cache = {} # URL -> Base64 string
        self._created_subdirs = set()
        self._pending_tasks = {} # URL -> asyncio.Task
        import asyncio
        self._semaphore = asyncio.Semaphore(4) # Limit concurrent image downloads to prioritize feeds

    def get_image_sync(self, url: str):
        """Synchronously retrieves an image from cache (memory or disk)."""
        if not url: return None
        
        from PyQt6.QtGui import QPixmap, QPixmapCache
        
        # 1. Check QPixmapCache
        cache_path = self._get_cache_path(url)
        pixmap = QPixmapCache.find(str(cache_path))
        if pixmap:
            return pixmap
            
        # 2. Check Disk Cache
        if cache_path.exists():
            try:
                pixmap = QPixmap(str(cache_path))
                if not pixmap.isNull():
                    QPixmapCache.insert(str(cache_path), pixmap)
                    return pixmap
            except Exception as e:
                logger.error(f"Error loading pixmap from disk {url}: {e}")
                
        return None

    async def get_image(self, url: str, api_client: Optional[APIClient] = None, max_dim: Optional[int] = None):
        """Fetches an image, caches it on disk, and returns it as a QPixmap."""
        from PyQt6.QtGui import QPixmap
        
        b64 = await self.get_image_b64(url, api_client, max_dim=max_dim)
        if not b64:
            return None
            
        try:
            from PyQt6.QtCore import QByteArray
            pixmap = QPixmap()
            pixmap.loadFromData(QByteArray.fromBase64(b64.encode("utf-8")))
            return pixmap
        except Exception as e:
            logger.error(f"Error converting B64 to Pixmap for {url}: {e}")
            return None

    async def get_image_b64(self, url: str, api_client: Optional[APIClient] = None, max_dim: Optional[int] = None, timeout: Optional[float] = None) -> Optional[str]:
        """Fetches an image, caches it on disk, and returns it as a Base64 string. Deduplicates concurrent requests."""
        if not url:
            return None

        # 1. Check Memory Cache
        if url in self._memory_cache:
            return self._memory_cache[url]

        # 2. Check for in-flight task (Deduplication)
        import asyncio
        if url in self._pending_tasks:
            return await self._pending_tasks[url]

        # 3. Create new task
        task = asyncio.create_task(self._fetch_image_b64(url, api_client, max_dim, timeout))
        self._pending_tasks[url] = task
        try:
            return await task
        finally:
            self._pending_tasks.pop(url, None)

    async def _fetch_image_b64(self, url: str, api_client: Optional[APIClient] = None, max_dim: Optional[int] = None, timeout: Optional[float] = None) -> Optional[str]:
        """Internal fetch logic."""
        # 1. Check Disk Cache
        cache_path = self._get_cache_path(url)
        if cache_path.exists():
            try:
                import base64
                with open(cache_path, "rb") as f:
                    data = f.read()
                    b64 = base64.b64encode(data).decode("utf-8")
                    self._memory_cache[url] = b64
                    return b64
            except Exception as e:
                logger.error(f"Error reading disk cache for {url}: {e}")

        # 2. Fetch from Server
        client = api_client or self.api_client
        if not client:
            logger.error(f"Cannot fetch {url}: No APIClient provided.")
            return None

        async with self._semaphore:
            try:
                logger.debug(f"Cache miss. Fetching image: {url}")
                img_timeout = timeout or 15.0
                resp = await client.get(url, timeout=img_timeout)
                if resp.status_code == 200:
                    data = resp.content
                    
                    if max_dim:
                        from PIL import Image
                        import io
                        try:
                            with Image.open(io.BytesIO(data)) as img:
                                if img.width > max_dim or img.height > max_dim:
                                    import asyncio
                                    data = await asyncio.to_thread(self._scale_image, data, max_dim)
                        except Exception as e:
                            logger.error(f"Error checking image dimensions for {url}: {e}")

                    with open(cache_path, "wb") as f:
                        f.write(data)

                    import base64
                    b64 = base64.b64encode(data).decode("utf-8")
                    self._memory_cache[url] = b64
                    return b64
                else:
                    logger.warning(f"Failed to fetch image {url} - Status: {resp.status_code}")
            except httpx.TimeoutException:
                logger.warning(f"Timeout fetching image {url} ({img_timeout}s)")
            except httpx.NetworkError as e:
                logger.warning(f"Network error fetching image {url}: {e}")
            except Exception as e:
                import traceback
                logger.error(f"Error fetching image {url}: {e}\n{traceback.format_exc()}")

        return None

    def _scale_image(self, data: bytes, max_dim: int) -> bytes:
        """Helper to scale down image bytes. Uses image_utils for high-quality scaling."""
        from comiccatcher.ui.image_utils import scale_image_to_bytes
        scaled = scale_image_to_bytes(data, max_dim, max_dim)
        return scaled if scaled else data

    def _get_cache_path(self, url: str) -> Path:
        """Generates a unique file path for a URL."""
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
        # Ensure subdirectory based on hash to avoid flat folder limits
        prefix = url_hash[:2]
        sub_dir = CACHE_DIR / prefix
        if prefix not in self._created_subdirs:
            sub_dir.mkdir(exist_ok=True)
            self._created_subdirs.add(prefix)
        return sub_dir / url_hash

    def clear_memory_cache(self):
        self._memory_cache.clear()

    def clear_disk_cache(self):
        """Removes all cached images from disk."""
        import shutil
        if CACHE_DIR.exists():
            try:
                # Remove everything inside CACHE_DIR but keep the dir itself
                for item in CACHE_DIR.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                self._created_subdirs.clear()
                logger.info("Disk cache cleared successfully.")
            except Exception as e:
                logger.error(f"Error clearing disk cache: {e}")
