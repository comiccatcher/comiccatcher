import asyncio
from pathlib import Path
from typing import Optional

from PyQt6.QtGui import QPixmap

from logger import get_logger
from api.image_manager import ImageManager
from ui.base_reader import BaseReaderView
from ui.local_archive import LocalPage, list_cbz_pages, read_cbz_entry_bytes

logger = get_logger("ui.local_reader")


class LocalReaderView(BaseReaderView):
    """
    Local CBZ reader.

    Extracts pages from zip archives on a background thread and caches them
    to disk via ImageManager's cache layout.
    """

    def __init__(self, on_exit, image_manager: ImageManager, local_db=None):
        super().__init__(on_exit)
        self.local_db = local_db
        self._path: Optional[Path] = None
        self._pages: list[LocalPage] = []
        self._sem = asyncio.Semaphore(2)
        # Reuse ImageManager's disk-cache infra
        self._img_mgr = image_manager

        self.thumb_slider.set_thumb_loader(self._load_page_pixmap)

    # ------------------------------------------------------------------ #
    # BaseReaderView interface                                             #
    # ------------------------------------------------------------------ #

    def _on_page_changed(self, idx: int):
        if self._path and self.local_db:
            self.local_db.update_progress(str(self._path.absolute()), idx, self._total)

    async def _load_page_pixmap(self, idx: int) -> Optional[QPixmap]:
        if not self._pages or idx >= len(self._pages):
            return None
        cache_path = await self._ensure_cached(idx, self._pages[idx].name)
        if not cache_path:
            return None
        pm = QPixmap(str(cache_path))
        return pm if not pm.isNull() else None

    async def _do_prefetch(self, idx: int):
        if self._pages and idx < len(self._pages):
            await self._ensure_cached(idx, self._pages[idx].name)

    # ------------------------------------------------------------------ #
    # Loading                                                              #
    # ------------------------------------------------------------------ #

    def load_cbz(self, path: Path):
        self._path  = Path(path)
        self._pages = []
        self._index = 0
        asyncio.create_task(self._load_pages())

    async def _load_pages(self):
        try:
            pages = await asyncio.to_thread(list_cbz_pages, self._path)
            self._pages = pages
            if not pages:
                logger.error("No pages found in archive")
                return
            
            # Check for saved progress
            if self.local_db:
                row = await asyncio.to_thread(self.local_db.get_comic, str(self._path.absolute()))
                if row:
                    r = dict(row)
                    saved_idx = r.get("current_page", 0)
                    if 0 <= saved_idx < len(pages):
                        self._index = saved_idx
                        logger.info(f"Restoring progress to page {saved_idx}")
            
            self._setup_reader(self._path.stem, len(pages))
            await self._show_page()
        except Exception as e:
            logger.error(f"Failed to load CBZ: {e}")

    # ------------------------------------------------------------------ #
    # Cache helpers                                                        #
    # ------------------------------------------------------------------ #

    async def _ensure_cached(self, idx: int, name: str) -> Optional[Path]:
        if not self._path:
            return None
        # Use a synthetic URL as a stable cache key
        url = f"local-cbz://{self._path.absolute()}/{name}"
        cache_path = self._img_mgr._get_cache_path(url)
        if cache_path.exists():
            return cache_path
        async with self._sem:
            if cache_path.exists():   # re-check after acquiring semaphore
                return cache_path
            try:
                data = await asyncio.to_thread(read_cbz_entry_bytes, self._path, name)
                if data:
                    cache_path.write_bytes(data)
                    return cache_path
            except Exception as e:
                logger.error(f"Extraction error for page {idx}: {e}")
        return None
