import asyncio
import os
from pathlib import Path
from typing import List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QFrame
)
from PyQt6.QtCore import Qt, QSize, QEvent
from PyQt6.QtGui import QPixmap, QKeyEvent, QImage, QPainter

from logger import get_logger
from api.image_manager import ImageManager
from ui.local_archive import LocalPage, list_cbz_pages, read_cbz_entry_bytes

logger = get_logger("ui.local_reader")

class LocalReaderView(QWidget):
    """
    High-performance local CBZ reader using QGraphicsView.
    """
    def __init__(self, on_exit):
        super().__init__()
        self.on_exit = on_exit
        self._path: Optional[Path] = None
        self._pages: List[LocalPage] = []
        self._index = 0
        self.image_manager = ImageManager(None)
        self._prefetch_tasks: set[int] = set()
        self._sem = asyncio.Semaphore(2)

        self.setStyleSheet("background-color: black; color: white;")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Header
        self.header = QFrame()
        self.header.setStyleSheet("background-color: rgba(0, 0, 0, 180);")
        self.header_layout = QHBoxLayout(self.header)
        
        self.btn_back = QPushButton("Back")
        self.btn_back.clicked.connect(self.on_exit)
        
        self.title_label = QLabel("")
        self.title_label.setStyleSheet("font-weight: bold;")
        
        self.counter_label = QLabel("0 / 0")
        
        self.header_layout.addWidget(self.btn_back)
        self.header_layout.addWidget(self.title_label, 1)
        self.header_layout.addWidget(self.counter_label)
        self.layout.addWidget(self.header)

        # Graphics View for Image
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.view.setStyleSheet("border: none; background-color: black;")
        
        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)
        
        self.layout.addWidget(self.view, 1)

        # Footer
        self.footer = QFrame()
        self.footer.setStyleSheet("background-color: rgba(0, 0, 0, 180);")
        self.footer_layout = QHBoxLayout(self.footer)
        
        self.btn_prev = QPushButton("Previous")
        self.btn_prev.clicked.connect(self.prev_page)
        
        self.btn_next = QPushButton("Next")
        self.btn_next.clicked.connect(self.next_page)
        
        self.footer_layout.addWidget(self.btn_prev)
        self.footer_layout.addStretch()
        self.footer_layout.addWidget(self.btn_next)
        self.layout.addWidget(self.footer)

        # Handle resize to fit image
        self.view.viewport().installEventFilter(self)

    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.Resize and source is self.view.viewport():
            self._fit_image()
        return super().eventFilter(source, event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Space, Qt.Key.Key_PageDown):
            self.next_page()
        elif event.key() in (Qt.Key.Key_Left, Qt.Key.Key_PageUp):
            self.prev_page()
        elif event.key() == Qt.Key.Key_Escape:
            self.on_exit()
        super().keyPressEvent(event)

    def load_cbz(self, path: Path):
        self._path = Path(path)
        self.title_label.setText(self._path.stem)
        self._pages = []
        self._index = 0
        self._prefetch_tasks.clear()
        
        asyncio.create_task(self._load_pages())

    async def _load_pages(self):
        try:
            pages = await asyncio.to_thread(list_cbz_pages, self._path)
            self._pages = pages
            if not pages:
                logger.error("No pages found")
                return
            await self._show_page()
        except Exception as e:
            logger.error(f"Failed to load pages: {e}")

    def next_page(self):
        if self._index < len(self._pages) - 1:
            self._index += 1
            asyncio.create_task(self._show_page())

    def prev_page(self):
        if self._index > 0:
            self._index -= 1
            asyncio.create_task(self._show_page())

    async def _show_page(self):
        if not self._path or not self._pages: return
        
        idx = self._index
        total = len(self._pages)
        self.counter_label.setText(f"{idx + 1} / {total}")
        self.btn_prev.setEnabled(idx > 0)
        self.btn_next.setEnabled(idx < total - 1)

        page = self._pages[idx]
        asset_path = await self._get_page_cache_path(idx, page.name)
        
        if asset_path and idx == self._index:
            pixmap = QPixmap(str(asset_path))
            if not pixmap.isNull():
                self.pixmap_item.setPixmap(pixmap)
                self.scene.setSceneRect(self.pixmap_item.boundingRect())
                self._fit_image()

        # Prefetch next 2
        for j in (idx + 1, idx + 2):
            if j < total and j not in self._prefetch_tasks:
                self._prefetch_tasks.add(j)
                asyncio.create_task(self._prefetch_page(j, self._pages[j].name))

    def _fit_image(self):
        if self.pixmap_item.pixmap().isNull(): return
        self.view.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    async def _prefetch_page(self, idx: int, name: str):
        try:
            await self._get_page_cache_path(idx, name)
        finally:
            self._prefetch_tasks.discard(idx)

    async def _get_page_cache_path(self, idx: int, name: str) -> Optional[Path]:
        if not self._path: return None
        url = f"local-cbz://{self._path.absolute()}/{name}"
        cache_path = self.image_manager._get_cache_path(url)
        
        if not cache_path.exists():
            async with self._sem:
                try:
                    data = await asyncio.to_thread(read_cbz_entry_bytes, self._path, name)
                    if data:
                        with open(cache_path, "wb") as f:
                            f.write(data)
                except Exception as e:
                    logger.error(f"Extraction error: {e}")
                    return None
        return cache_path if cache_path.exists() else None
