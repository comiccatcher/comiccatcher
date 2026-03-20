import asyncio
import traceback
import os
import time
import math
from typing import Optional, Dict, List
from urllib.parse import urljoin

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QFrame, QGridLayout, QLineEdit, QProgressBar, QGroupBox, QMenu, QComboBox
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QTimer
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
    selection_toggled = pyqtSignal(object, str, bool) # pub, key, is_selected
    download_requested = pyqtSignal(object, str) # pub, download_url

    def __init__(self, pub: Publication, base_url: str, image_manager: ImageManager):
        super().__init__()
        self.pub = pub
        self.base_url = base_url
        self.image_manager = image_manager
        
        self._selection_mode = False
        self._is_selected = False
        
        self.setFixedWidth(160)
        self.setFixedHeight(260)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("publication_card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        self.cover_label = QLabel(pub.metadata.title)
        self.cover_label.setFixedSize(150, 200)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setWordWrap(True)
        self.cover_label.setStyleSheet("""
            background-color: rgba(0, 0, 0, 40); 
            border-radius: 3px; 
            font-size: 11px; 
            padding: 10px;
        """)
        self.cover_label.setScaledContents(True)
        self.cover_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self.cover_label)

        self.title_label = QLabel(pub.metadata.title)
        self.title_label.setStyleSheet("font-size: 10px; border: none;")
        self.title_label.setWordWrap(True)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setFixedHeight(40)
        self.title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self.title_label)

        # Selection overlay
        self.selection_overlay = QLabel(self)
        self.selection_overlay.setFixedSize(160, 260)
        
        # We use a theme-aware accent color by relying on the global stylesheet
        self.selection_overlay.setObjectName("selection_overlay")
        self.selection_overlay.setStyleSheet("background-color: rgba(0, 122, 204, 100); border: 4px solid #007acc; border-radius: 5px;")
        self.selection_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.selection_overlay.hide()

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        
        # Determine a unique identity key for this publication

        # Prefer the 'self' URL if available, but fall back to identifier or title hash
        self.self_url = None
        for l in (pub.links or []):
            if l.rel == "self" or (isinstance(l.rel, list) and "self" in l.rel):
                self.self_url = urljoin(base_url, l.href)
                break
        
        if self.self_url:
            self.identity_key = self.self_url
        elif pub.identifier:
            self.identity_key = pub.identifier
        else:
            # Fallback to title hash to ensure uniqueness in the grid
            import hashlib
            raw = f"{pub.metadata.title}{base_url}"
            self.identity_key = hashlib.md5(raw.encode()).hexdigest()

        # Start loading thumb
        img_url = pub.images[0].href if (pub.images and len(pub.images) > 0) else None
        if img_url:
            full_img_url = urljoin(base_url, img_url)
            # Try to load from cache synchronously to avoid flash
            cache_path = self.image_manager._get_cache_path(full_img_url)
            if cache_path.exists():
                pixmap = QPixmap(str(cache_path))
                if not pixmap.isNull():
                    self.cover_label.setText("")
                    self.cover_label.setPixmap(pixmap)
                else:
                    asyncio.create_task(self._load_thumb(full_img_url))
            else:
                asyncio.create_task(self._load_thumb(full_img_url))

    async def _load_thumb(self, url: str):
        await self.image_manager.get_image_b64(url)

        # Check if the widget still exists before continuing
        try:
            if not self.cover_label: return
        except RuntimeError:
            return

        full_path = self.image_manager._get_cache_path(url)
        if full_path.exists():
            pixmap = QPixmap(str(full_path))
            if not pixmap.isNull():
                try:
                    self.cover_label.setText("")  # Clear the title fallback
                    self.cover_label.setPixmap(pixmap)
                except RuntimeError:
                    pass  # Widget was deleted while we were processing the pixmap

    def set_selection_mode(self, enabled: bool):
        self._selection_mode = enabled
        if not enabled:
            self.set_selected(False)

    def set_selected(self, selected: bool):
        self._is_selected = selected
        self.selection_overlay.setVisible(selected)

    def mousePressEvent(self, event):
        if self._selection_mode:
            self.set_selected(not self._is_selected)
            self.selection_toggled.emit(self.pub, self.identity_key, self._is_selected)
        else:
            # Use self.self_url (or identity_key if None) for navigation
            self.clicked.emit(self.pub, self.self_url or self.identity_key)
        super().mousePressEvent(event)

    def _on_context_menu(self, pos):
        from PyQt6.QtWidgets import QMenu
        download_url = next(
            (urljoin(self.base_url, l.href) 
             for l in (self.pub.links or [])
             if l.rel == "http://opds-spec.org/acquisition" or (l.type and "cbz" in l.type)), 
            None
        )
        if download_url:
            menu = QMenu(self)
            action_download = menu.addAction("Download")
            action = menu.exec(self.mapToGlobal(pos))
            if action == action_download:
                self.download_requested.emit(self.pub, download_url)

