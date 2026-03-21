import asyncio
from pathlib import Path
from typing import Any, Dict, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QFrame, QSizePolicy, QProgressBar
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QFont

from logger import get_logger
from api.image_manager import ImageManager
from api.local_db import LocalLibraryDB
from ui.local_archive import read_first_image
from ui.local_comicbox import flatten_comicbox, read_comicbox_dict, read_comicbox_cover
from ui.views.base_detail import BaseDetailView

logger = get_logger("ui.library_detail")

def _read_comicbox_meta(path: Path) -> Dict[str, Any]:
    raw = read_comicbox_dict(path)
    return flatten_comicbox(raw)

class LocalComicDetailView(BaseDetailView):
    def __init__(self, on_back, image_manager: ImageManager, on_read_local=None, local_db: Optional[LocalLibraryDB] = None):
        super().__init__(on_back, image_manager)
        self.on_read_local = on_read_local
        self.db = local_db
        self._path: Optional[Path] = None

    def load_path(self, path: Path):
        self._path = Path(path)
        
        info_layout = self._setup_main_info_layout()
        self._add_title(self._path.stem)
        
        # Action Button
        self._add_read_button(self._on_read_clicked, "Read")
        self.btn_read.setObjectName("primary_button")
        is_cbz = self._path.suffix.lower() == ".cbz"
        self.btn_read.setEnabled(is_cbz)
        
        # Delete Button (At the other end of the row)
        self._add_delete_button(self._on_delete_clicked)
        
        # Progression
        self._add_progression_label()
        
        # Metadata Rows
        asyncio.create_task(self._load_meta(self._path))
        
        # Cover
        if is_cbz:
            asyncio.create_task(self._load_cover(self._path))
            if self.db:
                asyncio.create_task(self._load_progress(self._path))
        else:
            self.progression_label.hide()

    async def _load_meta(self, path: Path):
        try:
            meta = await asyncio.to_thread(_read_comicbox_meta, path)
            if path != self._path: return
            self._render_meta(meta)
        except Exception as e:
            logger.error(f"Error loading meta: {e}")

    async def _load_cover(self, path: Path):
        url = f"local-cbz://{path.absolute()}/_cover"
        cache_path = self.image_manager._get_cache_path(url)
        
        if not cache_path.exists():
            try:
                data = await asyncio.to_thread(read_comicbox_cover, path)
                if not data:
                    res = await asyncio.to_thread(read_first_image, path)
                    if res: _, data = res
                if data:
                    with open(cache_path, "wb") as f:
                        f.write(data)
            except Exception:
                pass
        
        if cache_path.exists() and path == self._path:
            pixmap = QPixmap(str(cache_path))
            if not pixmap.isNull():
                self.cover_label.setPixmap(pixmap)

    async def _load_progress(self, path: Path):
        try:
            row = await asyncio.to_thread(self.db.get_comic, str(path.absolute()))
            if row and path == self._path:
                r = dict(row)
                curr = r.get("current_page", 0)
                total = r.get("page_count", 0)
                
                if total > 0:
                    self.progression_label.show()
                    self.progression_label.setText(f"Page {curr + 1} of {total}")
                    self._update_cover_progress(curr, total)
                    
                    if curr >= total - 1:
                        self.progression_label.setText(f"Finished: {total} pages read")
                        self.btn_read.setText("Read Again")
                    elif curr > 0:
                        self.btn_read.setText("Resume Reading")
                    else:
                        self.btn_read.setText("Read")
                else:
                    self.progression_label.hide()
                    self.btn_read.setText("Read")
            else:
                self.progression_label.hide()
                self.btn_read.setText("Read")
        except Exception as e:
            logger.error(f"Error loading progress: {e}")
            self.progression_label.hide()

    def _render_meta(self, meta: Dict[str, Any]):
        fields = [
            ("Series", "series"), ("Issue", "issue"),
            ("Volume", "volume"), ("Year", "year"), ("Writer", "writer"),
            ("Penciller", "penciller"), ("Inker", "inker"), ("Colorist", "colorist"),
            ("Letterer", "letterer"), ("Editor", "editor"), ("Publisher", "publisher"),
            ("Page Count", "page_count")
        ]
        
        for label, key in fields:
            self._add_metadata_row(label, meta.get(key))
            
        if meta.get("summary"):
            self._add_metadata_row("Summary", meta.get("summary"))
        elif meta.get("description"):
            self._add_metadata_row("Summary", meta.get("description"))
            
        # Add path at bottom
        self._add_metadata_row("File", str(self._path))

        self.info_layout.addStretch()

    def _on_delete_clicked(self):
        if not self._path: return
        
        try:
            p = self._path.absolute()
            if p.exists():
                p.unlink()
                logger.info(f"Deleted file: {p}")
            
            if self.db:
                self.db.remove_comic(str(p))
                logger.info(f"Removed from DB: {p}")
                
            self.on_back()
        except Exception as e:
            logger.error(f"Error during delete: {e}")

    def _on_read_clicked(self):
        if self.on_read_local and self._path:
            self.on_read_local(self._path)
