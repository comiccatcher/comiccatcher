# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

import asyncio
from pathlib import Path
from typing import Optional, List, Any

from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QPixmap

from comiccatcher.logger import get_logger
from comiccatcher.api.image_manager import ImageManager
from comiccatcher.config import ConfigManager
from comiccatcher.ui.theme_manager import UIConstants
from comiccatcher.ui.base_reader import BaseReaderView
from comiccatcher.ui.local_archive import LocalPage, list_archive_pages, read_archive_entry_bytes
from comiccatcher.ui.local_comicbox import generate_comic_labels

logger = get_logger("ui.local_reader")


class LocalReaderView(BaseReaderView):
    """
    Local comic archive reader (CBZ, CBR, CB7, CBT, PDF).

    Extracts pages from archives on a background thread and caches them
    to disk via ImageManager's cache layout.
    """

    def __init__(self, on_exit, image_manager: ImageManager, config_manager: ConfigManager, on_get_adjacent=None, on_transition=None, local_db=None):
        super().__init__(
            on_exit, 
            image_manager, 
            on_title_clicked=self._on_header_title_clicked,
            on_get_adjacent=on_get_adjacent,
            on_transition=on_transition,
            config_manager=config_manager
        )
        self.local_db = local_db
        self.config_manager = config_manager

        self._path: Optional[Path] = None
        self._pages: list[LocalPage] = []
        self._sem = asyncio.Semaphore(2)
        # Reuse ImageManager's disk-cache infra
        self._img_mgr = image_manager

        self.thumb_slider.set_thumb_loader(self._load_page_pixmap)

    def _on_header_title_clicked(self):
        if not self._path or not self.local_db: return
        
        # Fetch metadata from DB
        import sqlite3
        row = self.local_db.get_comic(str(self._path.absolute()))
        if not row: return
        r = dict(row)
        
        # Build credits
        creds = []
        for role in ["writer", "penciller", "inker", "colorist", "letterer", "editor"]:
            val = r.get(role)
            if val:
                creds.append(f"{role.capitalize()}: {val}")
        
        # Published info (Year)
        pub_info = r.get("year", "")
        
        # Get cover pixmap from cache
        cover_pixmap = QPixmap()
        cover_url = f"local-archive://{self._path.absolute()}/_cover_thumb"
        cache_path = self._img_mgr._get_cache_path(cover_url)
        if cache_path.exists():
            cover_pixmap.load(str(cache_path))

        # Build published string with month and year
        pub_month = r.get("month")
        pub_year = r.get("year")
        date_parts = []
        if pub_month:
            import calendar
            try:
                m_val = int(pub_month)
                if 1 <= m_val <= 12:
                    date_parts.append(calendar.month_name[m_val])
            except: pass
        if pub_year:
            date_parts.append(str(pub_year))

        data = {
            "credits": "\n".join(creds),
            "publisher": r.get("publisher"),
            "published": " ".join(date_parts) if date_parts else None,
            "summary": r.get("summary"),
            "web": r.get("web"),
            "manga": r.get("manga"),
            "notes": r.get("notes"),
            "imprint": r.get("imprint"),
            "genre": r.get("genre")
        }
        
        # Use focus-aware labels for the popover title
        label_focus = self.config_manager.get_library_label_focus()
        primary, secondary = generate_comic_labels(r, label_focus)
        
        self.meta_popover.set_show_cover(True)
        self.meta_popover.populate(cover_pixmap, data)
        
        # Center horizontally below header
        hdr_pos = self.header.mapToGlobal(self.header.rect().bottomLeft())
        x = hdr_pos.x() + self.header.width() // 2
        y = hdr_pos.y()
        self.meta_popover.show_at(QPoint(x, y), arrow_side="top")

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

    def load_archive(self, path: Path, context_paths: List[Path] = None):
        self.clear_display()
        self._path  = Path(path)
        self._pages = []
        self._index = 0
        self._context_paths = context_paths or []
        asyncio.create_task(self._load_pages())

    async def _load_pages(self):
        try:
            pages = await asyncio.to_thread(list_archive_pages, self._path)
            self._pages = pages
            if not pages:
                logger.error("No pages found in archive")
                return
            
            title = self._path.stem
            subtitle = None
            if self.local_db:
                row = await asyncio.to_thread(self.local_db.get_comic, str(self._path.absolute()))
                if row:
                    meta = dict(row)
                    saved_idx = meta.get("current_page", 0)
                    if 0 <= saved_idx < len(pages):
                        self._index = saved_idx
                        logger.info(f"Restoring progress to page {saved_idx}")
                    
                    # Use focus-aware label logic for consistency with Detail view
                    label_focus = self.config_manager.get_library_label_focus()
                    primary, secondary = generate_comic_labels(meta, label_focus)
                    
                    # Use primary label as title if we have meta, else filename
                    # Align with LocalDetailView: only use labels if we have real series/title meta
                    if meta.get("series") or meta.get("title"):
                        title = primary
                        subtitle = secondary
                    else:
                        title = self._path.stem
                        subtitle = None
            
            self._setup_reader(title, len(pages), subtitle, start_index=self._index)
            await self._show_page()
        except Exception as e:
            logger.error(f"Failed to load archive: {e}")

    # ------------------------------------------------------------------ #
    # Cache helpers                                                        #
    # ------------------------------------------------------------------ #

    async def _ensure_cached(self, idx: int, name: str) -> Optional[Path]:
        if not self._path:
            return None
        # Use a synthetic URL as a stable cache key
        url = f"local-archive://{self._path.absolute()}/{name}"
        cache_path = self._img_mgr._get_cache_path(url)
        if cache_path.exists():
            return cache_path
        async with self._sem:
            if cache_path.exists():   # re-check after acquiring semaphore
                return cache_path
            try:
                data = await asyncio.to_thread(read_archive_entry_bytes, self._path, name)
                if data:
                    cache_path.write_bytes(data)
                    return cache_path
            except Exception as e:
                logger.error(f"Extraction error for page {idx}: {e}")
        return None
