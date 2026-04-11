import asyncio
import urllib.parse
import time
from typing import Dict, Optional, Set
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, 
    QMenu, QStackedWidget, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPoint
from PyQt6.QtGui import QPixmap

from comiccatcher.models.feed_page import FeedPage, FeedItem
from comiccatcher.api.opds_v2 import OPDS2Client
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

class FeedBrowser(BaseBrowserView):
    """
    Coordinator shell for feed browsing. 
    Switches between PagedFeedView and ScrolledFeedView based on content and settings.
    """
    item_clicked = pyqtSignal(FeedItem, list)
    navigate_requested = pyqtSignal(str, str, bool) # url, title, replace
    download_requested = pyqtSignal(object, str) # pub, download_url
    selection_changed = pyqtSignal()


    def __init__(self, opds_client: OPDS2Client, image_manager: ImageManager, config_manager=None, download_manager=None, parent=None, show_labels=True):
        super().__init__(parent)
        self.opds_client = opds_client
        self.image_manager = image_manager
        self.config_manager = config_manager
        self.download_manager = download_manager
        self._show_labels = show_labels
        
        # Shared State
        self._current_context_id: float = 0
        self._collapsed_sections: Set[str] = set()
        self._paging_urls: Dict[str, str] = {}
        self._paging_mode = "scrolled"
        self._last_loaded_url: Optional[str] = None
        self._last_page: Optional[FeedPage] = None
        self.current_profile: Optional[FeedProfile] = None
        self._active_busy_sources: Set[str] = set()
        self._pending_covers: Set[str] = set()
        self._last_scrolled_status = ""
        
        # 1. Setup Toolbar (from BaseBrowserView)
        self._setup_toolbar()
        
        # 2. Setup Sub-Views
        self.paged_view = PagedFeedView(self.image_manager, self._collapsed_sections, self)
        self.scrolled_view = ScrolledFeedView(self.opds_client, self.image_manager, self._collapsed_sections, self)
        self.loading_view = LoadingOverlay(self)
        
        self.stack = QStackedWidget()
        self.stack.addWidget(self.paged_view)
        self.stack.addWidget(self.scrolled_view)
        self.stack.addWidget(self.loading_view)
        self.add_content_widget(self.stack)
        
        # 3. Connect Signals
        self.paged_view.item_clicked.connect(self._on_item_clicked)
        self.paged_view.navigate_requested.connect(self.navigate_requested.emit)
        self.paged_view.cover_request_needed.connect(self._on_cover_request)
        self.paged_view.selection_changed.connect(self._update_selection_ui)
        
        self.scrolled_view.item_clicked.connect(self._on_item_clicked)
        self.scrolled_view.navigate_requested.connect(self.navigate_requested.emit)
        self.scrolled_view.status_updated.connect(self._on_scrolled_status_updated)
        self.scrolled_view.busy_updated.connect(lambda b: self._update_busy_state("scrolled_fetch", b))
        self.scrolled_view.cover_request_needed.connect(self._on_cover_request)
        self.scrolled_view.selection_changed.connect(self._update_selection_ui)

        self.paged_view.mini_detail_requested.connect(self._show_mini_detail)
        self.scrolled_view.mini_detail_requested.connect(self._show_mini_detail)

        self.detail_popover = MiniDetailPopover(self)

        # 4. Selection Action Bar Configuration

        self.btn_sel_download = self.create_selection_button("Download", "download", self._on_bulk_download)
        self.btn_sel_download.setEnabled(False)

        self.selection_layout.addWidget(self.btn_sel_download)

        if self.download_manager:
            self.download_manager.add_callback(self._on_downloads_updated)

    def _on_item_clicked(self, item, context):
        if self._selection_mode:
            return
        self.item_clicked.emit(item, context)

    def _on_downloads_updated(self):
        active = any(t.status in ("Downloading", "Pending") for t in self.download_manager.tasks.values())
        self._update_busy_state("download_manager", active)

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
        self._refresh_status_label()

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

    def _refresh_status_label(self):
        # Priority 1: Heavy network ops (Initial Load or Background Book Downloads)
        if "initial_load" in self._active_busy_sources:
            self.status_label.setText("Fetching Feed...")
            return
            
        if self.download_manager:
            active_downloads = any(t.status in ("Downloading", "Pending") for t in self.download_manager.tasks.values())
            if active_downloads:
                self.status_label.setText("Downloading Books...")
                return

        # Combine Scrolled View metrics with Thumbnail info
        # ONLY if we are in scrolled mode
        text = ""
        if self._paging_mode == "scrolled":
            text = self._last_scrolled_status
        elif self._last_page:
            # In paged mode, just show the page title as base text
            text = self._last_page.title
        
        # Add Thumbnail info if busy fetching them
        if "covers" in self._active_busy_sources:
            count = len(self._pending_covers)
            cover_text = f"Loading Thumbnails ({count})"
            if text:
                text = f"{text} | {cover_text}"
            else:
                text = cover_text
        
        # Fallback if nothing specific is set but we are busy
        if not text and len(self._active_busy_sources) > 0:
            text = "Working..."
            
        self.status_label.setText(text)

    def _setup_toolbar(self):
        s = UIConstants.scale
        self.status_label.setStyleSheet(f"font-size: {s(11)}px; font-weight: bold;")
        
        self.btn_first = self.create_header_button("chevrons_left", "First Page")
        self.btn_first.clicked.connect(lambda: self._on_nav_clicked("first"))
        
        self.btn_prev = self.create_header_button("chevron_left", "Previous Page")
        self.btn_prev.clicked.connect(lambda: self._on_nav_clicked("previous"))
        
        self.page_label = QLabel("Page 1")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_label.setStyleSheet(f"font-weight: bold; margin: 0 {UIConstants.SECTION_HEADER_SPACING}px;")
        
        self.btn_next = self.create_header_button("chevron_right", "Next Page")
        self.btn_next.clicked.connect(lambda: self._on_nav_clicked("next"))
        
        self.btn_last = self.create_header_button("chevrons_right", "Last Page")
        self.btn_last.clicked.connect(lambda: self._on_nav_clicked("last"))

        self.paging_widgets = [self.btn_first, self.btn_prev, self.page_label, self.btn_next, self.btn_last]
        for w in self.paging_widgets: w.setVisible(False)
        
        self.btn_mode_scrolled = self.create_header_button("scrolling", "Continuous Scrolling", checkable=True)
        self.btn_mode_paged = self.create_header_button("paging", "Standard Paging", checkable=True)
        self.btn_mode_scrolled.clicked.connect(lambda: self._on_paging_mode_changed("scrolled"))
        self.btn_mode_paged.clicked.connect(lambda: self._on_paging_mode_changed("paged"))

        self.btn_labels = self.create_header_button("label", "Toggle Labels", checkable=True)
        self.btn_labels.setChecked(self._show_labels)
        self.btn_labels.clicked.connect(self.toggle_labels)
        
        self.btn_select = self.create_header_button("select", "Select Mode", checkable=True)
        self.btn_select.clicked.connect(self.toggle_selection_mode)

        self.btn_facets = self.create_header_button("filter", "Filters")
        self.facet_menu = QMenu(self)
        self.btn_facets.setMenu(self.facet_menu)
        self.btn_facets.setVisible(False)

        self.header_layout.addStretch()
        self.header_layout.addWidget(self.btn_first)
        self.header_layout.addWidget(self.btn_prev)
        self.header_layout.addWidget(self.page_label)
        self.header_layout.addWidget(self.btn_next)
        self.header_layout.addWidget(self.btn_last)
        self.header_layout.addStretch()
        
        paging_mode_layout = QHBoxLayout()
        paging_mode_layout.setSpacing(0)
        paging_mode_layout.addWidget(self.btn_mode_scrolled)
        paging_mode_layout.addWidget(self.btn_mode_paged)
        self.header_layout.addLayout(paging_mode_layout)
        self.header_layout.addSpacing(UIConstants.TOOLBAR_GAP)
        self.header_layout.addWidget(self.btn_labels)
        self.header_layout.addWidget(self.btn_select)
        self.header_layout.addWidget(self.btn_facets)

    def toggle_selection_mode(self, enabled: bool):
        super().toggle_selection_mode(enabled)
        if self._paging_mode == "scrolled":
            self.scrolled_view.toggle_selection_mode(enabled)
        else:
            self.paged_view.toggle_selection_mode(enabled)

    async def load_url(self, url: str, force_refresh: bool = False):
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
        
        self._update_busy_state("initial_load", True)
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
            self._last_page = page
            self._last_raw_feed = feed
            self._render_page(page, feed, target_offset=target_offset)
            if force_refresh:
                # Give a small delay for the UI to settle before requesting covers
                QTimer.singleShot(200, self.ensure_visible_covers)
        except Exception as e:
            logger.error(f"FeedBrowser: Failed to load {url}: {e}")
            self.status_label.setText(f"Error: {e}")
        finally:
            if ctx_id == self._current_context_id:
                self._update_busy_state("initial_load", False)

    def _render_page(self, page: FeedPage, raw_feed, target_offset: Optional[int] = None):
        self._update_paging_toolbar(page)
        self._update_facets(page)
        
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
        else:
            self.stack.setCurrentWidget(self.scrolled_view)
            self.scrolled_view.render(page, page.pagination_template, page.is_offset_based, self._current_context_id, target_offset=target_offset)

    def _update_paging_toolbar(self, page):
        has_paging = any(rel in self._paging_urls for rel in ["first", "previous", "next", "last"])
        show_paging = (self._paging_mode == "paged" and has_paging)
        for w in self.paging_widgets: w.setVisible(show_paging)
        
        if show_paging:
            page_text = f"Page {page.current_page}"
            if page.total_pages:
                page_text += f" (of {page.total_pages})"
            self.page_label.setText(page_text)
            
            self.btn_first.setEnabled("first" in self._paging_urls)
            self.btn_prev.setEnabled("previous" in self._paging_urls)
            self.btn_next.setEnabled("next" in self._paging_urls)
            self.btn_last.setEnabled("last" in self._paging_urls)

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
                submenu = self.facet_menu.addMenu(title)
                
                if facet.navigation:
                    has_content = True
                    for link in facet.navigation:
                        action = submenu.addAction(link.title or "Untitled")
                        # Connect directly to load_url via navigate_requested
                        full_url = urllib.parse.urljoin(self._last_loaded_url, link.href)
                        action.triggered.connect(lambda _, u=full_url, t=(link.title or "Untitled"): self.navigate_requested.emit(str(u), str(t), False))
            elif isinstance(facet, dict):
                # Handle generic dictionary facets if any
                title = facet.get("title", "Filter")
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
                            action.triggered.connect(lambda _, u=full_url, t=l_title: self.navigate_requested.emit(str(u), str(t), False))

        self.btn_facets.setVisible(has_content)

    def _on_paging_mode_changed(self, mode):
        self._paging_mode = mode
        if self.current_profile:
            self.current_profile.paging_mode = mode
            if self.config_manager: self.config_manager.update_feed(self.current_profile)
        
        # Re-render the existing data in the new mode without a network hit
        if self._last_page:
            self._render_page(self._last_page, self._last_raw_feed)

    def _on_nav_clicked(self, rel):
        url = self._paging_urls.get(rel)
        if url:
            title = self.page_label.text()
            self.navigate_requested.emit(url, title, True)

    def _on_cover_request(self, url):
        # Trigger async fetch via helper
        def on_done():
            self._update_busy_state("covers", len(self._pending_covers) > 0)
            if self.isVisible():
                self.paged_view.content.update()
                self.scrolled_view._vp.update()

        if url not in self._pending_covers:
            self._update_busy_state("covers", True)
            asyncio.create_task(ViewportHelper.fetch_cover_async(
                url, self.image_manager, self._pending_covers, 
                on_done_callback=on_done, max_dim=400
            ))

    def ensure_visible_covers(self):
        """Triggers a fetch for all covers currently visible in the active sub-view."""
        if self._paging_mode == "scrolled":
            self.scrolled_view._ensure_visible_covers()
        else:
            self.paged_view._ensure_visible_covers()

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
        if hasattr(self, 'paged_view'):
            self.paged_view.reapply_theme()
        if hasattr(self, 'scrolled_view'):
            self.scrolled_view.reapply_theme()
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
        
        # Collect nav buttons
        nav_btns = []
        for name in ['btn_first', 'btn_prev', 'btn_next', 'btn_last']:
            if hasattr(self, name):
                nav_btns.append(getattr(self, name))
                
        for btn in nav_btns:
            btn.setStyleSheet(btn_style)
            
        if hasattr(self, 'btn_mode_scrolled') and hasattr(self, 'btn_mode_paged'):
            # Mode buttons: Segments use accent for the active one, text_dim for inactive
            self.btn_mode_scrolled.setIcon(ThemeManager.get_icon("scrolling", "text_dim"))
            self.btn_mode_paged.setIcon(ThemeManager.get_icon("paging", "text_dim"))
            self._style_segmented_group([self.btn_mode_scrolled, self.btn_mode_paged])
            
        if hasattr(self, 'btn_labels'):
            # Label toggle: Use segmented style (even if solo) to match Library view
            self.btn_labels.setIcon(ThemeManager.get_icon("label", "text_dim"))
            self._style_segmented_group([self.btn_labels])

        if hasattr(self, 'btn_select'):
            self.btn_select.setIcon(ThemeManager.get_icon("select", "text_dim"))
            self._style_segmented_group([self.btn_select])
            
        if hasattr(self, 'btn_facets'):
            self.btn_facets.setIcon(ThemeManager.get_icon("filter", "text_dim"))
            self.btn_facets.setStyleSheet(btn_style)

    def toggle_labels(self, enabled: bool):
        self._show_labels = enabled
        self.paged_view.set_show_labels(enabled)
        self.scrolled_view.set_show_labels(enabled)
        self.refresh_icons()

    def _show_mini_detail(self, item, global_pos, model):
        """Displays the metadata popover for a publication card."""
        from comiccatcher.models.feed_page import ItemType
        if not item or item.type == ItemType.FOLDER or not item.raw_pub:
            return

        pub = item.raw_pub
        meta = pub.metadata
        if not meta: return

        # 1. Map OPDS Contributors to credits string
        creds = []
        roles = [
            ("author", "Author"), ("writer", "Writer"), ("penciler", "Penciller"),
            ("artist", "Artist"), ("inker", "Inker"), ("colorist", "Colorist"),
            ("letterer", "Letterer"), ("editor", "Editor"), ("translator", "Translator")
        ]
        
        for attr, label in roles:
            contributors = getattr(meta, attr, None)
            if contributors:
                names = ", ".join(c.name for c in contributors)
                creds.append(f"{label}: {names}")

        # 2. Extract Publisher and Date
        publisher = None
        if meta.publisher:
            publisher = ", ".join(c.name for c in meta.publisher)
        
        published = meta.published
        if published:
            # OPDS dates are typically ISO 8601 (e.g., 2024-03-11)
            # Local library uses "Month Year"
            import calendar
            try:
                # Basic parse of YYYY-MM-DD
                parts = published.split('-')
                if len(parts) >= 2:
                    y_val = parts[0]
                    m_val = int(parts[1])
                    if 1 <= m_val <= 12:
                        published = f"{calendar.month_name[m_val]} {y_val}"
                elif len(parts) == 1 and len(parts[0]) == 4:
                    # Just Year
                    published = parts[0]
            except Exception:
                pass # Fallback to raw value if parsing fails

        # 3. Assemble Data Dict
        data = {
            "credits": "\n".join(creds),
            "publisher": publisher,
            "published": published,
            "summary": meta.description,
            "web": None # Handled via detail view usually, keeping it simple for now
        }

        # 4. Configure and Show Popover
        self.detail_popover.set_show_cover(False)
        self.detail_popover.clear_actions()
        
        self.detail_popover.populate(
            data=data, 
            title=meta.title, 
            subtitle=meta.subtitle
        )
        # Smart Positioning (Similar to local_library)
        # We use global_pos as a base. We need to know the card size to offset properly.
        card_w = UIConstants.CARD_WIDTH

        
        # Default: To the right of the card center
        pop_x = global_pos.x() + (card_w // 2)
        pop_y = global_pos.y()
        arrow_side = "left"
        
        # Screen boundary check
        screen = QApplication.primaryScreen().availableGeometry()
        if pop_x + self.detail_popover.width() > screen.right():
            # Show to the left instead
            pop_x = global_pos.x() - (card_w // 2)
            arrow_side = "right"
            
        self.detail_popover.show_at(QPoint(pop_x, pop_y), arrow_side=arrow_side)
