import asyncio
from pathlib import Path
from typing import Any, Dict, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QFont

from logger import get_logger
from api.image_manager import ImageManager
from ui.local_archive import read_first_image
from ui.local_comicbox import flatten_comicbox, read_comicbox_dict, read_comicbox_cover

logger = get_logger("ui.library_detail")

def _read_comicbox_meta(path: Path) -> Dict[str, Any]:
    raw = read_comicbox_dict(path)
    return flatten_comicbox(raw)

class LocalComicDetailView(QWidget):
    def __init__(self, on_back, on_read_local=None):
        super().__init__()
        self.on_back = on_back
        self.on_read_local = on_read_local
        self._path: Optional[Path] = None
        self.image_manager = ImageManager(None)

        self.layout = QVBoxLayout(self)

        # Header
        self.header = QHBoxLayout()
        self.btn_back = QPushButton("Back")
        self.btn_back.clicked.connect(self.on_back)
        
        self.title_label = QLabel("Comic Title")
        self.title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.title_label.setWordWrap(True)
        
        self.btn_read = QPushButton("Read")
        self.btn_read.setStyleSheet("background-color: #2e7d32; color: white; padding: 8px 16px;")
        self.btn_read.clicked.connect(self._on_read_clicked)
        self.btn_read.setEnabled(False)

        self.header.addWidget(self.btn_back)
        self.header.addWidget(self.title_label, 1)
        self.header.addWidget(self.btn_read)
        self.layout.addLayout(self.header)

        # Path Label
        self.path_label = QLabel("")
        self.path_label.setStyleSheet("color: gray; font-size: 10px;")
        self.layout.addWidget(self.path_label)

        self.line = QFrame()
        self.line.setFrameShape(QFrame.Shape.HLine)
        self.line.setFrameShadow(QFrame.Shadow.Sunken)
        self.layout.addWidget(self.line)

        # Content (Cover + Metadata)
        self.content_layout = QHBoxLayout()
        
        # Cover
        self.cover_label = QLabel()
        self.cover_label.setFixedSize(300, 450)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setStyleSheet("border: 1px solid #444; background-color: #111;")
        self.cover_label.setScaledContents(True)
        self.content_layout.addWidget(self.cover_label, 0, Qt.AlignmentFlag.AlignTop)

        # Metadata Scroll Area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        self.meta_container = QWidget()
        self.meta_layout = QVBoxLayout(self.meta_container)
        self.meta_layout.setSpacing(10)
        self.meta_layout.addStretch()
        
        self.scroll.setWidget(self.meta_container)
        self.content_layout.addWidget(self.scroll, 1)

        self.layout.addLayout(self.content_layout)

    def load_path(self, path: Path):
        self._path = Path(path)
        self.title_label.setText(self._path.stem)
        self.path_label.setText(str(self._path))
        
        is_cbz = self._path.suffix.lower() == ".cbz"
        self.btn_read.setEnabled(is_cbz)
        
        # Clear existing meta
        for i in reversed(range(self.meta_layout.count())): 
            item = self.meta_layout.itemAt(i)
            if item.widget():
                item.widget().setParent(None)
        
        self.cover_label.clear()
        
        # Load data
        asyncio.create_task(self._load_meta(self._path))
        if is_cbz:
            asyncio.create_task(self._load_cover(self._path))

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

    def _render_meta(self, meta: Dict[str, Any]):
        # Clear stretch
        self.meta_layout.takeAt(self.meta_layout.count()-1)

        def add_row(label, value):
            if not value: return
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            
            l = QLabel(f"{label}:")
            l.setFixedWidth(120)
            l.setStyleSheet("color: gray; font-weight: bold;")
            
            v = QLabel(str(value))
            v.setWordWrap(True)
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            
            row_layout.addWidget(l)
            row_layout.addWidget(v, 1)
            self.meta_layout.addWidget(row)

        fields = [
            ("Title", "title"), ("Series", "series"), ("Issue", "issue"),
            ("Volume", "volume"), ("Year", "year"), ("Writer", "writer"),
            ("Penciller", "penciller"), ("Inker", "inker"), ("Colorist", "colorist"),
            ("Letterer", "letterer"), ("Editor", "editor"), ("Publisher", "publisher"),
            ("Page Count", "page_count")
        ]
        
        for label, key in fields:
            add_row(label, meta.get(key))
            
        if meta.get("summary"):
            add_row("Summary", meta.get("summary"))
        elif meta.get("description"):
            add_row("Summary", meta.get("description"))

        self.meta_layout.addStretch()

    def _on_read_clicked(self):
        if self.on_read_local and self._path:
            self.on_read_local(self._path)
