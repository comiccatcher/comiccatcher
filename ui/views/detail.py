import asyncio
import traceback
import uuid
from typing import List, Union, Any, Optional
from urllib.parse import urljoin

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QFrame, QProgressBar
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap

from logger import get_logger
from api.image_manager import ImageManager
from models.opds import Publication, Contributor, Link
from ui.image_data import TRANSPARENT_DATA_URL

logger = get_logger("ui.detail")

class ClickableBadge(QFrame):
    def __init__(self, text, on_click):
        super().__init__()
        self.on_click = on_click
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #333;
                border-radius: 10px;
                padding: 2px 10px;
            }
            QFrame:hover {
                background-color: #444;
            }
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        label = QLabel(text)
        label.setStyleSheet("color: #ddd; font-size: 11px; border: none;")
        layout.addWidget(label)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        self.on_click()
        super().mousePressEvent(event)

class DetailView(QWidget):
    def __init__(self, on_back, on_read, on_navigate, on_start_download, on_open_detail):
        super().__init__()
        self.on_back = on_back
        self.on_read = on_read
        self.on_navigate = on_navigate
        self.on_start_download = on_start_download
        self.on_open_detail = on_open_detail
        
        self.api_client = None
        self.opds_client = None
        self.image_manager = None
        
        self._current_pub = None
        self._current_base_url = None
        self._active_load_id = None

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)

        # Header
        self.header = QHBoxLayout()
        self.btn_back = QPushButton("Back")
        self.btn_back.clicked.connect(self.on_back)
        self.header.addWidget(self.btn_back)
        self.header.addStretch()
        self.layout.addLayout(self.header)

        # Progress
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.layout.addWidget(self.progress)

        # Main Scroll Area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.content_widget)
        self.layout.addWidget(self.scroll)

    def load_publication(self, pub: Publication, base_url: str, api_client, opds_client, image_manager, history=None, force_refresh: bool = False):
        self.api_client = api_client
        self.opds_client = opds_client
        self.image_manager = image_manager
        self._current_pub = pub
        self._current_base_url = base_url
        self._active_load_id = str(uuid.uuid4())
        
        self.progress.setVisible(True)
        self._render_details(pub, base_url)
        
        if not (pub.readingOrder and len(pub.readingOrder) > 0):
            asyncio.create_task(self._fetch_full_metadata(pub, base_url, self._active_load_id, force_refresh))
        else:
            self.progress.setVisible(False)

    async def _fetch_full_metadata(self, pub: Publication, base_url: str, load_id: str, force_refresh: bool = False):
        manifest_url = None
        for link in pub.links:
            if link.type in ["application/webpub+json", "application/divina+json"]:
                manifest_url = link.href
                break
        
        if manifest_url and load_id == self._active_load_id:
            try:
                full_url = urljoin(base_url, manifest_url)
                full_pub = await self.opds_client.get_publication(full_url, force_refresh=force_refresh)
                
                if load_id == self._active_load_id:
                    if not full_pub.images and pub.images: full_pub.images = pub.images
                    if not full_pub.metadata.description and pub.metadata.description: 
                        full_pub.metadata.description = pub.metadata.description
                    
                    self._current_pub = full_pub
                    self._render_details(full_pub, base_url)
            except Exception as e:
                logger.error(f"Error upgrading metadata: {e}")
        
        if load_id == self._active_load_id:
            self.progress.setVisible(False)

    def _render_details(self, pub: Publication, base_url: str):
        for i in reversed(range(self.content_layout.count())):
            item = self.content_layout.itemAt(i)
            if item.widget(): item.widget().setParent(None)

        m = pub.metadata
        top_layout = QHBoxLayout()
        
        # Cover
        cover_label = QLabel()
        cover_label.setFixedSize(300, 450)
        cover_label.setStyleSheet("background-color: #111; border: 1px solid #444;")
        cover_label.setScaledContents(True)
        top_layout.addWidget(cover_label, 0, Qt.AlignmentFlag.AlignTop)
        
        img_url = self._get_image_url(pub)
        if img_url:
            asyncio.create_task(self._load_cover(urljoin(base_url, img_url), cover_label))

        # Info Column
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(20, 0, 0, 0)
        
        title = QLabel(m.title)
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        title.setWordWrap(True)
        info_layout.addWidget(title)
        
        if m.subtitle:
            subtitle = QLabel(m.subtitle)
            subtitle.setStyleSheet("font-size: 16px; color: gray; font-style: italic;")
            info_layout.addWidget(subtitle)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_read = QPushButton("Read Now")
        btn_read.setStyleSheet("background-color: #2e7d32; color: white; padding: 10px; font-weight: bold;")
        manifest_url = next((urljoin(base_url, l.href) for l in pub.links if l.type in ["application/webpub+json", "application/divina+json"]), base_url)
        btn_read.clicked.connect(lambda: self.on_read(pub, manifest_url))
        btn_layout.addWidget(btn_read)
        
        download_url = next((urljoin(base_url, l.href) for l in pub.links if l.rel == "http://opds-spec.org/acquisition" or (l.type and "cbz" in l.type)), None)
        if download_url:
            btn_down = QPushButton("Download")
            btn_down.clicked.connect(lambda: self.on_start_download(pub, download_url))
            btn_layout.addWidget(btn_down)
        
        btn_layout.addStretch()
        info_layout.addLayout(btn_layout)

        # Hotlinks / Credits
        role_map = {
            "author": "Author", "artist": "Artist", "penciler": "Penciler", 
            "inker": "Inker", "colorist": "Colorist", "letterer": "Letterer", 
            "editor": "Editor", "publisher": "Publisher"
        }
        for attr, label in role_map.items():
            val = getattr(m, attr, None)
            if val:
                self._add_clickable_metadata(info_layout, label, val, base_url)

        if m.published:
            info_layout.addWidget(QLabel(f"<b>Published:</b> {m.published}"))
        
        # Subjects
        if m.subject:
            info_layout.addWidget(QLabel("<b>Subjects:</b>"))
            subj_layout = QHBoxLayout()
            subj_layout.setSpacing(5)
            subj_widget = QWidget()
            subj_widget.setLayout(subj_layout)
            subj_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
            
            subjects = m.subject if isinstance(m.subject, list) else [m.subject]
            for s in subjects:
                name = s.get("name") if isinstance(s, dict) else str(s)
                href = None
                links = s.get("links", []) if isinstance(s, dict) else []
                for l in links:
                    if "opds" in (l.get("type", "") if isinstance(l, dict) else getattr(l, 'type', '') or ""):
                        href = l.get("href") if isinstance(l, dict) else l.href
                        break
                
                if href:
                    full_href = urljoin(base_url, href)
                    badge = ClickableBadge(name, lambda u=full_href, t=name: self.on_navigate(u, t))
                    subj_layout.addWidget(badge)
                else:
                    l = QLabel(name)
                    l.setStyleSheet("background-color: #333; border-radius: 10px; padding: 2px 10px; font-size: 11px;")
                    subj_layout.addWidget(l)
            info_layout.addWidget(subj_widget)

        if m.description:
            info_layout.addWidget(QLabel("<b>Summary:</b>"))
            summary = QLabel(m.description)
            summary.setWordWrap(True)
            summary.setStyleSheet("color: #ccc; font-size: 13px;")
            info_layout.addWidget(summary)

        info_layout.addStretch()
        top_layout.addWidget(info_widget, 1)
        
        container = QWidget()
        container.setLayout(top_layout)
        self.content_layout.addWidget(container)

        # carousels
        self._add_carousels(pub, base_url)

    def _add_clickable_metadata(self, layout, label, contributors, base_url):
        items = contributors if isinstance(contributors, list) else [contributors]
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(5)
        
        l_label = QLabel(f"<b>{label}:</b>")
        l_label.setFixedWidth(80)
        row_layout.addWidget(l_label)
        
        flow_layout = QHBoxLayout()
        flow_layout.setSpacing(5)
        flow_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        for item in items:
            name = item.name if hasattr(item, 'name') else (item.get("name") if isinstance(item, dict) else str(item))
            href = None
            links = item.get("links", []) if isinstance(item, dict) else (getattr(item, 'links', []) or [])
            for l in links:
                l_type = l.get("type", "") if isinstance(l, dict) else getattr(l, 'type', '') or ""
                if "opds" in l_type:
                    href = l.get("href") if isinstance(l, dict) else l.href
                    break
            
            if href:
                full_href = urljoin(base_url, href)
                btn = QPushButton(name)
                btn.setFlat(True)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setStyleSheet("color: #3791ef; text-align: left; padding: 0; border: none; font-size: 13px;")
                btn.clicked.connect(lambda _, u=full_href, t=name: self.on_navigate(u, t))
                flow_layout.addWidget(btn)
            else:
                flow_layout.addWidget(QLabel(name))
        
        row_widget = QWidget()
        row_widget.setLayout(flow_layout)
        row_layout.addWidget(row_widget, 1)
        
        container = QWidget()
        container.setLayout(row_layout)
        layout.addWidget(container)

    def _add_carousels(self, pub: Publication, base_url: str):
        belongs_to = pub.metadata.belongsTo or pub.belongsTo
        if not belongs_to: return
        
        from ui.views.browser import PublicationCard
        
        for rel_type in ["series", "collection"]:
            items = belongs_to.get(rel_type, [])
            if not isinstance(items, list): items = [items]
            for item in items:
                links = item.get("links", [])
                for link in links:
                    l_href = link.get("href") if isinstance(link, dict) else getattr(link, 'href', None)
                    if not l_href: continue
                    
                    label_text = item.get("name") or rel_type.capitalize()
                    if rel_type == "series": label_text = f"More from {label_text}"
                    
                    header = QHBoxLayout()
                    l_title = QLabel(label_text)
                    l_title.setStyleSheet("font-size: 18px; font-weight: bold; margin-top: 20px;")
                    header.addWidget(l_title)
                    header.addStretch()
                    
                    btn_all = QPushButton("See All")
                    btn_all.setFlat(True)
                    btn_all.setStyleSheet("color: #3791ef; margin-top: 20px;")
                    full_href = urljoin(base_url, l_href)
                    btn_all.clicked.connect(lambda _, u=full_href, t=label_text: self.on_navigate(u, t))
                    header.addWidget(btn_all)
                    
                    self.content_layout.addLayout(header)
                    
                    # Async load carousel content
                    scroll = QScrollArea()
                    scroll.setFixedHeight(280)
                    scroll.setWidgetResizable(True)
                    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
                    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                    
                    inner = QWidget()
                    h_layout = QHBoxLayout(inner)
                    h_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
                    scroll.setWidget(inner)
                    self.content_layout.addWidget(scroll)
                    
                    asyncio.create_task(self._load_carousel_data(full_href, h_layout))

    async def _load_carousel_data(self, url, layout):
        try:
            from ui.views.browser import PublicationCard
            feed = await self.opds_client.get_feed(url)
            pubs = feed.publications or []
            if not pubs and feed.groups:
                for g in feed.groups:
                    if g.publications: pubs.extend(g.publications)
            
            if not pubs:
                layout.addWidget(QLabel("No items found."))
                return

            base_server_url = self.api_client.profile.get_base_url()
            for pub in pubs[:15]:
                card = PublicationCard(pub, base_server_url, self.image_manager)
                card.clicked.connect(self.on_open_detail)
                layout.addWidget(card)
        except Exception as e:
            logger.error(f"Carousel error: {e}")

    async def _load_cover(self, url: str, label: QLabel):
        asset_path = await self.image_manager.get_image_asset_path(url)
        if asset_path:
            from config import CACHE_DIR
            import hashlib
            url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
            full_path = CACHE_DIR / url_hash[:2] / url_hash
            if full_path.exists():
                pixmap = QPixmap(str(full_path))
                if not pixmap.isNull():
                    label.setPixmap(pixmap)

    def _get_image_url(self, pub: Publication) -> Optional[str]:
        if pub.images: return pub.images[0].href
        if pub.links:
            for link in pub.links:
                if "image" in (link.rel or "") or (link.type and "image/" in link.type):
                    return link.href
        return None

    def _format_contributors(self, val: Any) -> str:
        if not val: return ""
        if isinstance(val, str): return val
        if isinstance(val, list):
            names = []
            for item in val:
                if isinstance(item, str): names.append(item)
                elif hasattr(item, "name"): names.append(item.name)
                elif isinstance(item, dict): names.append(item.get("name", ""))
            return ", ".join(filter(None, names))
        if hasattr(val, "name"): return val.name
        if isinstance(val, dict): return val.get("name", str(val))
        return str(val)
