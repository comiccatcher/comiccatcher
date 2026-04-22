# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

import asyncio
import re
import urllib.parse
from urllib.parse import urljoin
import time
import uuid
from typing import Dict, Optional, Set
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, 
    QMenu, QStackedWidget, QApplication, QPushButton,
    QButtonGroup
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPoint
from PyQt6.QtGui import QPixmap

from comiccatcher.models.feed_page import FeedPage, FeedItem
from comiccatcher.api.opds_v2 import OPDS2Client, OPDSClientError
from comiccatcher.api.image_manager import ImageManager
from comiccatcher.ui.theme_manager import ThemeManager, UIConstants
from comiccatcher.models.feed import FeedProfile
from comiccatcher.logger import get_logger
from comiccatcher.ui.view_helpers import ViewportHelper

# Import specialized sub-views
from comiccatcher.ui.views.paged_feed_view import PagedFeedView
from comiccatcher.ui.views.scrolled_feed_view import ScrolledFeedView
from comiccatcher.ui.views.base_browser import BaseBrowserView
from comiccatcher.ui.components.mini_detail_popover import MiniDetailPopover
from comiccatcher.ui.components.paging_control import PagingControl

logger = get_logger("ui.feed_browser")

class LoadingOverlay(QWidget):
    """A simple full-view overlay with a large transparent logo."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.logo = QLabel()
        s = UIConstants.scale
        self._logo_size = s(256)
        
        # Apply transparency via graphics effect
        from PyQt6.QtWidgets import QGraphicsOpacityEffect
        self.opacity_effect = QGraphicsOpacityEffect()
        self.opacity_effect.setOpacity(0.15) # Mostly transparent
        self.logo.setGraphicsEffect(self.opacity_effect)
        
        self.layout.addWidget(self.logo)
        self._set_default_logo()

    def _set_default_logo(self):
        # Use the generic 'feeds' icon as the default for the background
        icon = ThemeManager.get_icon("feeds")
        pixmap = icon.pixmap(self._logo_size, self._logo_size)
        if not pixmap.isNull():
            self.set_icon(pixmap)

    def set_icon(self, pixmap: QPixmap):
        if pixmap and not pixmap.isNull():
            self.logo.setPixmap(pixmap.scaled(
                self._logo_size, self._logo_size, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            ))
        else:
            self._set_default_logo()

    def reapply_theme(self):
        theme = ThemeManager.get_current_theme_colors()
        self.setStyleSheet(f"background-color: {theme['bg_main']};")

class ErrorOverlay(QWidget):
    """An overlay shown when a feed fails to load."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s = UIConstants.scale
        self.layout.setSpacing(s(20))

        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.icon_label)

        self.message_label = QLabel("Failed to load feed")
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message_label.setWordWrap(True)
        self.layout.addWidget(self.message_label)

        self.reapply_theme()

    def set_message(self, message: str):
        self.message_label.setText(message)

    def reapply_theme(self):
        theme = ThemeManager.get_current_theme_colors()
        s = UIConstants.scale
        self.setStyleSheet(f"background-color: {theme['bg_main']};")
        self.message_label.setStyleSheet(f"font-size: {UIConstants.FONT_SIZE_FEED_NAME_LARGE}px; color: {theme['text_main']};")
        
        # Use a large error icon
        icon = ThemeManager.get_icon("close", "danger")
        self.icon_label.setPixmap(icon.pixmap(s(64), s(64)))

