import asyncio
import traceback
from pathlib import Path
from typing import List, Optional
from urllib.parse import urljoin

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QFrame
)
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QPixmap, QKeyEvent, QPainter

from logger import get_logger
from api.client import APIClient
from api.image_manager import ImageManager
from api.progression import ProgressionSync
from models.opds import Publication

logger = get_logger("ui.reader")

class ReaderView(QWidget):
    """
    High-performance streaming OPDS reader using QGraphicsView.
    """
    def __init__(self, api_client: APIClient, on_exit):
        super().__init__()
        self.api_client = api_client
        self.on_exit = on_exit
        self.image_manager = None
        self.progression_sync = None
        self.progression_url = None
        
        self._current_pub = None
        self._manifest_url = None
        self._reading_order = []
        self._index = 0
        self._prefetch_set = set()
        self._load_token = 0

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
        
        self.title_label = QLabel("Loading...")
        self.title_label.setStyleSheet("font-weight: bold;")
        
        self.counter_label = QLabel("0 / 0")
        
        self.header_layout.addWidget(self.btn_back)
        self.header_layout.addWidget(self.title_label, 1)
        self.header_layout.addWidget(self.counter_label)
        self.layout.addWidget(self.header)

        # Graphics View
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

    def load_manifest(self, pub: Publication, manifest_url: str):
        self._load_token += 1
        self._current_pub = pub
        self._manifest_url = manifest_url
        self.title_label.setText(pub.metadata.title)
        self.image_manager = ImageManager(self.api_client)
        self.progression_sync = ProgressionSync(self.api_client)
        self._reading_order = []
        self._index = 0
        self._prefetch_set.clear()
        
        # Determine progression URL
        self.progression_url = None
        for link in pub.links:
            if getattr(link, 'rel', '') == "http://www.cantook.com/api/progression":
                self.progression_url = urljoin(self.api_client.profile.get_base_url(), link.href)
                break

        asyncio.create_task(self._fetch_and_load(self._load_token))

    async def _fetch_and_load(self, token: int):
        try:
            if self._manifest_url:
                response = await self.api_client.get(self._manifest_url)
                response.raise_for_status()
                data = response.json()
                if "readingOrder" in data:
                    self._reading_order = data["readingOrder"]
            elif self._current_pub.readingOrder:
                self._reading_order = [item.model_dump() for item in self._current_pub.readingOrder]

            if token != self._load_token: return

            if not self._reading_order:
                logger.error("No pages found")
                return

            # Initial index from progression if available
            if self.progression_url:
                prog_data = await self.progression_sync.get_progression(self.progression_url)
                if prog_data and "progression" in prog_data:
                    pct = prog_data["progression"]
                    self._index = int(pct * len(self._reading_order))
                    self._index = min(max(self._index, 0), len(self._reading_order) - 1)

            await self._show_page()
        except Exception as e:
            logger.error(f"Error loading manifest: {e}")

    def next_page(self):
        if self._index < len(self._reading_order) - 1:
            self._index += 1
            asyncio.create_task(self._show_page())

    def prev_page(self):
        if self._index > 0:
            self._index -= 1
            asyncio.create_task(self._show_page())

    async def _show_page(self):
        if not self._reading_order: return
        
        idx = self._index
        total = len(self._reading_order)
        self.counter_label.setText(f"{idx + 1} / {total}")
        self.btn_prev.setEnabled(idx > 0)
        self.btn_next.setEnabled(idx < total - 1)

        item = self._reading_order[idx]
        href = item.get("href")
        base = self.api_client.profile.get_base_url()
        full_url = urljoin(base, href) if not href.startswith("http") else href
        
        asset_path = await self.image_manager.get_image_asset_path(full_url)
        
        if asset_path and idx == self._index:
            # Need absolute path for QPixmap
            from config import CACHE_DIR
            import hashlib
            url_hash = hashlib.sha256(full_url.encode("utf-8")).hexdigest()
            full_cache_path = CACHE_DIR / url_hash[:2] / url_hash
            
            if full_cache_path.exists():
                pixmap = QPixmap(str(full_cache_path))
                if not pixmap.isNull():
                    self.pixmap_item.setPixmap(pixmap)
                    self.scene.setSceneRect(self.pixmap_item.boundingRect())
                    self._fit_image()

        # Prefetch next 3
        for i in range(1, 4):
            nxt = idx + i
            if nxt < total:
                n_item = self._reading_order[nxt]
                n_href = n_item.get("href")
                n_full = urljoin(base, n_href) if not n_href.startswith("http") else n_href
                if n_full not in self._prefetch_set:
                    self._prefetch_set.add(n_full)
                    asyncio.create_task(self._prefetch_image(n_full))

        # Sync progression
        if self.progression_url and total > 0:
            pct = idx / total
            if idx == total - 1: pct = 1.0
            asyncio.create_task(self.progression_sync.update_progression(self.progression_url, pct, pct))

    def _fit_image(self):
        if self.pixmap_item.pixmap().isNull(): return
        self.view.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    async def _prefetch_image(self, url: str):
        try:
            await self.image_manager.get_image_b64(url)
        except: pass
        finally:
            self._prefetch_set.discard(url)
