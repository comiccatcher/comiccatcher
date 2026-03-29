import asyncio
import urllib.parse
import re
import time
from typing import List, Dict, Optional, Set
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, 
    QPushButton, QMenu, QStackedWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

from models.feed_page import FeedPage, FeedItem
from api.opds_v2 import OPDS2Client
from api.image_manager import ImageManager
from ui.theme_manager import ThemeManager, UIConstants
from models.feed import FeedProfile
from logger import get_logger

# Import specialized sub-views
from ui.views.paged_feed_view import PagedFeedView
from ui.views.scrolled_feed_view import ScrolledFeedView
from ui.views.base_browser import BaseBrowserView

logger = get_logger("ui.feed_browser")

class FeedBrowser(BaseBrowserView):
    """
    Coordinator shell for feed browsing. 
    Switches between PagedFeedView and ScrolledFeedView based on content and settings.
    """
    item_clicked = pyqtSignal(FeedItem, list)
    navigate_requested = pyqtSignal(str, str, bool) # url, title, replace
    download_requested = pyqtSignal(object, str) # pub, download_url


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
        
        # 1. Setup Toolbar (from BaseBrowserView)
        self._setup_toolbar()
        
        # 2. Setup Sub-Views
        self.paged_view = PagedFeedView(self.image_manager, self._collapsed_sections, self)
        self.scrolled_view = ScrolledFeedView(self.opds_client, self.image_manager, self._collapsed_sections, self)
        
        self.stack = QStackedWidget()
        self.stack.addWidget(self.paged_view)
        self.stack.addWidget(self.scrolled_view)
        self.add_content_widget(self.stack)
        
        # 3. Connect Signals
        self.paged_view.item_clicked.connect(self.item_clicked.emit)
        self.paged_view.navigate_requested.connect(self.navigate_requested.emit)
        
        self.scrolled_view.item_clicked.connect(self.item_clicked.emit)
        self.scrolled_view.status_updated.connect(self.status_label.setText)
        self.scrolled_view.busy_updated.connect(lambda b: self._update_busy_state("scrolled_fetch", b))
        self.scrolled_view.cover_request_needed.connect(self._on_cover_request)

        if self.download_manager:
            self.download_manager.add_callback(self._on_downloads_updated)

    def _on_downloads_updated(self):
        active = any(t.status in ("Downloading", "Pending") for t in self.download_manager.tasks.values())
        self._update_busy_state("download_manager", active)

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
        self.header_layout.addWidget(self.btn_facets)

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
            
            from api.feed_reconciler import FeedReconciler
            page = FeedReconciler.reconcile(feed, url)
            self._last_page = page
            self._last_raw_feed = feed
            self._render_page(page, feed, target_offset=target_offset)
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
            self.status_label.setText(page.title)
        else:
            self.stack.setCurrentWidget(self.scrolled_view)
            template, is_offset = self._detect_template(raw_feed)
            self.scrolled_view.render(page, template, is_offset, self._current_context_id, target_offset=target_offset)

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

        from models.opds import Group
        
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
                        action.triggered.connect(lambda _, u=full_url, t=link.title: self.navigate_requested.emit(u, t))
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
                            action.triggered.connect(lambda _, u=full_url, t=l_title: self.navigate_requested.emit(u, t))

        self.btn_facets.setVisible(has_content)

    def _detect_template(self, feed):
        if not feed or not hasattr(feed, 'metadata') or not feed.metadata:
            return None, False
        links = feed.links or []
        next_href = next((l.href for l in links if l.rel == "next"), None)
        if not next_href: return None, False
        
        next_href = urllib.parse.urljoin(self._last_loaded_url, next_href)
        is_offset = False
        template = None
        
        match = re.search(r'/(?P<prefix>[a-z])/(?P<group>\d+)/(?P<page>\d+)', next_href)
        if match:
            pre, grp, page = match.groups()
            template = next_href.replace(f"/{pre}/{grp}/{page}", f"/{pre}/{grp}/{{page}}")
        else:
            match = re.search(r'(?P<key>page|offset)=(?P<val>\d+)', next_href)
            if match:
                key, val = match.groups()
                is_offset = (key == 'offset')
                template = next_href.replace(f"{key}={val}", f"{key}={{page}}")
        return template, is_offset

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
        if not self.isVisible():
            return
            
        # Delegate to image manager
        async def fetch():
            await self.image_manager.get_image_b64(url)
            if self.isVisible():
                self.paged_view.content.update()
                self.scrolled_view._vp.update()
        asyncio.create_task(fetch())

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
        # Sub-views will pick up theme on their next repaint or we could explicitly call it
        if hasattr(self, 'paged_view'):
            self.paged_view.update()
        if hasattr(self, 'scrolled_view'):
            self.scrolled_view.update()
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
            
        if hasattr(self, 'btn_facets'):
            self.btn_facets.setIcon(ThemeManager.get_icon("filter", "text_dim"))
            self.btn_facets.setStyleSheet(btn_style)

    def toggle_labels(self, enabled: bool):
        self._show_labels = enabled
        self.paged_view.set_show_labels(enabled)
        self.scrolled_view.set_show_labels(enabled)
        self.refresh_icons()
