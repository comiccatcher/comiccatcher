import asyncio
import traceback
import os
import time
import math
from typing import Optional, Dict, List
from urllib.parse import urljoin

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QFrame, QGridLayout, QLineEdit, QProgressBar, QGroupBox, QMenu
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QPixmap, QIcon, QKeyEvent, QWheelEvent

from config import ConfigManager
from api.client import APIClient
from api.opds_v2 import OPDS2Client
from api.image_manager import ImageManager
from api.progression import ProgressionSync
from models.opds import OPDSFeed, Group, Link, Publication
from logger import get_logger

logger = get_logger("ui.browser")

class PublicationCard(QFrame):
    clicked = pyqtSignal(object, str) # pub, self_url

    def __init__(self, pub: Publication, base_url: str, image_manager: ImageManager):
        super().__init__()
        self.pub = pub
        self.base_url = base_url
        self.image_manager = image_manager
        
        self.setFixedWidth(160)
        self.setFixedHeight(260)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("background-color: #222; border-radius: 5px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        self.cover_label = QLabel()
        self.cover_label.setFixedSize(150, 200)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setStyleSheet("background-color: #111; border-radius: 3px;")
        self.cover_label.setScaledContents(True)
        layout.addWidget(self.cover_label)

        self.title_label = QLabel(pub.metadata.title)
        self.title_label.setStyleSheet("font-size: 10px; color: white; border: none;")
        self.title_label.setWordWrap(True)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setFixedHeight(40)
        layout.addWidget(self.title_label)

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Determine self URL
        self.self_url = base_url
        for l in (pub.links or []):
            if l.rel == "self" or (isinstance(l.rel, list) and "self" in l.rel):
                self.self_url = urljoin(base_url, l.href)
                break

        # Start loading thumb
        img_url = pub.images[0].href if (pub.images and len(pub.images) > 0) else None
        if img_url:
            full_img_url = urljoin(base_url, img_url)
            asyncio.create_task(self._load_thumb(full_img_url))

    async def _load_thumb(self, url: str):
        asset_path = await self.image_manager.get_image_asset_path(url)
        if asset_path:
            from config import CACHE_DIR
            import hashlib
            url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
            full_path = CACHE_DIR / url_hash[:2] / url_hash
            if full_path.exists():
                pixmap = QPixmap(str(full_path))
                if not pixmap.isNull():
                    self.cover_label.setPixmap(pixmap)

    def mousePressEvent(self, event):
        self.clicked.emit(self.pub, self.self_url)
        super().mousePressEvent(event)

class PagingBar(QFrame):
    def __init__(self, on_navigate):
        super().__init__()
        self.on_navigate = on_navigate
        self.setFixedHeight(45)
        self.setStyleSheet("background-color: #2d2d2d; border-bottom: 1px solid #3e3e42;")
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(10, 0, 10, 0)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter) # Center the bar
        
        self.btn_first = QPushButton("<<")
        self.btn_prev = QPushButton("<")
        self.label_status = QLabel("Page 1")
        self.label_status.setStyleSheet("color: #ffffff; font-weight: bold; margin: 0 10px; font-size: 13px;")
        self.btn_next = QPushButton(">")
        self.btn_last = QPushButton(">>")
        
        button_style = """
            QPushButton {
                background-color: #3e3e42;
                color: #ffffff;
                border: 1px solid #454545;
                border-radius: 3px;
                padding: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #505050;
            }
            QPushButton:disabled {
                color: #666666;
                background-color: #2d2d2d;
            }
        """
        
        for b in [self.btn_first, self.btn_prev, self.btn_next, self.btn_last]:
            b.setFixedWidth(40)
            b.setStyleSheet(button_style)
            self.layout.addWidget(b)
            if b == self.btn_prev: self.layout.addWidget(self.label_status)
            
    def update_links(self, feed: OPDSFeed, base_url: str):
        def find_rel(rel_targets):
            if not isinstance(rel_targets, list): rel_targets = [rel_targets]
            # Check top-level links first
            for link in (feed.links or []):
                rel = link.rel
                rels = [rel] if isinstance(rel, str) else (rel or [])
                if any(t in rels or f"http://opds-spec.org/{t}" in rels for t in rel_targets):
                    return urljoin(base_url, link.href)
            # Some servers put them in navigation
            for link in (feed.navigation or []):
                rel = link.rel
                rels = [rel] if isinstance(rel, str) else (rel or [])
                if any(t in rels or f"http://opds-spec.org/{t}" in rels for t in rel_targets):
                    return urljoin(base_url, link.href)
            return None

        first = find_rel("first")
        prev = find_rel(["prev", "previous"])
        nxt = find_rel("next")
        last = find_rel("last")
        
        logger.debug(f"Paging links found - first: {bool(first)}, prev: {bool(prev)}, next: {bool(nxt)}, last: {bool(last)}")

        self.btn_first.setEnabled(bool(first))
        self.btn_prev.setEnabled(bool(prev))
        self.btn_next.setEnabled(bool(nxt))
        self.btn_last.setEnabled(bool(last))
        
        # Disconnect previous
        try: self.btn_first.clicked.disconnect()
        except: pass
        try: self.btn_prev.clicked.disconnect()
        except: pass
        try: self.btn_next.clicked.disconnect()
        except: pass
        try: self.btn_last.clicked.disconnect()
        except: pass
        
        # Pass replace=True to preserve current breadcrumb
        if first: self.btn_first.clicked.connect(lambda _, u=first: self.on_navigate(u, "Page 1", replace=True, keep_title=True))
        if prev: self.btn_prev.clicked.connect(lambda _, u=prev: self.on_navigate(u, "Prev Page", replace=True, keep_title=True))
        if nxt: self.btn_next.clicked.connect(lambda _, u=nxt: self.on_navigate(u, "Next Page", replace=True, keep_title=True))
        if last: self.btn_last.clicked.connect(lambda _, u=last: self.on_navigate(u, "Last Page", replace=True, keep_title=True))
        
        m = feed.metadata
        curr = getattr(m, "currentPage", None)
        total = getattr(m, "numberOfItems", None)
        per = getattr(m, "itemsPerPage", None)
        
        status = ""
        if curr is not None:
            # Detect 0-based vs 1-based
            display_curr = curr + 1 if curr == 0 or (total and curr < total/per and curr < 1) else curr
            if total and per and per > 0:
                pages = math.ceil(total/per)
                status = f"Page {display_curr} of {pages}"
            else:
                status = f"Page {display_curr}"
        
        self.label_status.setText(status)
        has_any = any([first, prev, nxt, last])
        self.setVisible(has_any)
        return has_any