class PagingBar(QFrame):
    def __init__(self, on_navigate):
        super().__init__()
        self.on_navigate = on_navigate
        self.setFixedHeight(45)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(10, 0, 10, 0)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignLeft) # Left-justify the bar
        
        self.btn_first = QPushButton("<<")
        self.btn_prev = QPushButton("<")
        self.label_status = QLabel("Page 1")
        self.label_status.setStyleSheet("font-weight: bold; margin: 0 10px; font-size: 13px;")
        self.btn_next = QPushButton(">")
        self.btn_last = QPushButton(">>")
        
        for b in [self.btn_first, self.btn_prev, self.btn_next, self.btn_last]:
            b.setFixedWidth(40)
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
    def __init__(self, config_manager: ConfigManager, on_open_detail, on_navigate, on_start_download, on_offset_change=None):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.config_manager = config_manager
        self.on_open_detail_callback = on_open_detail
        self.on_navigate = on_navigate
        self.on_start_download = on_start_download
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
        
        # ReFit State
        self.refit_offset = 0
        self.items_per_screen = 10
        self.total_refit_pages = 1
        self.is_pub_mode = False
        self._server_index_base = None

        # Continuous Mode state
        self.sparse_buffer = {} # global_index -> item
        self._last_cols = 1
        self._scroll_debounce = QTimer()
        self._scroll_debounce.setSingleShot(True)
        self._scroll_debounce.setInterval(300)
        self._scroll_debounce.timeout.connect(self._on_scroll_settled)
        self._rendered_widgets = {} # global_index -> QWidget
        self._is_updating_continuous = False

        # Selection State
        self._selection_mode = False
        self._selected_items = set() # Set of self_urls
        self._selected_pubs = {} # self_url -> pub object

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Header
        self.header_widget = QWidget()
        self.header = QHBoxLayout(self.header_widget)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 11px;")
        
        self.btn_select = QPushButton("Select")
        self.btn_select.setCheckable(True)
        self.btn_select.clicked.connect(self.toggle_selection_mode)
        self.btn_select.setVisible(False) # Only visible when publications are loaded
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search...")
        self.search_input.setVisible(False)
        
        self.btn_facets = QPushButton("Filters")
        self.facet_menu = QMenu(self)
        self.btn_facets.setMenu(self.facet_menu)
        self.btn_facets.setVisible(False)
        
        self.paging_mode_combo = QComboBox()
        self.paging_mode_combo.addItems(["ReFit Mode", "Continuous Mode", "Traditional"])
        current_method = self.config_manager.get_scroll_method()
        if current_method == "continuous":
            self.paging_mode_combo.setCurrentText("Continuous Mode")
        elif current_method == "paging":
            self.paging_mode_combo.setCurrentText("Traditional")
        else:
            self.paging_mode_combo.setCurrentText("ReFit Mode")
            
        self.paging_mode_combo.currentTextChanged.connect(self._on_paging_mode_changed)
        
        self.header.addWidget(self.status_label)
        self.header.addStretch()
        self.header.addWidget(self.btn_select)
        self.header.addWidget(self.paging_mode_combo)
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
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll_event)
        
        self.content_container = QWidget()
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.scroll.setWidget(self.content_container)
        
        # Paging Bar Container (to reserve space and prevent ReFit jumps)
        self.paging_container = QFrame()
        self.paging_container.setFixedHeight(45)
        self.paging_container_layout = QVBoxLayout(self.paging_container)
        self.paging_container_layout.setContentsMargins(0, 0, 0, 0)
        self.paging_container_layout.setSpacing(0)
        
        # Paging Bar
        self.paging_bar = PagingBar(self.on_navigate)
        self.paging_bar.setVisible(False)
        self.paging_bar.setObjectName("top_header")
        
        # ReFit Paging Bar
        self.refit_paging_bar = PagingBar(self.on_navigate)
        self.refit_paging_bar.setVisible(False)
        self.refit_paging_bar.setObjectName("top_header")

        self.paging_container_layout.addWidget(self.paging_bar)
        self.paging_container_layout.addWidget(self.refit_paging_bar)

        self.layout.addWidget(self.header_widget)
        self.layout.addWidget(self.paging_container)
        self.layout.addWidget(self.scroll, 1)

        # Selection Action Bar
        self.selection_bar = QWidget()
        self.selection_bar.setObjectName("top_header") # reuse top_header styling for now
        self.selection_bar.setFixedHeight(50)
        sel_layout = QHBoxLayout(self.selection_bar)
        
        self.btn_sel_cancel = QPushButton("Cancel")
        self.btn_sel_cancel.clicked.connect(lambda: self.toggle_selection_mode(False))
        self.label_sel_count = QLabel("0 items selected")
        self.label_sel_count.setStyleSheet("font-weight: bold;")
        self.btn_sel_action = QPushButton("Download Selected")
        self.btn_sel_action.setObjectName("primary_button")
        self.btn_sel_action.clicked.connect(self._on_bulk_download)
        self.btn_sel_action.setEnabled(False)
        
        sel_layout.addWidget(self.btn_sel_cancel)
        sel_layout.addStretch()
        sel_layout.addWidget(self.label_sel_count)
        sel_layout.addStretch()
        sel_layout.addWidget(self.btn_sel_action)
        
        self.selection_bar.setVisible(False)
        self.layout.addWidget(self.selection_bar)

        # Progress (Floating Overlay)
        self.progress = QProgressBar(self)
        self.progress.setFixedHeight(3)
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 0)
        self.progress.setStyleSheet("QProgressBar { background: transparent; border: none; }")
        self.progress.setVisible(False)

    def toggle_selection_mode(self, enabled: Optional[bool] = None):
        if enabled is None:
            enabled = not self._selection_mode
            
        self._selection_mode = enabled
        self.btn_select.setChecked(enabled)
        self.btn_select.setText("Done" if enabled else "Select")
        self.selection_bar.setVisible(enabled)
        
        if not enabled:
            self._selected_items.clear()
            self._selected_pubs.clear()
            self._update_selection_ui()
            
        # Update all visible cards
        # We need to traverse the layout to find all PublicationCards
        def update_cards(widget):
            if isinstance(widget, PublicationCard):
                widget.set_selection_mode(enabled)
                if enabled and widget.identity_key in self._selected_items:
                    widget.set_selected(True)
            
            # Recurse into children
            if hasattr(widget, "layout") and widget.layout() is not None:
                for i in range(widget.layout().count()):
                    item = widget.layout().itemAt(i)
                    if item.widget():
                        update_cards(item.widget())
            
            # Handle QScrollArea specifically
            if isinstance(widget, QScrollArea) and widget.widget():
                update_cards(widget.widget())
                        
        update_cards(self.content_container)

    def _on_card_selection_toggled(self, pub, key, is_selected):
        if is_selected:
            self._selected_items.add(key)
            self._selected_pubs[key] = pub
        else:
            self._selected_items.discard(key)
            if key in self._selected_pubs:
                del self._selected_pubs[key]
                
        self._update_selection_ui()
        
    def _update_selection_ui(self):
        count = len(self._selected_items)
        self.label_sel_count.setText(f"{count} item{'s' if count != 1 else ''} selected")
        self.btn_sel_action.setEnabled(count > 0)
        self.btn_sel_action.setText(f"Download {count} Item{'s' if count != 1 else ''}")

    def _on_bulk_download(self):
        from PyQt6.QtWidgets import QMessageBox
        count = len(self._selected_items)
        if count == 0: return
        
        reply = QMessageBox.question(
            self, "Confirm Bulk Download",
            f"Are you sure you want to download {count} publication{'s' if count != 1 else ''}?\nThis will be done sequentially.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            items = list(self._selected_pubs.values())
            self.toggle_selection_mode(False)
            asyncio.create_task(self._process_bulk_download(items))

    async def _process_bulk_download(self, pubs):
        if not self.on_start_download:
            self.status_label.setText("Error: Download manager not connected.")
            return

        queued_count = 0
        total_pubs = len(pubs)
        logger.info(f"Starting bulk download processing for {total_pubs} items")
        
        for i, pub in enumerate(pubs):
            # Check for existing acquisition link in the summary
            download_url = self._find_acquisition_link(pub)
            
            # If missing, try fetching the full manifest
            if not download_url:
                logger.info(f"Acquisition link missing in summary for '{pub.metadata.title}', fetching full manifest...")
                self.status_label.setText(f"Fetching manifest {i+1}/{total_pubs}: {pub.metadata.title}...")
                
                # Robust self-link detection
                self_url = None
                for l in (pub.links or []):
                    rel_list = [l.rel] if isinstance(l.rel, str) else (l.rel or [])
                    if any(r == "self" or r == "http://opds-spec.org/self" for r in rel_list):
                        self_url = urljoin(self.api_client.profile.get_base_url(), l.href)
                        break
                
                if self_url:
                    try:
                        # Fetch manifest with caching
                        full_pub = await self.opds_client.get_publication(self_url)
                        download_url = self._find_acquisition_link(full_pub)
                        if download_url:
                            logger.info(f"Found acquisition link in full manifest for '{pub.metadata.title}'")
                        else:
                            logger.warning(f"Manifest fetched but still no acquisition link for '{pub.metadata.title}'")
                    except Exception as e:
                        logger.error(f"Failed to fetch manifest for {pub.metadata.title} from {self_url}: {e}")
                else:
                    logger.warning(f"No 'self' link found in summary for '{pub.metadata.title}', cannot fetch manifest.")
            
            if download_url:
                logger.info(f"Queuing bulk download for '{pub.metadata.title}': {download_url}")
                self.status_label.setText(f"Queued {queued_count+1}/{total_pubs}: {pub.metadata.title}...")
                self.on_start_download(pub, download_url)
                queued_count += 1
                await asyncio.sleep(0.05) # Small stagger
            else:
                logger.warning(f"No download URL found for '{pub.metadata.title}' after all checks. Links: {[l.rel for l in (pub.links or [])]}")

        if queued_count == 0:
            self.status_label.setText(f"Failed to queue any items. Check logs.")
        else:
            self.status_label.setText(f"Successfully queued {queued_count} item{'s' if queued_count != 1 else ''}.")
            
        # Auto-exit selection mode after bulk action
        QTimer.singleShot(2500, lambda: self.toggle_selection_mode(False))

    def _find_acquisition_link(self, pub):
        """Helper to find an acquisition link in a publication or its manifest."""
        for l in (pub.links or []):
            # Normalize rels to a list of lower-case strings
            rels = l.rel
            if isinstance(rels, str):
                rel_list = [rels.lower()]
            elif isinstance(rels, list):
                rel_list = [str(r).lower() for r in rels]
            else:
                rel_list = []
                
            # Aggressive check for acquisition rels
            is_acq = any("acquisition" in r for r in rel_list)
            
            # Type-based detection (CBZ, CBR, PDF, EPUB, etc.)
            l_type = (l.type or "").lower()
            l_href = (l.href or "").lower()
            is_comic = any(t in l_type for t in ["cbz", "cbr", "cb7", "pdf", "octet-stream"]) or \
                       any(l_href.endswith(ext) for ext in [".cbz", ".cbr", ".cb7", ".pdf"])
            
            # If it's explicitly an acquisition link, or looks like a comic file, take it
            if is_acq or is_comic:
                # Avoid links that are clearly not downloads (like search, self, etc. if mislabeled)
                if any(r in rel_list for r in ["self", "search", "alternate"]) and not is_acq:
                    continue
                return urljoin(self.api_client.profile.get_base_url(), l.href)
        return None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Position progress bar at the top of the scroll area
        y = self.header_widget.y() + self.header_widget.height()
        if self.paging_container.isVisible():
            y = max(y, self.paging_container.y() + self.paging_container.height())
        self.progress.setGeometry(0, y, self.width(), 3)
        
        method = self.config_manager.get_scroll_method()
        if method == "refit" and self.items_buffer:
            # Re-render current offset with new capacity
            self._render_refit_screen()
        elif method == "continuous" and self.sparse_buffer:
            # Recalculate layout for continuous mode
            available_w = self.scroll.viewport().width() - 20
            self._last_cols = max(1, available_w // 175) if self.is_pub_mode else 1
            self.content_container.setFixedWidth(self.scroll.viewport().width())
            self._resize_continuous_canvas()
            self._sync_continuous_view()
            asyncio.create_task(self._update_continuous_data())

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape and self._selection_mode:
            self.toggle_selection_mode(False)
            return

        method = self.config_manager.get_scroll_method()
        if method == "refit":
            if event.key() == Qt.Key.Key_Right or event.key() == Qt.Key.Key_PageDown:
                self.next_refit_screen()
            elif event.key() == Qt.Key.Key_Left or event.key() == Qt.Key.Key_PageUp:
                self.prev_refit_screen()
            elif event.key() == Qt.Key.Key_Home:
                self.jump_to_absolute_first()
            elif event.key() == Qt.Key.Key_End:
                self.jump_to_absolute_last()
        super().keyPressEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        method = self.config_manager.get_scroll_method()
        if method == "refit":
            if event.angleDelta().y() < 0:
                self.next_refit_screen()
            else:
                self.prev_refit_screen()
            event.accept()
        else:
            super().wheelEvent(event)

    def _on_paging_mode_changed(self, text):
        method = "refit"
        if text == "Continuous Mode":
            method = "continuous"
        elif text == "Traditional":
            method = "paging"
            
        self.config_manager.settings["scroll_method"] = method
        self.config_manager.save_settings()
        
        # Clear UI before reload
        self._clear_all_content()
        
        # Trigger reload of current URL if available
        if hasattr(self, '_last_loaded_url') and self._last_loaded_url:
            asyncio.create_task(self.load_feed(self._last_loaded_url, force_refresh=True))

    def set_feed_context(self, profile):
        self.api_client = APIClient(profile)
        self.opds_client = OPDS2Client(self.api_client)
        self.image_manager = ImageManager(self.api_client)

    async def load_feed(self, url: str, title: str = None, force_refresh: bool = False, initial_offset: int = 0):
        self._load_token += 1
        token = self._load_token
        self._last_loaded_url = url
        
        self.progress.setVisible(True)
        self.status_label.setText(f"Loading {title or 'Catalog'}...")
        
        # Clear existing content completely
        self._clear_all_content()

        try:
            logger.debug(f"Fetching feed: {url}")
            feed = await self.opds_client.get_feed(url, force_refresh=force_refresh)
            if token != self._load_token: return
            
            logger.debug(f"Feed fetched: '{feed.metadata.title}'. Links: {len(feed.links or [])}, Groups: {len(feed.groups or [])}, Pubs: {len(feed.publications or [])}, Nav: {len(feed.navigation or [])}")
            
            self.status_label.setText(feed.metadata.title)
            
            method = self.config_manager.get_scroll_method()
            self.paging_bar.setVisible(False)
            self.refit_paging_bar.setVisible(False)
            self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            
            # Reset refit/continuous state
            self.refit_offset = initial_offset
            self.items_buffer = []
            self.sparse_buffer = {}
            # (Note: widgets cleared in _clear_all_content)
            
            # CRITICAL: Reset container sizing from continuous mode
            self.content_container.setMinimumHeight(0)
            self.content_container.setMaximumHeight(16777215)
            self.content_container.setFixedWidth(16777215)
            
            self.is_loading_more = False
            self._server_index_base = None
            
            # Unified update logic
            self._update_after_fetch(feed, url, reset_offset=True)
            
            # Decide rendering mode
            is_dashboard = any(bool(getattr(g, "publications", None)) for g in (feed.groups or []))
            has_pubs = bool(feed.publications)
            has_nav = bool(feed.navigation)
            self.is_pub_mode = has_pubs
            
            if is_dashboard or has_pubs:
                self.btn_select.setVisible(True)
            else:
                self.btn_select.setVisible(False)
            
            if is_dashboard:
                logger.debug("Rendering Dashboard")
                self._render_dashboard(feed)
            else:
                if has_pubs:
                    self.items_buffer.extend(feed.publications)
                elif has_nav:
                    self.items_buffer.extend([n for n in feed.navigation if n.title != "Start"])

                if method == "refit":
                    logger.debug("Rendering ReFit Mode")
                    self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                    # Small delay to let UI settle for capacity calculation
                    QTimer.singleShot(50, self._render_refit_screen)
                elif method == "continuous":
                    logger.debug("Rendering Continuous Mode")
                    self._render_continuous_page(feed, append=False)
                else: # paging
                    logger.debug("Rendering Traditional Paging")
                    has_paging = self.paging_bar.update_links(feed, url)
                    self.refit_paging_bar.setVisible(False)
                    if has_paging:
                        self.paging_container.setVisible(True)
                        self.paging_bar.setVisible(True)
                    else:
                        self.paging_container.setVisible(False)
                        self.paging_bar.setVisible(False)
                        
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

    def _clear_all_content(self):
        self.toggle_selection_mode(False)
        
        # 1. Clear layout
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        
        # 2. Clear absolute positioned widgets
        for w in list(self._rendered_widgets.values()):
            w.hide()
            w.deleteLater()
        self._rendered_widgets = {}
        
        # 3. Final safety: check for any orphans on the container
        for child in list(self.content_container.children()):
            if isinstance(child, QWidget) and child != self.content_layout.parentWidget():
                # We check if it's NOT the container widget that holds the layout
                # Actually self.content_container IS the parent widget.
                # The content_layout's items were cleared above.
                # We want to clear everything EXCEPT the layout itself.
                if child.layout() is None: # Layout-managed widgets usually have parents
                    child.hide()
                    child.deleteLater()

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

    def _render_refit_screen(self):
        if not self.items_buffer: return
        
        self.content_layout.parentWidget().setUpdatesEnabled(False)
        # Clear existing
        for i in reversed(range(self.content_layout.count())):
            layout_item = self.content_layout.takeAt(i)
            if layout_item.widget():
                layout_item.widget().deleteLater()

        # Calculate capacity with safety margins (20px padding)
        available_h = self.scroll.viewport().height() - 20
        available_w = self.scroll.viewport().width() - 20
        
        self._last_rows = 1
        self._last_cols = 1

        if self.is_pub_mode:
            # PublicationCard: 160x260. Grid spacing: 10.
            self._last_cols = max(1, available_w // 175)
            self._last_rows = max(1, available_h // 275)
            self.items_per_screen = self._last_cols * self._last_rows
        else:
            # Navigation buttons: ~40px high.
            self._last_rows = max(1, available_h // 45)
            self._last_cols = 1
            self.items_per_screen = self._last_rows

        # Simplified Clamping: 
        # Only prevent scrolling past the actual end of our items.
        # We ALLOW the ReFit mode to show a partial screen at the very end.
        max_allowed_offset = len(self.items_buffer) - 1
        if self.refit_offset > max_allowed_offset:
            self.refit_offset = max(0, max_allowed_offset)
        
        # Align offset to a multiple of items_per_screen to keep "pages" consistent RELATIVE TO GLOBAL START
        if self.items_per_screen > 0:
            current_abs_idx = self.buffer_absolute_offset + self.refit_offset
            page_num = current_abs_idx // self.items_per_screen
            snapped_abs_idx = page_num * self.items_per_screen
            
            # Map snapped global index back to local buffer offset
            self.refit_offset = snapped_abs_idx - self.buffer_absolute_offset
            
            # Final boundary check: don't snap outside the buffer
            self.refit_offset = max(0, min(self.refit_offset, len(self.items_buffer) - 1))

        batch = self.items_buffer[self.refit_offset : self.refit_offset + self.items_per_screen]

        if self.is_pub_mode:
            self._render_grid(batch)
        else:
            self._render_navigation(batch)

        # Proactive/Aggressive fetch (Bidirectional)
        if not self.is_loading_more:
            per_page = 50
            if hasattr(self, '_last_feed_metadata'):
                per_page = getattr(self._last_feed_metadata, "itemsPerPage", 50) or 50

            # Forward pre-fetch: if buffer is small or near the end
            if self.next_url:
                near_end_next = self.refit_offset + self.items_per_screen >= len(self.items_buffer) - self.items_per_screen
                is_small_buffer_next = len(self.items_buffer) < (per_page * 1.5)
                if near_end_next or is_small_buffer_next:
                    asyncio.create_task(self._fetch_more_for_refit(jump=near_end_next))
            
            # Backward pre-fetch: if we have a prev link and buffer is small or near the start
            # (only if not already loading forward)
            if self.prev_url and not self.is_loading_more:
                near_start_prev = self.refit_offset < self.items_per_screen
                is_small_buffer_prev = len(self.items_buffer) < (per_page * 1.5)
                if near_start_prev or is_small_buffer_prev:
                    asyncio.create_task(self._fetch_prev_for_refit(jump=False))

        self._update_refit_paging_bar()
        self.content_layout.parentWidget().setUpdatesEnabled(True)
        self.setFocus()

    def _update_refit_paging_bar(self):
        # Calculate local total pages based on current BUFFER
        local_total_pages = math.ceil(len(self.items_buffer) / self.items_per_screen) if self.items_per_screen else 1
        
        # Calculate global total pages based on server metadata if available
        global_total_pages = math.ceil(self.total_items / self.items_per_screen) if (self.total_items and self.items_per_screen) else local_total_pages
        
        if global_total_pages <= 1:
            self.refit_paging_bar.setVisible(False)
            return

        self.refit_paging_bar.setVisible(True)
        
        # Calculate screen number relative to absolute server start
        if self.items_per_screen > 0:
            current_item_index = self.buffer_absolute_offset + self.refit_offset
            current_page = (current_item_index // self.items_per_screen) + 1
        else:
            current_page = 1
            
        # Clamp to avoid Screen 163 of 160
        current_page = min(current_page, global_total_pages)
        
        status_text = f"Screen {current_page} of {global_total_pages}"
        # Only show Loading... if the current screen is actually empty or we are in a hard-wait state
        if self.is_loading_more and len(self.items_buffer) == 0:
            status_text += " (Loading...)"
            
        self.refit_paging_bar.label_status.setText(status_text)
        
        if global_total_pages <= 1:
            self.refit_paging_bar.setVisible(False)
            self.paging_container.setVisible(False)
            return

        self.paging_container.setVisible(True)
        self.refit_paging_bar.setVisible(True)
        self.paging_bar.setVisible(False)
        self.refit_paging_bar.btn_first.setEnabled(current_page > 1 or self.first_url is not None)
        self.refit_paging_bar.btn_prev.setEnabled(current_page > 1 or self.prev_url is not None)
        self.refit_paging_bar.btn_next.setEnabled(current_page < global_total_pages or self.next_url is not None)
        self.refit_paging_bar.btn_last.setEnabled(current_page < global_total_pages or self.last_url is not None)
        
        # Explicit Logging
        b_f = 1 if self.refit_paging_bar.btn_first.isEnabled() else 0
        b_p = 1 if self.refit_paging_bar.btn_prev.isEnabled() else 0
        b_n = 1 if self.refit_paging_bar.btn_next.isEnabled() else 0
        b_l = 1 if self.refit_paging_bar.btn_last.isEnabled() else 0
        
        h = self.scroll.viewport().height()
        w = self.scroll.viewport().width()
        
        # Calculate server page overlap if possible
        server_pg = "N/A"
        server_per = "N/A"
        if hasattr(self, '_last_feed_metadata') and self._last_feed_metadata:
            c = getattr(self._last_feed_metadata, "currentPage", None)
            p = getattr(self._last_feed_metadata, "itemsPerPage", None)
            if c is not None:
                server_pg = str(c + (1 if getattr(self, '_server_index_base', 0) == 1 else 0))
            if p is not None:
                server_per = str(p)
        
        mode_str = "PUB" if self.is_pub_mode else "NAV"
        grid_str = f"{self._last_rows}x{self._last_cols}"
        logger.debug(f"ReFitNav | {mode_str} | state:[F:{b_f} P:{b_p} N:{b_n} L:{b_l}] | label:'{status_text}' | ctx:[svr_items:{self.total_items}, svr_pg:{server_pg}, svr_per:{server_per}, virt_pg:{current_page}, buf_size:{len(self.items_buffer)}, abs_offset:{self.buffer_absolute_offset}] | UI:[h:{h}, w:{w}, grid:{grid_str} ({self.items_per_screen}/scr)]")

        # Disconnect old signals
        for b in [self.refit_paging_bar.btn_first, self.refit_paging_bar.btn_prev, 
                  self.refit_paging_bar.btn_next, self.refit_paging_bar.btn_last]:
            try: b.clicked.disconnect()
            except: pass
            
        self.refit_paging_bar.btn_first.clicked.connect(lambda: self.jump_to_absolute_first() or self.setFocus())
        self.refit_paging_bar.btn_prev.clicked.connect(lambda: self.prev_refit_screen() or self.setFocus())
        self.refit_paging_bar.btn_next.clicked.connect(lambda: self.next_refit_screen() or self.setFocus())
        self.refit_paging_bar.btn_last.clicked.connect(lambda: self.jump_to_absolute_last() or self.setFocus())

    def next_refit_screen(self):
        logger.debug("User clicked ReFit Next Screen")
        if self.refit_offset + self.items_per_screen < len(self.items_buffer):
            self.refit_offset += self.items_per_screen
            if self.on_offset_change: self.on_offset_change(self.refit_offset)
            self._render_refit_screen()
        elif self.next_url and not self.is_loading_more:
            asyncio.create_task(self._fetch_more_for_refit(jump=True))

    async def _fetch_more_for_refit(self, jump=False):
        if self.is_loading_more: return
        self.is_loading_more = True
        self.progress.setVisible(True)
        try:
            feed = await self.opds_client.get_feed(self.next_url)
            self._update_after_fetch(feed, self.next_url, reset_offset=False)
            
            new_items = feed.publications or [n for n in (feed.navigation or []) if n.title != "Start"]
            
            # Prevent duplicates
            existing_ids = {getattr(i, 'id', None) or getattr(i, 'href', None) for i in self.items_buffer}
            filtered_new = [i for i in new_items if (getattr(i, 'id', None) or getattr(i, 'href', None)) not in existing_ids]
            
            if filtered_new:
                self.items_buffer.extend(filtered_new)
                logger.debug(f"Buffer Extended (Forward) | added:{len(filtered_new)}, total:{len(self.items_buffer)}")
                
            if jump:
                # Only jump if there's actually more room in the total item count
                current_abs_idx = self.buffer_absolute_offset + self.refit_offset
                if current_abs_idx + self.items_per_screen < self.total_items:
                    self.refit_offset += self.items_per_screen
                    if self.on_offset_change: self.on_offset_change(self.refit_offset)
            
            self._render_refit_screen()
        except Exception as e:
            logger.error(f"Error fetching more for ReFit: {e}")
        finally:
            self.is_loading_more = False
            self.progress.setVisible(False)

    def prev_refit_screen(self):
        logger.debug("User clicked ReFit Prev Screen")
        if self.refit_offset > 0:
            self.refit_offset = max(0, self.refit_offset - self.items_per_screen)
            if self.on_offset_change: self.on_offset_change(self.refit_offset)
            self._render_refit_screen()
        elif self.prev_url and not self.is_loading_more:
            asyncio.create_task(self._fetch_prev_for_refit(jump=True))

    async def _fetch_prev_for_refit(self, jump=False):
        if self.is_loading_more: return
        self.is_loading_more = True
        self.progress.setVisible(True)
        try:
            feed = await self.opds_client.get_feed(self.prev_url)
            self._update_after_fetch(feed, self.prev_url, reset_offset=False)
            
            new_items = feed.publications or [n for n in feed.navigation if n.title != "Start"]
            
            # Prevent duplicates
            existing_ids = {getattr(i, 'id', None) or getattr(i, 'href', None) for i in self.items_buffer}
            filtered_new = [i for i in new_items if (getattr(i, 'id', None) or getattr(i, 'href', None)) not in existing_ids]
            
            if filtered_new:
                count = len(filtered_new)
                self.items_buffer = filtered_new + self.items_buffer
                
                # Update absolute offset
                self.buffer_absolute_offset -= count
                if self.buffer_absolute_offset < 0: self.buffer_absolute_offset = 0
                
                # Adjust offset so we stay on the "same" items relative to the start
                self.refit_offset += count
                logger.debug(f"Buffer Extended (Backward) | added:{count}, total:{len(self.items_buffer)}, new_abs_offset:{self.buffer_absolute_offset}")
            
            if jump:
                self.refit_offset = max(0, self.refit_offset - self.items_per_screen)
                if self.on_offset_change: self.on_offset_change(self.refit_offset)
                
            self._render_refit_screen()
        except Exception as e:
            logger.error(f"Error fetching prev for ReFit: {e}")
        finally:
            self.is_loading_more = False
            self.progress.setVisible(False)

    def jump_to_refit_offset(self, offset):
        self.refit_offset = max(0, min(offset, len(self.items_buffer) - self.items_per_screen))
        if self.on_offset_change: self.on_offset_change(self.refit_offset)
        self._render_refit_screen()

    def jump_to_absolute_first(self):
        logger.debug("User clicked ReFit Jump First")
        if self.first_url:
            asyncio.create_task(self._fetch_absolute_first())
        else:
            self.jump_to_refit_offset(0)

    async def _fetch_absolute_first(self):
        self.progress.setVisible(True)
        try:
            feed = await self.opds_client.get_feed(self.first_url)
            self.items_buffer = feed.publications or [n for n in feed.navigation if n.title != "Start"]
            self.refit_offset = 0
            self.buffer_absolute_offset = 0 # It's the first page
            self._update_after_fetch(feed, self.first_url)
            self._render_refit_screen()
        except Exception as e:
            logger.error(f"Error jumping to first: {e}")
        finally:
            self.progress.setVisible(False)

    def jump_to_absolute_last(self):
        logger.debug("User clicked ReFit Jump Last")
        if self.last_url:
            asyncio.create_task(self._fetch_absolute_last())
        else:
            self.jump_to_refit_offset(len(self.items_buffer) - self.items_per_screen)

    async def _fetch_absolute_last(self):
        if self.is_loading_more: return
        self.is_loading_more = True
        self.progress.setVisible(True)
        try:
            feed = await self.opds_client.get_feed(self.last_url)
            # HARD RESET: replace buffer to ensure perfect alignment
            self.items_buffer = feed.publications or [n for n in feed.navigation if n.title != "Start"]
            
            # 1. Update metadata and ABSOLUTE OFFSET
            self._update_after_fetch(feed, self.last_url, reset_offset=True)
            
            # 2. Wait for UI to settle
            await asyncio.sleep(0.05)
            
            # 3. Align ReFit to the absolute global end
            if self.items_per_screen > 0:
                # Target the start of the final screen globally
                target_global_start = ((self.total_items - 1) // self.items_per_screen) * self.items_per_screen
                # Calculate local offset within THIS buffer
                self.refit_offset = target_global_start - self.buffer_absolute_offset
                self.refit_offset = max(0, min(self.refit_offset, len(self.items_buffer) - 1))
            else:
                self.refit_offset = 0
                
            self._render_refit_screen()
        except Exception as e:
            logger.error(f"Error jumping to last: {e}")
        finally:
            self.is_loading_more = False
            self.progress.setVisible(False)

    def _update_after_fetch(self, feed, url, reset_offset=True):
        self._last_feed_metadata = feed.metadata
        self.total_items = getattr(feed.metadata, 'numberOfItems', self.total_items)
        
        # 1. Determine and lock the server index base (0 vs 1) for this session if not yet known
        if not hasattr(self, '_server_index_base') or self._server_index_base is None:
            curr_page = getattr(feed.metadata, 'currentPage', None)
            if curr_page is not None:
                # If we are on the first page (no prev link), curr_page IS our base.
                has_prev = any(l.rel == "prev" or l.rel == "previous" for l in (feed.links or []))
                if not has_prev:
                    self._server_index_base = curr_page
                else:
                    # Guess: 0 if we see a 0, else 1
                    self._server_index_base = 0 if curr_page == 0 else 1

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

        if reset_offset:
            curr_page = getattr(feed.metadata, 'currentPage', None)
            per_page = getattr(feed.metadata, 'itemsPerPage', 100)
            if curr_page is not None:
                base = self._server_index_base if self._server_index_base is not None else 1
                self.buffer_absolute_offset = (curr_page - base) * per_page
                logger.debug(f"Paging Detection | curr_pg:{curr_page}, base:{base}, abs_offset:{self.buffer_absolute_offset}")

    def _on_scroll_event(self, value):
        if self.config_manager.get_scroll_method() == "continuous":
            self._scroll_debounce.start()
            
            # Throttled live update during scrub (~20fps)
            now = time.time()
            if not hasattr(self, '_last_scroll_update'): self._last_scroll_update = 0
            if now - self._last_scroll_update > 0.05:
                self._sync_continuous_view()
                self._last_scroll_update = now

    def _on_scroll_settled(self):
        if self.config_manager.get_scroll_method() == "continuous":
            # Final sync and trigger background fetches
            self._sync_continuous_view()
            asyncio.create_task(self._update_continuous_data())

    def _render_continuous_page(self, feed, append=False):
        # 1. Setup virtual canvas size
        available_w = self.scroll.viewport().width() - 20
        self._last_cols = max(1, available_w // 175) if self.is_pub_mode else 1
        self.content_container.setFixedWidth(self.scroll.viewport().width())

        # 2. Inject current feed items into sparse buffer
        start_idx = self.buffer_absolute_offset
        items = feed.publications or [n for n in feed.navigation if n.title != "Start"]
        for i, item in enumerate(items):
            self.sparse_buffer[start_idx + i] = item

        # 3. Size canvas (uses total_items if known, estimates from buffer otherwise)
        self._resize_continuous_canvas()

        # 4. Trigger initial sync
        self._sync_continuous_view()
        asyncio.create_task(self._update_continuous_data())

    def _resize_continuous_canvas(self):
        """Resize the virtual canvas to fit all known items.

        Uses server-reported total_items when available.  When the server does
        not include numberOfItems (total_items == 0) we estimate from the
        highest index we have loaded plus one extra server page so the
        scrollbar extends beyond the currently loaded region.
        """
        item_h = 275 if self.is_pub_mode else 45
        cols = max(1, self._last_cols) if hasattr(self, '_last_cols') else 1
        per_page = 100
        if hasattr(self, '_last_feed_metadata'):
            per_page = getattr(self._last_feed_metadata, "itemsPerPage", 100) or 100

        effective_total = self.total_items
        if not effective_total and self.sparse_buffer:
            # No server count: estimate so the scrollbar reaches past what we know
            effective_total = max(self.sparse_buffer.keys()) + per_page + 1

        if not effective_total:
            return

        rows = math.ceil(effective_total / cols)
        total_h = rows * item_h
        self.content_container.setMinimumHeight(total_h)
        self.content_container.setMaximumHeight(total_h)

    def _sync_continuous_view(self):
        """Synchronously update visible widgets based on current scroll position."""
        if not self.total_items and not self.sparse_buffer:
            return

        # Effective total: server count if known, else estimated from loaded data
        per_page = 100
        if hasattr(self, '_last_feed_metadata'):
            per_page = getattr(self._last_feed_metadata, "itemsPerPage", 100) or 100
        effective_total = self.total_items or (max(self.sparse_buffer.keys()) + per_page + 1)

        # 1. Calculate visible range
        viewport_h = self.scroll.viewport().height()
        scroll_y = self.scroll.verticalScrollBar().value()
        item_h = 275 if self.is_pub_mode else 45
        cols = max(1, getattr(self, '_last_cols', 1))

        start_row = scroll_y // item_h
        end_row = (scroll_y + viewport_h) // item_h

        # 3-row lookahead above and below reduces placeholder flicker on large feeds
        start_row = max(0, start_row - 3)
        effective_rows = math.ceil(effective_total / cols)
        end_row = min(effective_rows, end_row + 3)

        visible_indices = set(range(start_row * cols, min(effective_total, (end_row + 1) * cols)))

        # 2. Update status text
        first_visible = (scroll_y // item_h) * cols
        est_items = ((viewport_h // item_h) + 1) * cols
        total_label = str(self.total_items) if self.total_items else "?"
        self.status_label.setText(
            f"Showing {first_visible + 1}-{min(effective_total, first_visible + est_items)} of {total_label}"
        )

        # 3. Handle widget lifecycle
        self._render_visible_range(visible_indices, item_h, cols)

    async def _update_continuous_data(self):
        if (not self.total_items and not self.sparse_buffer) or self._is_updating_continuous:
            return
        self._is_updating_continuous = True
        
        try:
            tried_pages = set()
            while True:
                # Calculate visible range again
                viewport_h = self.scroll.viewport().height()
                scroll_y = self.scroll.verticalScrollBar().value()
                item_h = 275 if self.is_pub_mode else 45
                cols = self._last_cols
                per_page = 100
                if hasattr(self, '_last_feed_metadata'):
                    per_page = getattr(self._last_feed_metadata, "itemsPerPage", 100) or 100
                effective_total = self.total_items or (
                    max(self.sparse_buffer.keys()) + per_page + 1 if self.sparse_buffer else 0
                )
                if not effective_total:
                    break
                start_row = max(0, (scroll_y // item_h) - 3)
                end_row = min(math.ceil(effective_total / cols), (scroll_y + viewport_h) // item_h + 3)
                visible_indices = set(range(start_row * cols, min(effective_total, (end_row + 1) * cols)))
                
                missing = [i for i in visible_indices if i not in self.sparse_buffer]
                if not missing:
                    break

                target_idx = missing[0]
                target_page = (target_idx // per_page) + (self._server_index_base or 0)
                
                if target_page in tried_pages:
                    break
                tried_pages.add(target_page)
                
                success = await self._fetch_missing_indices(missing)
                # Sync UI immediately after fetch
                self._sync_continuous_view()
                
                if not success:
                    break
        finally:
            self._is_updating_continuous = False

    def _render_visible_range(self, visible_indices, item_h, cols):
        # Remove widgets no longer visible
        to_remove = set(self._rendered_widgets.keys()) - visible_indices
        for idx in to_remove:
            w = self._rendered_widgets.pop(idx)
            w.hide()
            w.deleteLater()
            
        # Add or update visible ones
        for idx in visible_indices:
            has_data = idx in self.sparse_buffer
            existing_widget = self._rendered_widgets.get(idx)
            
            # If we have a placeholder but now have data, replace it
            if existing_widget and getattr(existing_widget, 'is_placeholder', False) and has_data:
                existing_widget.hide()
                existing_widget.deleteLater()
                del self._rendered_widgets[idx]
                existing_widget = None

            if not existing_widget:
                if has_data:
                    item_data = self.sparse_buffer[idx]
                    widget = self._create_continuous_widget(item_data)
                else:
                    widget = self._create_placeholder_widget()
                
                widget.setParent(self.content_container)
                row = idx // cols
                col = idx % cols
                x = col * 175 if self.is_pub_mode else 0
                y = row * item_h
                widget.move(x, y)
                widget.show()
                self._rendered_widgets[idx] = widget

    def _create_placeholder_widget(self):
        w = QFrame()
        w.is_placeholder = True
        w.setObjectName("placeholder_card")
        if self.is_pub_mode:
            w.setFixedSize(160, 260)
            layout = QVBoxLayout(w)
            lbl = QLabel("...")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(lbl)
        else:
            w.setFixedSize(self.content_container.width() - 20, 40)
        return w

    def _create_continuous_widget(self, item):
        if isinstance(item, Publication):
            card = PublicationCard(item, self.api_client.profile.get_base_url(), self.image_manager)
            card.clicked.connect(self.on_open_detail_callback)
            card.selection_toggled.connect(self._on_card_selection_toggled)
            card.download_requested.connect(self.on_start_download)
            card.set_selection_mode(self._selection_mode)
            if card.self_url in self._selected_items:
                card.set_selected(True)
            return card
        else:
            # Navigation
            btn = QPushButton(item.title)
            btn.setFixedSize(self.content_container.width() - 20, 40)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setObjectName("nav_continuous_button")
            u = urljoin(self.api_client.profile.get_base_url(), item.href)
            btn.clicked.connect(lambda _, url=u, t=item.title: self.on_navigate(url, t))
            return btn

    async def _fetch_missing_indices(self, missing_indices):
        if self.is_loading_more: return False
        
        # 1. Group missing indices into server pages
        per_page = 100 # Default
        if hasattr(self, '_last_feed_metadata'):
            per_page = getattr(self._last_feed_metadata, "itemsPerPage", 100) or 100
            
        # Target the first missing index's page
        target_idx = missing_indices[0]
        target_page = (target_idx // per_page) + (self._server_index_base or 0)
        
        # 2. Predict URL
        url = self._predict_page_url(target_page)
        if not url:
            return False

        self.is_loading_more = True
        self.progress.setVisible(True)
        try:
            feed = await self.opds_client.get_feed(url)
            self._update_after_fetch(feed, url, reset_offset=False)
            
            # Map fetched items to their global indices
            page_start_idx = (target_page - (self._server_index_base or 0)) * per_page
            new_items = feed.publications or [n for n in feed.navigation if n.title != "Start"]
            
            if not new_items:
                return False

            for i, item in enumerate(new_items):
                self.sparse_buffer[page_start_idx + i] = item

            # Grow canvas if total_items just became known or estimate has changed
            self._resize_continuous_canvas()
            return True
                
        except Exception as e:
            logger.error(f"Continuous mode fetch error: {e}")
            return False
        finally:
            self.is_loading_more = False
            self.progress.setVisible(False)

    def _predict_page_url(self, page_num):
        """Predict the URL for a specific page number based on common patterns."""
        # Use next_url or last_url as a template if available, they are more likely to have params
        template_url = self.next_url or self.last_url or self._last_loaded_url
        if not template_url: return None
        
        import re
        url = template_url
        
        # Pattern 1: &page=X or ?page=X (Komga, Stump)
        if "page=" in url:
            new_url = re.sub(r'page=\d+', f'page={page_num}', url)
            logger.debug(f"Predict | Pattern:PageParam, Result: {new_url}")
            return new_url
            
        # Pattern 2: Path-based (Codex: .../p/0/1 -> .../p/0/32)
        from urllib.parse import urlparse, urlunparse
        u = urlparse(url)
        path_parts = u.path.split('/')
        
        # Find the last numeric part
        for i in reversed(range(len(path_parts))):
            if path_parts[i].isdigit():
                path_parts[i] = str(page_num)
                new_path = '/'.join(path_parts)
                new_url = urlunparse(u._replace(path=new_path))
                logger.debug(f"Predict | Pattern:PathSegment, Result: {new_url}")
                return new_url
                
        # Fallback Pattern
        if "?" in self._last_loaded_url:
            new_url = f"{self._last_loaded_url}&page={page_num}"
        else:
            new_url = f"{self._last_loaded_url}?page={page_num}"
        logger.debug(f"Predict | Pattern:Fallback, Result: {new_url}")
        return new_url

    def _render_dashboard(self, feed: OPDSFeed):
        self.paging_bar.setVisible(False)
        self.refit_paging_bar.setVisible(False)
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
                        card.selection_toggled.connect(self._on_card_selection_toggled)
                        card.download_requested.connect(self.on_start_download)
                        card.set_selection_mode(self._selection_mode)
                        if card.self_url in self._selected_items:
                            card.set_selected(True)
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
            btn.setObjectName("nav_link_button")
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
            card.selection_toggled.connect(self._on_card_selection_toggled)
            card.download_requested.connect(self.on_start_download)
            card.set_selection_mode(self._selection_mode)
            if card.self_url in self._selected_items:
                card.set_selected(True)
            grid_layout.addWidget(card, i // cols, i % cols)
            
        self.content_layout.addWidget(grid_widget)