class FeedBrowser(BaseBrowserView):
    """
    Coordinator shell for feed browsing. 
    Switches between PagedFeedView and ScrolledFeedView based on content and settings.
    """
    item_clicked = pyqtSignal(FeedItem, list)
    navigate_requested = pyqtSignal(str, str, bool, str) # url, title, replace, icon_name
    download_requested = pyqtSignal(object, str) # pub, download_url
    selection_changed = pyqtSignal()
    page_loaded = pyqtSignal()
    card_size_changed = pyqtSignal(str)
    show_labels_changed = pyqtSignal(bool)


    def __init__(self, opds_client: OPDS2Client, image_manager: ImageManager, config_manager=None, download_manager=None, parent=None):
        super().__init__(parent)
        self.opds_client = opds_client
        self.image_manager = image_manager
        self.config_manager = config_manager
        self.download_manager = download_manager
        self._show_labels = self.config_manager.get_show_labels() if config_manager else True
        self._card_size = self.config_manager.get_card_size() if config_manager else "medium"
        
        # Shared State
        self._current_context_id: float = 0
        self._collapsed_sections: Set[str] = set()
        self._paging_urls: Dict[str, str] = {}
        self._paging_mode = "scrolled"
        self._last_loaded_url: Optional[str] = None
        self._last_page: Optional[FeedPage] = None
        self.current_profile: Optional[FeedProfile] = None
        self._active_busy_sources: Set[str] = set()
        self._pending_covers: Dict[str, asyncio.Task] = {} # url -> Task
        self._last_scrolled_status = ""
        self._active_popover_load_id: Optional[str] = None
        self._sticky_search_templates: Dict[str, str] = {} # feed_id -> last_search_template

        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(UIConstants.SCROLL_DEBOUNCE_MS)
        self._debounce_timer.timeout.connect(self._on_debounce_timeout)
        
        # 1. Setup Toolbar (from BaseBrowserView)
        self._setup_toolbar()
        
        # 2. Setup Sub-Views
        self.paged_view = PagedFeedView(self.image_manager, self._collapsed_sections, self, card_size=self._card_size)
        self.scrolled_view = ScrolledFeedView(self.opds_client, self.image_manager, self._collapsed_sections, self, card_size=self._card_size)
        self.loading_view = LoadingOverlay(self)
        self.error_view = ErrorOverlay(self)
        
        self.stack = QStackedWidget()
        self.stack.addWidget(self.paged_view)
        self.stack.addWidget(self.scrolled_view)
        self.stack.addWidget(self.loading_view)
        self.stack.addWidget(self.error_view)
        self.add_content_widget(self.stack)
        
        # 3. Connect Signals
        self.paged_view.item_clicked.connect(self._on_item_clicked)
        self.paged_view.navigate_requested.connect(self.navigate_requested.emit)
        self.paged_view.selection_changed.connect(self._update_selection_ui)
        self.paged_view.scrolled.connect(self._update_status)
        
        self.scrolled_view.item_clicked.connect(self._on_item_clicked)
        self.scrolled_view.navigate_requested.connect(self.navigate_requested.emit)
        self.scrolled_view.status_updated.connect(self._on_scrolled_status_updated)
        self.scrolled_view.busy_updated.connect(lambda b: self._update_busy_state("scrolled_fetch", b))
        self.scrolled_view.selection_changed.connect(self._update_selection_ui)
        self.scrolled_view.scrolled.connect(self._update_status)

        self.paged_view.mini_detail_requested.connect(self._show_mini_detail)
        self.scrolled_view.mini_detail_requested.connect(self._show_mini_detail)

        self.detail_popover = MiniDetailPopover(self)

        # 4. Selection Action Bar Configuration

        self.btn_sel_download = self.create_selection_button("Download", "download", self._on_bulk_download)
        self.btn_sel_download.setEnabled(False)

        self.selection_layout.addWidget(self.btn_sel_download)

    def _on_item_clicked(self, item, context):
        if self._selection_mode:
            return
        self.item_clicked.emit(item, context)

    def _update_selection_ui(self):
        """Updates selection bar label and button state."""
        subview = self.scrolled_view if self._paging_mode == "scrolled" else self.paged_view
        selected = subview.get_selected_items()
        count = len(selected)
        
        self.label_sel_count.setText(f"{count} item{'s' if count != 1 else ''}")
        self.btn_sel_download.setEnabled(count > 0)

        # Refresh icon color for visual feedback
        icon_name = self._selection_buttons.get(self.btn_sel_download)
        if icon_name:
            self.btn_sel_download.setIcon(ThemeManager.get_icon(icon_name, "accent" if count > 0 else "text_dim"))

    def _on_bulk_download(self):
        """Triggers downloads for all selected items that have download links."""
        from PyQt6.QtWidgets import QMessageBox
        subview = self.scrolled_view if self._paging_mode == "scrolled" else self.paged_view
        selected = subview.get_selected_items()
        
        # Filter items that actually have a download URL and publication data
        valid_items = [item for item in selected if item.download_url and item.raw_pub]
        
        if not valid_items:
            QMessageBox.information(self, "No Downloads Available", "None of the selected items have acquisition links.")
            return

        count = len(valid_items)
        reply = QMessageBox.question(
            self, "Confirm Bulk Download",
            f"Are you sure you want to download {count} selected item{'s' if count != 1 else ''}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            for item in valid_items:
                self.download_requested.emit(item.raw_pub, item.download_url)
            
            logger.info(f"Bulk download triggered for {count} items.")
            self.toggle_selection_mode(False)

    def _on_scrolled_status_updated(self, status: str):
        self._last_scrolled_status = status
        # Kick the status update (which starts the cover debounce)
        self._update_status()

    def _update_busy_state(self, source: str, is_busy: bool):
        if is_busy:
            self._active_busy_sources.add(source)
        else:
            self._active_busy_sources.discard(source)
        
        busy = len(self._active_busy_sources) > 0
        self.status_area.setVisible(busy)
        self.progress_bar.setVisible(busy)
        
        if busy:
            self.status_area.raise_()
        
        self._refresh_status_label()

    def _update_status(self):
        """High-frequency status update (labels only). Triggers debounced cover reconciliation."""
        if self._paging_mode == "scrolled":
            self.scrolled_view._update_status()
        else:
            self._refresh_status_label()
            
        if not self._debounce_timer.isActive():
            self._debounce_timer.start()

    def _on_debounce_timeout(self):
        """Triggered after scrolling/resizing has paused for 300ms."""
        self.ensure_visible_covers()

    def _refresh_status_label(self):
        # 1. Update Top Label (Feed Title)
        # NOTE: This label is currently unused/hidden as it is redundant with the 
        # server identity pill in the main header. Consider for removal in future cleanup.
        self.status_label.setText("")

        # 2. Update Bottom Label (Technical Stats & Progress)
        status_parts = []
        
        # Priority info: Heavy network ops
        if "initial_load" in self._active_busy_sources:
            status_parts.append("Fetching Feed...")
        elif self.download_manager:
            active_downloads = any(t.status in ("Downloading", "Pending") for t in self.download_manager.tasks.values())
            if active_downloads:
                status_parts.append("Downloading Books...")

        # Scrolled View metrics (Items 1-X of Y)
        # Only show if the feed actually supports pagination to avoid "Items 1-10 of 10" on small static lists
        is_paginated = self._last_page.is_paginated if self._last_page else False
        if self._paging_mode == "scrolled" and self._last_scrolled_status and is_paginated:
            status_parts.append(self._last_scrolled_status)
        
        # Thumbnail info
        if "covers" in self._active_busy_sources:
            count = len(self._pending_covers)
            status_parts.append(f"Loading Thumbnails ({count})")
        
        # Fallback if busy but no specific text
        if not status_parts and len(self._active_busy_sources) > 0:
            status_parts.append("Working...")
            
        full_status = " | ".join(status_parts)
        self.bottom_status_label.setText(full_status)

    @property
    def search_template(self) -> Optional[str]:
        """Returns the search template from the current page, or the last known one for this feed."""
        if self._last_page and self._last_page.search_template:
            return self._last_page.search_template
        
        if self.current_profile and self.current_profile.id in self._sticky_search_templates:
            return self._sticky_search_templates[self.current_profile.id]
        
        return None

    def _setup_toolbar(self):
        s = UIConstants.scale
        # Maintain fixed width for the left and right groups to keep the center centered.
        # We use a broader width to accommodate the Feed Title + Subtitle.
        self.left_group.setFixedWidth(s(400))
        self.right_group.setFixedWidth(s(400))
        self.right_layout.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.center_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.status_label.setStyleSheet(f"font-size: {UIConstants.FONT_SIZE_SECTION_HEADER}px; font-weight: bold;")
        
        # Paging Control
        self.paging_control = PagingControl()
        self.paging_control.nav_requested.connect(self._on_nav_clicked)
        self.paging_control.setVisible(False)
        
        self.btn_mode_scrolled = self.create_header_button("scrolling", "Continuous Scrolling", checkable=True)
        self.btn_mode_paged = self.create_header_button("paging", "Standard Paging", checkable=True)
        self.btn_mode_scrolled.clicked.connect(lambda: self._on_paging_mode_changed("scrolled"))
        self.btn_mode_paged.clicked.connect(lambda: self._on_paging_mode_changed("paged"))

        self.btn_card_small = self.create_header_button("card_small", "Small Cards", checkable=True)
        self.btn_card_medium = self.create_header_button("card_medium", "Medium Cards", checkable=True)
        self.btn_card_large = self.create_header_button("card_large", "Large Cards", checkable=True)
        self.card_size_group = QButtonGroup(self)
        self.card_size_group.setExclusive(True)
        self.card_size_group.addButton(self.btn_card_small)
        self.card_size_group.addButton(self.btn_card_medium)
        self.card_size_group.addButton(self.btn_card_large)
        self.btn_card_small.clicked.connect(lambda: self._on_card_size_changed("small"))
        self.btn_card_medium.clicked.connect(lambda: self._on_card_size_changed("medium"))
        self.btn_card_large.clicked.connect(lambda: self._on_card_size_changed("large"))

        self.btn_labels = self.create_header_button("label", "Toggle Labels", checkable=True)
        self.btn_labels.setChecked(self._show_labels)
        self.btn_labels.clicked.connect(self.toggle_labels)
        
        self.btn_select = self.create_header_button("select", "Select Mode", checkable=True)
        self.btn_select.clicked.connect(self.toggle_selection_mode)

        self.btn_facets = self.create_header_button("filter", "Filters")
        self.facet_menu = QMenu(self)
        self.btn_facets.setMenu(self.facet_menu)
        self.btn_facets.setVisible(False)

        # 5. Populate Layout Groups
        # Center (Paging)
        self.center_layout.addWidget(self.paging_control)
        
        # Right (Modes and Actions)
        paging_mode_layout = QHBoxLayout()
        paging_mode_layout.setSpacing(0)
        paging_mode_layout.addWidget(self.btn_mode_scrolled)
        paging_mode_layout.addWidget(self.btn_mode_paged)
        self.right_layout.addLayout(paging_mode_layout)
        self.right_layout.addSpacing(UIConstants.TOOLBAR_GAP)

        card_size_layout = QHBoxLayout()
        card_size_layout.setSpacing(0)
        card_size_layout.addWidget(self.btn_card_small)
        card_size_layout.addWidget(self.btn_card_medium)
        card_size_layout.addWidget(self.btn_card_large)
        self.right_layout.addLayout(card_size_layout)
        self.right_layout.addSpacing(UIConstants.TOOLBAR_GAP)

        self.right_layout.addWidget(self.btn_labels)
        self.right_layout.addWidget(self.btn_select)
        self.right_layout.addWidget(self.btn_facets)

    def toggle_selection_mode(self, enabled: bool):
        super().toggle_selection_mode(enabled)
        if self._paging_mode == "scrolled":
            self.scrolled_view.toggle_selection_mode(enabled)
        else:
            self.paged_view.toggle_selection_mode(enabled)

    async def load_url(self, url: str, force_refresh: bool = False, is_paging: bool = False):
        # Prevent redundant reloads if we are already showing this URL in this feed context.
        # This preserves scroll position when returning from Detail views or switching tabs.
        is_same_url = (url == self._last_loaded_url)
        is_same_feed = True
        if self.current_profile:
            is_same_feed = (getattr(self, "_last_feed_id", None) == self.current_profile.id)
            
        if is_same_url and is_same_feed and not force_refresh:
            # We must still ensure the sub-view is visible if switching back from detail
            # but we DON'T want to call render() as it resets scroll.
            return

        self._current_context_id = time.time()
        ctx_id = self._current_context_id
        
        # Capture scroll position if we are doing a manual refresh of the SAME URL
        target_offset = None
        if force_refresh and is_same_url and self._paging_mode == "scrolled":
            target_offset = self.scrolled_view._scroll_offset

        self._last_loaded_url = url
        
        # Try to use server icon for loading screen
        server_pixmap = None
        if self.current_profile and self.current_profile.icon_url:
            icon_url = self.current_profile.icon_url
            icon_path = self.image_manager._get_cache_path(icon_url)
            if icon_path.exists():
                server_pixmap = QPixmap(str(icon_path))
            else:
                # Trigger a background fetch for next time
                asyncio.create_task(self.image_manager.get_image_b64(icon_url))
        
        self.loading_view.set_icon(server_pixmap)
        self.stack.setCurrentWidget(self.loading_view)
        
        # Clear previous page data to prevent title/status bleed during load
        if not is_paging:
            self._last_page = None
            self.page_loaded.emit() # Refresh header immediately to clear old title
        
        # Hide paging/facets until new data arrives, UNLESS we are just paging
        if not is_paging:
            self._update_paging_toolbar(None)
            self.btn_facets.setVisible(False)
        
        self._update_busy_state("initial_load", True)
        
        # Cancel all pending thumbnail tasks for the previous page
        for task in self._pending_covers.values():
            task.cancel()
        self._pending_covers.clear()
        
        try:
            feed = await self.opds_client.get_feed(url, force_refresh=force_refresh)
            if ctx_id != self._current_context_id: return
            
            # Capture Paging Links
            self._paging_urls = {}
            for link in (feed.links or []):
                rel_list = [link.rel] if isinstance(link.rel, str) else (link.rel or [])
                for rel in rel_list:
                    if rel in ["first", "previous", "next", "last"]:
                        self._paging_urls[rel] = urllib.parse.urljoin(url, link.href)
            
            from comiccatcher.api.feed_reconciler import FeedReconciler
            page = FeedReconciler.reconcile(feed, url)
            
            # Persistent search template logic: 
            # If the current page has a template, remember it for this feed profile.
            if page.search_template and self.current_profile:
                self._sticky_search_templates[self.current_profile.id] = page.search_template

            self._last_page = page
            self._last_raw_feed = feed
            self._render_page(page, feed, target_offset=target_offset)
            if force_refresh:
                # Give a small delay for the UI to settle before requesting covers
                QTimer.singleShot(200, self.ensure_visible_covers)
        except OPDSClientError as e:
            logger.error(f"FeedBrowser: OPDS Error loading {url}: {e}")
            if ctx_id == self._current_context_id:
                msg = str(e)
                self.error_view.set_message(f"Feed Error:\n{msg}")
                self.stack.setCurrentWidget(self.error_view)
        except Exception as e:
            logger.error(f"FeedBrowser: Unexpected error loading {url}: {e}")
            if ctx_id == self._current_context_id:
                self.error_view.set_message(f"Unexpected error loading feed:\n{e}")
                self.stack.setCurrentWidget(self.error_view)
        finally:
            if ctx_id == self._current_context_id:
                self._update_busy_state("initial_load", False)

    def _render_page(self, page: FeedPage, raw_feed, target_offset: Optional[int] = None, target_item_index: Optional[int] = None):
        self._update_paging_toolbar(page)
        self._update_facets(page)
        
        # Sync the breadcrumb title (e.g., adding/removing Page suffix based on mode)
        self._sync_history_title(self._paging_mode, page.current_page)

        # Decide mode
        mode = self._paging_mode
        if self.current_profile:
            if getattr(self, '_last_feed_id', None) != self.current_profile.id:
                mode = self.current_profile.paging_mode
                self._paging_mode = mode
                self._last_feed_id = self.current_profile.id
        
        self.btn_mode_scrolled.setChecked(mode == "scrolled")
        self.btn_mode_paged.setChecked(mode == "paged")
        
        # Sync label state to sub-views before rendering
        self.paged_view.set_show_labels(self._show_labels)
        self.scrolled_view.set_show_labels(self._show_labels)
        
        if mode == "paged":
            self.stack.setCurrentWidget(self.paged_view)
            self.paged_view.render(page)
            # Sync status label
            self._refresh_status_label()
            
            # Start background pre-fetching of adjacent and last pages
            self._prefetch_adjacent_pages()
        else:
            self.stack.setCurrentWidget(self.scrolled_view)
            self.scrolled_view.render(page, page.pagination_template, page.is_offset_based, self._current_context_id, target_offset=target_offset, target_item_index=target_item_index)
            
        self._update_status()
        self.page_loaded.emit()

    def _prefetch_adjacent_pages(self):
        """Proactively fetch likely target pages into the OPDS cache."""
        # Only prefetch for paged mode
        if self._paging_mode != "paged": return
        
        # We target next, previous, and last as they are common user targets
        for rel in ["next", "previous", "last"]:
            url = self._paging_urls.get(rel)
            if url:
                # Fire and forget - the OPDSClient handles its own cache and deduplication
                task = asyncio.create_task(self.opds_client.get_feed(url))
                def _on_prefetch_done(t, u=url):
                    try:
                        t.result()
                    except Exception as e:
                        logger.debug(f"Prefetch failed for {u}: {e}")
                task.add_done_callback(_on_prefetch_done)

    def _update_paging_toolbar(self, page: Optional[FeedPage]):
        if not page:
            self.paging_control.setVisible(False)
            return

        has_paging = any(rel in self._paging_urls for rel in ["first", "previous", "next", "last"])
        show_paging = (self._paging_mode == "paged" and has_paging)
        self.paging_control.setVisible(show_paging)
        
        if show_paging:
            available_rels = set(self._paging_urls.keys())
            self.paging_control.update_state(page.current_page, page.total_pages, available_rels)

    def _update_facets(self, page: FeedPage):
        """Populates the filter menu with server-provided facets."""
        self.facet_menu.clear()
        
        if not page.facets:
            self.btn_facets.setVisible(False)
            return

        from comiccatcher.models.opds import Group
        
        has_content = False
        for facet in page.facets:
            if isinstance(facet, Group):
                title = facet.metadata.title or "Filters"
                # Create a submenu for this group
                
                # OPDS 2.0 Facets use .links, while Groups often use .navigation or .publications
                facet_links = facet.navigation or facet.links or []
                
                if facet_links:
                    has_content = True
                    submenu = self.facet_menu.addMenu(title)
                    for link in facet_links:
                        l_title = link.title or "Untitled"
                        action = submenu.addAction(l_title)
                        # Connect directly to load_url via navigate_requested
                        full_url = urllib.parse.urljoin(self._last_loaded_url, link.href)
                        facet_title = f"{title}:{l_title}"
                        action.triggered.connect(lambda _, u=full_url, t=facet_title: self.navigate_requested.emit(str(u), str(t), False, "filter"))
            elif isinstance(facet, dict):
                # Handle generic dictionary facets (OPDS 2.0 standard often uses a metadata object)
                title = "Filter"
                if "metadata" in facet and isinstance(facet["metadata"], dict):
                    title = facet["metadata"].get("title", title)
                elif "title" in facet:
                    title = facet["title"]
                
                links = facet.get("links", [])
                if links:
                    has_content = True
                    submenu = self.facet_menu.addMenu(title)
                    for link_data in links:
                        l_title = link_data.get("title", "Untitled")
                        l_href = link_data.get("href")
                        if l_href:
                            full_url = urllib.parse.urljoin(self._last_loaded_url, l_href)
                            action = submenu.addAction(l_title)
                            facet_title = f"{title}:{l_title}"
                            action.triggered.connect(lambda _, u=full_url, t=facet_title: self.navigate_requested.emit(str(u), str(t), False, "filter"))

        self.btn_facets.setVisible(has_content)

    def _sync_history_title(self, mode: str, page_number: int):
        """Updates the breadcrumb title in AppLayout to match the current mode and page."""
        base_title = self.get_current_title()
        base_title = re.sub(r" \(Page \d+\)$", "", base_title)
        
        new_title = base_title
        if mode == "paged" and page_number > 1:
            new_title = f"{base_title} (Page {page_number})"
            
        # Update AppLayout
        p = self.parent()
        while p and not hasattr(p, 'update_current_history_title'):
            p = p.parent()
        if p:
            p.update_current_history_title(new_title)

    def _on_paging_mode_changed(self, mode):
        # Determine parity targets before switching
        target_item_index = None
        target_page_index = None
        
        if self._paging_mode == "paged" and mode == "scrolled" and self._last_page:
            # Paged -> Scrolled: Calculate the start index of the current page
            ipp = self._last_page.feed_items_per_page
            if not ipp and self._last_page.main_section:
                ipp = self._last_page.main_section.items_per_page
            
            ipp = ipp or 20 # Fallback
            target_item_index = (self._last_page.current_page - 1) * ipp
        elif self._paging_mode == "scrolled" and mode == "paged":
            # Scrolled -> Paged: Determine which page is visible
            target_page_index = self.scrolled_view.get_first_visible_page_index()

        self._paging_mode = mode
        if self.current_profile:
            self.current_profile.paging_mode = mode
            if self.config_manager: self.config_manager.update_feed(self.current_profile)
        
        # Re-render or Load
        if self._last_page:
            if target_page_index and target_page_index != self._last_page.current_page:
                # We need to officially "load" the new page to get its metadata/links
                if self.scrolled_view._pagination_template:
                    val = target_page_index
                    if self.scrolled_view._pagination_base_number == 0:
                        val = target_page_index - 1
                    target_url = self.scrolled_view._pagination_template.replace("{page}", str(val))
                    asyncio.create_task(self.load_url(target_url, is_paging=True))
                else:
                    self._render_page(self._last_page, self._last_raw_feed)
            else:
                self._render_page(self._last_page, self._last_raw_feed, target_item_index=target_item_index)

        # Sync the title (removes/adds Page suffix)
        curr_p = self._last_page.current_page if self._last_page else 1
        self._sync_history_title(mode, curr_p)

    def get_current_title(self) -> str:
        """Retrieves the current breadcrumb title from the parent app layout."""
        if self.parent() and hasattr(self.parent(), 'parent'):
            # Path depends on nesting: FeedBrowser -> QStackedWidget -> AppLayout
            p = self.parent()
            while p and not hasattr(p, 'get_current_history'):
                p = p.parent()
            if p:
                hist, idx = p.get_current_history()
                if idx >= 0:
                    return hist[idx].get("title", "")
        return self._last_page.title if self._last_page else "Feed"

    def _on_nav_clicked(self, rel):
        url = self._paging_urls.get(rel)
        if url:
            # Optimistically update the page label based on the relative direction
            self._set_loading_page(rel)
            
            # Determine target page number for the breadcrumb title
            curr = self._last_page.current_page
            total = self._last_page.total_pages
            target = curr
            if rel == "first": target = 1
            elif rel == "last": target = total or curr
            elif rel == "next": target = curr + 1
            elif rel == "previous": target = max(1, curr - 1)

            # Get the base title from the current history (to preserve original link names)
            # and strip any existing Page suffix
            base_title = self.get_current_title()
            base_title = re.sub(r" \(Page \d+\)$", "", base_title)
            
            title = base_title
            if target > 1:
                title = f"{base_title} (Page {target})"
            
            # Navigate
            self.navigate_requested.emit(url, title, True, "")

    def _set_loading_page(self, rel):
        """Immediately update UI to show which page we are attempting to load."""
        if not self._last_page: return
        self.paging_control.set_loading_state(rel, self._last_page.current_page, self._last_page.total_pages)

    def _on_cover_request(self, url):
        # This is now only a fallback for direct requests. 
        # Primary reconciliation happens in ensure_visible_covers.
        if self.image_manager.get_image_sync(url):
            return
        if url in self._pending_covers:
            return

        def on_done():
            self._pending_covers.pop(url, None)
            self._update_busy_state("covers", len(self._pending_covers) > 0)
            if self.isVisible():
                self.paged_view.content.update()
                self.scrolled_view._vp.update()

        self._update_busy_state("covers", True)
        task = asyncio.create_task(ViewportHelper.fetch_cover_async(
            url, self.image_manager, set(), # We manage tracking ourselves now
            on_done_callback=on_done, max_dim=400
        ))
        self._pending_covers[url] = task

    def ensure_visible_covers(self):
        """Reconciles currently visible covers: cancels off-screen tasks, starts on-screen ones."""
        if not self.isVisible() or not self._last_page:
            return

        # 1. Identify what's visible now
        visible_urls = set()
        if self._paging_mode == "scrolled":
            visible_urls = self.scrolled_view._ensure_visible_covers()
        else:
            visible_urls = self.paged_view._ensure_visible_covers()

        # 2. Cancel tasks for URLs no longer visible
        to_cancel = [url for url in self._pending_covers if url not in visible_urls]
        for url in to_cancel:
            task = self._pending_covers.pop(url)
            task.cancel()

        # 3. Start tasks for visible URLs not yet cached or pending
        for url in visible_urls:
            if url not in self._pending_covers and not self.image_manager.get_image_sync(url):
                self._on_cover_request(url)

        self._update_busy_state("covers", len(self._pending_covers) > 0)


    def expand_all(self):
        self.set_all_sections_collapsed(False)
        self.scrolled_view.expand_all()
        
    def collapse_all(self):
        self.set_all_sections_collapsed(True)
        self.scrolled_view.collapse_all()

    def _show_header_context_menu(self, pos):
        logger.debug(f"FeedBrowser: _show_header_context_menu called at {pos}")
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QCursor
        menu = QMenu(self)
        menu.addAction("Expand All").triggered.connect(self.expand_all)
        menu.addAction("Collapse All").triggered.connect(self.collapse_all)
        
        # Use the global cursor position for the menu to avoid coordinate mapping issues
        # between nested sub-views and the main shell.
        menu.exec(QCursor.pos())

    def reapply_theme(self):
        super().reapply_theme()
        if hasattr(self, 'loading_view'):
            self.loading_view.reapply_theme()
        if hasattr(self, 'error_view'):
            self.error_view.reapply_theme()
        if hasattr(self, 'paged_view'):
            self.paged_view.reapply_theme()
        if hasattr(self, 'scrolled_view'):
            self.scrolled_view.reapply_theme()
        if hasattr(self, 'paging_control'):
            self.paging_control.reapply_theme()
        self.refresh_icons()

    def refresh_icons(self):
        theme = ThemeManager.get_current_theme_colors()
        # Default style for standard (non-segmented) buttons like nav arrows
        s = UIConstants.scale
        btn_style = f"""
            QPushButton {{ 
                border: none; 
                padding: {s(4)}px; 
                background-color: transparent;
            }} 
            QPushButton:hover {{ 
                background-color: {theme['bg_item_hover']}; 
                border-radius: {s(4)}px; 
            }}
            QPushButton:disabled {{
                opacity: 0.3;
            }}
        """

        if hasattr(self, 'btn_mode_scrolled') and hasattr(self, 'btn_mode_paged'):
            self._style_segmented_group([self.btn_mode_scrolled, self.btn_mode_paged])

        if hasattr(self, 'btn_card_small') and hasattr(self, 'btn_card_medium') and hasattr(self, 'btn_card_large'):
            self._style_segmented_group([self.btn_card_small, self.btn_card_medium, self.btn_card_large])

        if hasattr(self, 'btn_labels'):
            self._style_segmented_group([self.btn_labels])

        if hasattr(self, 'btn_select'):
            self._style_segmented_group([self.btn_select])

        if hasattr(self, 'btn_facets'):
            self.btn_facets.setStyleSheet(btn_style)

        self._refresh_toolbar_states()

    def _on_card_size_changed(self, size: str):
        if self._card_size == size: return
        self._card_size = size
        if self.config_manager:
            self.config_manager.set_card_size(size)

        self.paged_view.set_card_size(size)
        self.scrolled_view.set_card_size(size)
        self._refresh_toolbar_states()
        self.card_size_changed.emit(size)

    def _refresh_toolbar_states(self):
        """Syncs button states and icons with current configuration."""
        if hasattr(self, 'btn_mode_scrolled') and hasattr(self, 'btn_mode_paged'):
            scrolled = self._paging_mode == "scrolled"
            self.btn_mode_scrolled.setChecked(scrolled)
            self.btn_mode_paged.setChecked(not scrolled)
            self.btn_mode_scrolled.setIcon(ThemeManager.get_icon("scrolling", "accent" if scrolled else "text_dim"))
            self.btn_mode_paged.setIcon(ThemeManager.get_icon("paging", "accent" if not scrolled else "text_dim"))

        if hasattr(self, 'btn_card_small') and hasattr(self, 'btn_card_medium') and hasattr(self, 'btn_card_large'):
            small = self._card_size == "small"
            medium = self._card_size == "medium"
            large = self._card_size == "large"
            self.btn_card_small.setChecked(small)
            self.btn_card_medium.setChecked(medium)
            self.btn_card_large.setChecked(large)
            self.btn_card_small.setIcon(ThemeManager.get_icon("card_small", "accent" if small else "text_dim"))
            self.btn_card_medium.setIcon(ThemeManager.get_icon("card_medium", "accent" if medium else "text_dim"))
            self.btn_card_large.setIcon(ThemeManager.get_icon("card_large", "accent" if large else "text_dim"))

        if hasattr(self, 'btn_labels'):
            self.btn_labels.setChecked(self._show_labels)
            self.btn_labels.setIcon(ThemeManager.get_icon("label", "accent" if self._show_labels else "text_dim"))

        if hasattr(self, 'btn_select'):
            self.btn_select.setChecked(self._selection_mode)
            self.btn_select.setIcon(ThemeManager.get_icon("select", "accent" if self._selection_mode else "text_dim"))

        if hasattr(self, 'btn_facets'):
            self.btn_facets.setIcon(ThemeManager.get_icon("filter", "text_dim"))

    def toggle_labels(self, enabled: bool):
        if self._show_labels == enabled: return
        self._show_labels = enabled
        if self.config_manager:
            self.config_manager.set_show_labels(enabled)
        self.paged_view.set_show_labels(enabled)
        self.scrolled_view.set_show_labels(enabled)
        self.refresh_icons()
        self.show_labels_changed.emit(enabled)

    def _show_mini_detail(self, item, index, view, model):
        """Displays the metadata popover for a publication card and triggers enrichment."""
        from comiccatcher.models.feed_page import ItemType
        if not item or item.type == ItemType.FOLDER or not item.raw_pub:
            return

        # 1. Immediate UI update with what we have
        ViewportHelper.enrich_popover_for_item(self.detail_popover, item, self._last_loaded_url)

        # 2. Position and show (only on initial request)
        self.detail_popover.clear_actions()

        # ... (rest of action setup)
        # A. Details Action (Emits item_clicked with context)
        subview = self.scrolled_view if self._paging_mode == "scrolled" else self.paged_view
        context_pubs = subview.gather_context_pubs(model) if model else []
        self.detail_popover.add_action("eye", "Details", lambda: self._on_item_clicked(item, context_pubs))

        # B. Select Action
        def do_select():
            # Identify active view
            subview = self.scrolled_view if self._paging_mode == "scrolled" else self.paged_view

            # Find the widget containing this item
            target_view = None
            target_idx = None

            # This is a bit complex in FeedBrowser because there are multiple QListViews
            # We search for the one that has our model
            views = []
            if hasattr(subview, '_section_views'):
                views.extend(subview._section_views)
            if hasattr(subview, '_grids'):
                views.extend(list(subview._grids.values()))
            if hasattr(subview, '_ribbons'):
                views.extend(list(subview._ribbons.values()))

            for v in views:
                if v.model() == model:
                    target_view = v
                    break

            if target_view:
                # Find the row for this item in the model
                for row in range(model.rowCount()):
                    if model.get_item(row) == item:
                        target_idx = model.index(row)
                        break

            if target_view and target_idx:
                if not self._selection_mode:
                    self.toggle_selection_mode(True)

                # Selection might need to be explicit if toggle_selection_mode clears it
                from PyQt6.QtCore import QItemSelectionModel
                target_view.selectionModel().select(target_idx, QItemSelectionModel.SelectionFlag.Select)
                self._update_selection_ui()

        self.detail_popover.add_action("select", "Select", do_select)

        # C. Download Action (Connected to single-item download)
        btn_down = self.detail_popover.add_action("download", "Download", lambda: self._on_mini_detail_download(item))

        # Initial state based on current metadata
        from comiccatcher.api.feed_reconciler import FeedReconciler
        download_url, _ = FeedReconciler._find_acquisition_link(item.raw_pub, self._last_loaded_url)
        btn_down.setEnabled(download_url is not None)

        # 3. Position and show
        ViewportHelper.position_popover(self.detail_popover, view, index)
        # 4. Enrichment
        self._active_popover_load_id = ViewportHelper.trigger_manifest_enrichment(
            self.detail_popover, 
            item, 
            self.opds_client, 
            self._last_loaded_url,
            lambda: self._active_popover_load_id
        )

    def _on_mini_detail_download(self, item):

        """Starts a download for a single item from the popover."""
        from comiccatcher.api.feed_reconciler import FeedReconciler
        pub = item.raw_pub
        url, filename = FeedReconciler._find_acquisition_link(pub, self._last_loaded_url)
        if url:
            self.download_requested.emit(pub, url)
        else:
            logger.warning(f"No download URL found for {item.title}")