class BrowserView(QWidget):
    def __init__(self, config_manager: ConfigManager, on_open_detail, on_navigate, on_offset_change=None):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.config_manager = config_manager
        self.on_open_detail_callback = on_open_detail
        self.on_navigate = on_navigate
        self.on_offset_change = on_offset_change
        
        self.api_client = None
        self.opds_client = None
        self.image_manager = None
        self._load_token = 0

        # Paging State
        self.items_buffer = []
        self.total_items = 0
        self.buffer_absolute_offset = 0
        self.next_url = None
        self.prev_url = None
        self.first_url = None
        self.last_url = None
        self.is_loading_more = False
        
        # Viewport State
        self.viewport_offset = 0
        self.items_per_screen = 10
        self.total_viewport_pages = 1
        self.is_pub_mode = False

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Header
        self.header_widget = QWidget()
        self.header = QHBoxLayout(self.header_widget)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #aaa; font-size: 11px;")
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search...")
        self.search_input.setVisible(False)
        
        self.btn_facets = QPushButton("Filters")
        self.btn_facets.setStyleSheet("background-color: #3e3e42; color: white; padding: 4px 8px; border-radius: 3px;")
        self.facet_menu = QMenu(self)
        self.btn_facets.setMenu(self.facet_menu)
        self.btn_facets.setVisible(False)
        
        self.header.addWidget(self.status_label)
        self.header.addStretch()
        self.header.addWidget(self.btn_facets)
        self.header.addWidget(self.search_input)
        self.layout.addWidget(self.header_widget)

        # Progress
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.layout.addWidget(self.progress)

        # Scroll Area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        self.content_container = QWidget()
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.scroll.setWidget(self.content_container)
        
        # Paging Bar (now at top)
        self.paging_bar = PagingBar(self.on_navigate)
        self.paging_bar.setVisible(False)
        self.paging_bar.setStyleSheet("background-color: #252526; border-bottom: 1px solid #333;")
        
        # Viewport Paging Bar (Alternative to standard paging)
        self.viewport_paging_bar = PagingBar(self.on_navigate) # Reuse class structure, logic overridden in methods
        self.viewport_paging_bar.setVisible(False)
        self.viewport_paging_bar.setStyleSheet("background-color: #1e3a5f; border-bottom: 1px solid #333;")

        self.layout.addWidget(self.header_widget)
        self.layout.addWidget(self.paging_bar)
        self.layout.addWidget(self.viewport_paging_bar)
        self.layout.addWidget(self.progress)
        self.layout.addWidget(self.scroll, 1)

    def keyPressEvent(self, event: QKeyEvent):
        method = self.config_manager.get_scroll_method()
        if method == "viewport":
            if event.key() == Qt.Key.Key_Right or event.key() == Qt.Key.Key_PageDown:
                self.next_viewport_screen()
            elif event.key() == Qt.Key.Key_Left or event.key() == Qt.Key.Key_PageUp:
                self.prev_viewport_screen()
            elif event.key() == Qt.Key.Key_Home:
                self.jump_to_absolute_first()
            elif event.key() == Qt.Key.Key_End:
                self.jump_to_absolute_last()
        super().keyPressEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        method = self.config_manager.get_scroll_method()
        if method == "viewport":
            if event.angleDelta().y() < 0:
                self.next_viewport_screen()
            else:
                self.prev_viewport_screen()
            event.accept()
        else:
            super().wheelEvent(event)

    def load_profile(self, profile):
        self.api_client = APIClient(profile)
        self.opds_client = OPDS2Client(self.api_client)
        self.image_manager = ImageManager(self.api_client)

    async def load_feed(self, url: str, title: str = None, force_refresh: bool = False, initial_offset: int = 0):
        self._load_token += 1
        token = self._load_token
        
        self.progress.setVisible(True)
        self.status_label.setText(f"Loading {title or 'Catalog'}...")
        
        # Clear existing content
        for i in reversed(range(self.content_layout.count())):
            item = self.content_layout.itemAt(i)
            if item.widget():
                item.widget().setParent(None)

        try:
            logger.debug(f"Fetching feed: {url}")
            feed = await self.opds_client.get_feed(url, force_refresh=force_refresh)
            if token != self._load_token: return
            
            logger.debug(f"Feed fetched: '{feed.metadata.title}'. Links: {len(feed.links or [])}, Groups: {len(feed.groups or [])}, Pubs: {len(feed.publications or [])}, Nav: {len(feed.navigation or [])}")
            
            self.status_label.setText(feed.metadata.title)
            
            method = self.config_manager.get_scroll_method()
            self.paging_bar.setVisible(False)
            self.viewport_paging_bar.setVisible(False)
            self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            
            # Reset viewport/infinite state
            self.viewport_offset = initial_offset
            self.items_buffer = []
            self.is_loading_more = False
            self.total_items = getattr(feed.metadata, 'numberOfItems', 0)
            
            # Calculate absolute offset of the first item in our buffer
            curr_page = getattr(feed.metadata, 'currentPage', 1)
            per_page = getattr(feed.metadata, 'itemsPerPage', 100)
            if curr_page == 0: # 0-based
                self.buffer_absolute_offset = 0
            else: # 1-based
                self.buffer_absolute_offset = (curr_page - 1) * per_page
            
            def find_rel(rel_targets):
                if not isinstance(rel_targets, list): rel_targets = [rel_targets]
                for link in (feed.links or []):
                    rel = link.rel
                    rels = [rel] if isinstance(rel, str) else (rel or [])
                    if any(t in rels or f"http://opds-spec.org/{t}" in rels for t in rel_targets):
                        return urljoin(url, link.href)
                return None

            self.next_url = find_rel("next")
            self.prev_url = find_rel(["prev", "previous"])
            self.first_url = find_rel("first")
            self.last_url = find_rel("last")
            
            # Decide rendering mode
            is_dashboard = any(bool(getattr(g, "publications", None)) for g in (feed.groups or []))
            has_pubs = bool(feed.publications)
            has_nav = bool(feed.navigation)
            self.is_pub_mode = has_pubs
            
            if is_dashboard:
                logger.debug("Rendering Dashboard")
                self._render_dashboard(feed)
            else:
                if has_pubs:
                    self.items_buffer.extend(feed.publications)
                elif has_nav:
                    self.items_buffer.extend([n for n in feed.navigation if n.title != "Start"])

                if method == "viewport":
                    logger.debug("Rendering Viewport")
                    self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                    self._render_viewport_screen()
                elif method == "infinite":
                    logger.debug("Rendering Infinite Scroll")
                    self._render_infinite_page(feed, append=False)
                else: # paging
                    logger.debug("Rendering Traditional Paging")
                    self.paging_bar.update_links(feed, url)
                    if has_pubs:
                        self._render_grid(feed.publications)
                        if has_nav:
                            self._render_navigation(feed.navigation, at_top=True)
                    elif has_nav:
                        self._render_navigation(feed.navigation)
                    else:
                        self.content_layout.addWidget(QLabel("This folder is empty."))
                
            self._setup_facets(feed)
                
        except Exception as e:
            logger.error(f"Feed error: {e}\n{traceback.format_exc()}")
            self.content_layout.addWidget(QLabel(f"Error loading feed: {e}"))
        finally:
            if token == self._load_token:
                self.progress.setVisible(False)

    def _setup_facets(self, feed: OPDSFeed):
        facet_groups = []
        if hasattr(feed, 'facets') and feed.facets:
            facet_groups.extend(feed.facets)
        if feed.groups:
            for group in feed.groups:
                if getattr(group, "navigation", None):
                    # Check if any navigation item has a "facet" relation
                    has_facet = False
                    for n in group.navigation:
                        rel_str = "".join(n.rel or []) if isinstance(n.rel, list) else (n.rel or "")
                        if "facet" in rel_str or "http://opds-spec.org/facet" in rel_str:
                            has_facet = True
                            break
                    if has_facet:
                        facet_groups.append(group)

        self.facet_menu.clear()
        if not facet_groups:
            self.btn_facets.setVisible(False)
            return

        self.btn_facets.setVisible(True)
        for group in facet_groups:
            is_dict = isinstance(group, dict)
            metadata = group.get("metadata") if is_dict else getattr(group, "metadata", None)
            title = "Filter"
            if metadata:
                title = metadata.get("title") if isinstance(metadata, dict) else getattr(metadata, "title", "Filter")
            
            # Add section header
            header_action = self.facet_menu.addAction(title)
            header_action.setEnabled(False)
            font = header_action.font()
            font.setBold(True)
            header_action.setFont(font)
            
            links = []
            if is_dict:
                links = group.get("navigation") or group.get("links") or []
            else:
                links = getattr(group, "navigation", None) or getattr(group, "links", None) or []
                
            for link in links:
                l_is_dict = isinstance(link, dict)
                l_title = link.get("title", "Option") if l_is_dict else getattr(link, "title", "Option")
                l_href = link.get("href") if l_is_dict else getattr(link, "href", None)
                
                if l_href:
                    action = self.facet_menu.addAction(f"  {l_title}")
                    url = urljoin(self.api_client.profile.get_base_url(), l_href)
                    # Using lambda with default args to correctly capture loop variables
                    action.triggered.connect(lambda checked, u=url, t=l_title: self.on_navigate(u, t, replace=True))
            
            self.facet_menu.addSeparator()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.config_manager.get_scroll_method() == "viewport" and self.items_buffer:
            # Re-render the current offset with the new capacity
            self._render_viewport_screen()

    def _render_viewport_screen(self):
        if not self.items_buffer: return
        
        self.content_layout.parentWidget().setUpdatesEnabled(False)
        # Clear existing
        for i in reversed(range(self.content_layout.count())):
            item = self.content_layout.itemAt(i)
            if item.widget(): item.widget().setParent(None)

        # Calculate capacity
        available_h = self.scroll.viewport().height()
        available_w = self.scroll.viewport().width()

        if self.is_pub_mode:
            # PublicationCard: 160x260. Grid spacing: 10.
            # We need (W + 10) per column, and we can fit (available_w + 10) total.
            cols = max(1, (available_w + 10) // 170)
            rows = max(1, (available_h + 10) // 270)
            self.items_per_screen = cols * rows
        else:
            # Navigation buttons: ~40px high.
            self.items_per_screen = max(1, available_h // 40)

        # Clamp offset to prevent empty screens after resize
        if self.viewport_offset >= len(self.items_buffer):
            self.viewport_offset = max(0, len(self.items_buffer) - self.items_per_screen)
        
        # Align offset to a multiple of items_per_screen to keep "pages" consistent
        if self.items_per_screen > 0:
            page_num = self.viewport_offset // self.items_per_screen
            self.viewport_offset = page_num * self.items_per_screen

        batch = self.items_buffer[self.viewport_offset : self.viewport_offset + self.items_per_screen]

        if self.is_pub_mode:
            self._render_grid(batch)
        else:
            self._render_navigation(batch)

        # Proactive fetch
        if self.viewport_offset + self.items_per_screen >= len(self.items_buffer) - self.items_per_screen:
            if self.next_url and not self.is_loading_more:
                asyncio.create_task(self._fetch_more_for_viewport())

        self._update_viewport_paging_bar()
        self.content_layout.parentWidget().setUpdatesEnabled(True)
        self.setFocus()

    def _update_viewport_paging_bar(self):
        # Calculate local total pages based on current BUFFER
        local_total_pages = math.ceil(len(self.items_buffer) / self.items_per_screen) if self.items_per_screen else 1
        
        # Calculate global total pages based on server metadata if available
        global_total_pages = math.ceil(self.total_items / self.items_per_screen) if (self.total_items and self.items_per_screen) else local_total_pages
        
        if global_total_pages <= 1:
            self.viewport_paging_bar.setVisible(False)
            return

        self.viewport_paging_bar.setVisible(True)
        
        # Calculate screen number relative to absolute server start
        if self.items_per_screen > 0:
            current_item_index = self.buffer_absolute_offset + self.viewport_offset
            current_page = (current_item_index // self.items_per_screen) + 1
        else:
            current_page = 1
        
        status_text = f"Screen {current_page} of {global_total_pages}"
        if self.is_loading_more:
            status_text += " (Loading...)"
        self.viewport_paging_bar.label_status.setText(status_text)
        
        self.viewport_paging_bar.btn_first.setEnabled(current_page > 1 or self.first_url is not None)
        self.viewport_paging_bar.btn_prev.setEnabled(current_page > 1 or self.prev_url is not None)
        self.viewport_paging_bar.btn_next.setEnabled(current_page < global_total_pages or self.next_url is not None)
        self.viewport_paging_bar.btn_last.setEnabled(current_page < global_total_pages or self.last_url is not None)
        
        # Disconnect old signals
        for b in [self.viewport_paging_bar.btn_first, self.viewport_paging_bar.btn_prev, 
                  self.viewport_paging_bar.btn_next, self.viewport_paging_bar.btn_last]:
            try: b.clicked.disconnect()
            except: pass
            
        self.viewport_paging_bar.btn_first.clicked.connect(lambda: self.jump_to_absolute_first() or self.setFocus())
        self.viewport_paging_bar.btn_prev.clicked.connect(lambda: self.prev_viewport_screen() or self.setFocus())
        self.viewport_paging_bar.btn_next.clicked.connect(lambda: self.next_viewport_screen() or self.setFocus())
        self.viewport_paging_bar.btn_last.clicked.connect(lambda: self.jump_to_absolute_last() or self.setFocus())

    def next_viewport_screen(self):
        if self.viewport_offset + self.items_per_screen < len(self.items_buffer):
            self.viewport_offset += self.items_per_screen
            if self.on_offset_change: self.on_offset_change(self.viewport_offset)
            self._render_viewport_screen()
        elif self.next_url and not self.is_loading_more:
            self.is_loading_more = True
            asyncio.create_task(self._fetch_more_for_viewport())

    async def _fetch_more_for_viewport(self):
        self.progress.setVisible(True)
        try:
            feed = await self.opds_client.get_feed(self.next_url)
            self._update_after_fetch(feed, self.next_url)
            
            if self.is_pub_mode:
                self.items_buffer.extend(feed.publications or [])
            else:
                self.items_buffer.extend([n for n in (feed.navigation or []) if n.title != "Start"])
                
            # Jump forward now that buffer is expanded
            self.viewport_offset += self.items_per_screen
            if self.on_offset_change: self.on_offset_change(self.viewport_offset)
            self._render_viewport_screen()
        except Exception as e:
            logger.error(f"Error fetching more for viewport: {e}")
        finally:
            self.is_loading_more = False
            self.progress.setVisible(False)

    def prev_viewport_screen(self):
        if self.viewport_offset > 0:
            self.viewport_offset = max(0, self.viewport_offset - self.items_per_screen)
            if self.on_offset_change: self.on_offset_change(self.viewport_offset)
            self._render_viewport_screen()
        elif self.prev_url and not self.is_loading_more:
            self.is_loading_more = True
            asyncio.create_task(self._fetch_prev_for_viewport())

    async def _fetch_prev_for_viewport(self):
        self.progress.setVisible(True)
        try:
            feed = await self.opds_client.get_feed(self.prev_url)
            self._update_after_fetch(feed, self.prev_url)
            
            new_items = feed.publications or [n for n in feed.navigation if n.title != "Start"]
            count = len(new_items)
            # Prepend to buffer
            self.items_buffer = new_items + self.items_buffer
            
            # Update absolute offset
            self.buffer_absolute_offset -= count
            if self.buffer_absolute_offset < 0: self.buffer_absolute_offset = 0
            
            # Adjust offset so we stay on the "same" items relative to the start
            self.viewport_offset += count
            # Now move back one screen
            self.viewport_offset = max(0, self.viewport_offset - self.items_per_screen)
            if self.on_offset_change: self.on_offset_change(self.viewport_offset)
            self._render_viewport_screen()
        except Exception as e:
            logger.error(f"Error fetching prev for viewport: {e}")
        finally:
            self.is_loading_more = False
            self.progress.setVisible(False)

    def jump_to_viewport_offset(self, offset):
        self.viewport_offset = max(0, min(offset, len(self.items_buffer) - self.items_per_screen))
        if self.on_offset_change: self.on_offset_change(self.viewport_offset)
        self._render_viewport_screen()

    def jump_to_absolute_first(self):
        if self.first_url:
            asyncio.create_task(self._fetch_absolute_first())
        else:
            self.jump_to_viewport_offset(0)

    async def _fetch_absolute_first(self):
        self.progress.setVisible(True)
        try:
            feed = await self.opds_client.get_feed(self.first_url)
            self.items_buffer = feed.publications or [n for n in feed.navigation if n.title != "Start"]
            self.viewport_offset = 0
            self.buffer_absolute_offset = 0 # It's the first page
            self._update_after_fetch(feed, self.first_url)
            self._render_viewport_screen()
        except Exception as e:
            logger.error(f"Error jumping to first: {e}")
        finally:
            self.progress.setVisible(False)

    def jump_to_absolute_last(self):
        if self.last_url:
            asyncio.create_task(self._fetch_absolute_last())
        else:
            self.jump_to_viewport_offset(len(self.items_buffer) - self.items_per_screen)

    async def _fetch_absolute_last(self):
        self.progress.setVisible(True)
        try:
            feed = await self.opds_client.get_feed(self.last_url)
            self.items_buffer = feed.publications or [n for n in feed.navigation if n.title != "Start"]
            
            # Update metadata
            self._update_after_fetch(feed, self.last_url)
            
            # Align viewport to the start of the last screen in this new buffer
            if self.items_per_screen > 0:
                # Find how many items are in the final partial screen
                remainder = len(self.items_buffer) % self.items_per_screen
                if remainder == 0:
                    self.viewport_offset = max(0, len(self.items_buffer) - self.items_per_screen)
                else:
                    self.viewport_offset = len(self.items_buffer) - remainder
            else:
                self.viewport_offset = 0
                
            self._render_viewport_screen()
        except Exception as e:
            logger.error(f"Error jumping to last: {e}")
        finally:
            self.progress.setVisible(False)

    def _update_after_fetch(self, feed, url):
        self.total_items = getattr(feed.metadata, 'numberOfItems', self.total_items)
        
        curr_page = getattr(feed.metadata, 'currentPage', 1)
        per_page = getattr(feed.metadata, 'itemsPerPage', 100)
        if curr_page == 0: # 0-based
            self.buffer_absolute_offset = 0
        else: # 1-based
            self.buffer_absolute_offset = (curr_page - 1) * per_page

        def find_rel(rel_targets):
            if not isinstance(rel_targets, list): rel_targets = [rel_targets]
            for link in (feed.links or []):
                rel = link.rel
                rels = [rel] if isinstance(rel, str) else (rel or [])
                if any(t in rels or f"http://opds-spec.org/{t}" in rels for t in rel_targets):
                    return urljoin(url, link.href)
            return None
        self.next_url = find_rel("next")
        self.prev_url = find_rel(["prev", "previous"])
        self.first_url = find_rel("first")
        self.last_url = find_rel("last")

    def _render_infinite_page(self, feed, append=False):
        pass

    def _render_dashboard(self, feed: OPDSFeed):
        self.paging_bar.setVisible(False)
        self.viewport_paging_bar.setVisible(False)
        if feed.navigation:
            self._render_navigation(feed.navigation)

        if feed.groups:
            for group in feed.groups:
                title = group.metadata.title if (hasattr(group, 'metadata') and group.metadata) else "Group"
                label = QLabel(title)
                label.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 10px;")
                self.content_layout.addWidget(label)
                
                if group.publications:
                    scroll = QScrollArea()
                    scroll.setFixedHeight(280)
                    scroll.setWidgetResizable(True)
                    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
                    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                    
                    inner = QWidget()
                    h_layout = QHBoxLayout(inner)
                    h_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
                    
                    for pub in group.publications:
                        card = PublicationCard(pub, self.api_client.profile.get_base_url(), self.image_manager)
                        card.clicked.connect(self.on_open_detail_callback)
                        h_layout.addWidget(card)
                    
                    scroll.setWidget(inner)
                    self.content_layout.addWidget(scroll)

    def _render_navigation(self, navigation: List[Link], at_top=False):
        nav_group = QGroupBox("Navigation")
        nav_layout = QVBoxLayout(nav_group)
        nav_layout.setSpacing(0)
        
        for n in navigation:
            if n.title == "Start": continue
            btn = QPushButton(n.title)
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("text-align: left; padding: 8px; border-bottom: 1px solid #333; color: #3791ef;")
            url = urljoin(self.api_client.profile.get_base_url(), n.href)
            btn.clicked.connect(lambda _, u=url, t=n.title: self.on_navigate(u, t))
            nav_layout.addWidget(btn)
            
        if at_top:
            self.content_layout.insertWidget(0, nav_group)
        else:
            self.content_layout.addWidget(nav_group)

    def _render_grid(self, publications: List[Publication]):
        grid_widget = QWidget()
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setSpacing(10)
        
        cols = 5
        for i, pub in enumerate(publications):
            card = PublicationCard(pub, self.api_client.profile.get_base_url(), self.image_manager)
            card.clicked.connect(self.on_open_detail_callback)
            grid_layout.addWidget(card, i // cols, i % cols)
            
        self.content_layout.addWidget(grid_widget)
