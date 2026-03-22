import asyncio
import urllib.parse
import re
import time
import math
from typing import List, Dict, Optional, Set
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame, QHBoxLayout, 
    QPushButton, QMenu, QListView, QAbstractItemView, QScrollArea, QProgressBar,
    QComboBox, QStackedWidget, QSizePolicy, QSpacerItem
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer

from models.feed_page import FeedPage, FeedSection, FeedItem, ItemType, SectionLayout
from api.feed_reconciler import FeedReconciler
from api.opds_v2 import OPDS2Client
from api.image_manager import ImageManager
from ui.components.feed_browser_model import FeedBrowserModel
from ui.components.feed_card_delegate import FeedCardDelegate
from ui.components.base_ribbon import BaseCardRibbon
from models.feed import FeedProfile
from ui.theme_manager import ThemeManager, UIConstants
from logger import get_logger

logger = get_logger("ui.feed_browser")

from ui.views.base_browser import BaseBrowserView

class FeedBrowser(BaseBrowserView):
    """
    Surgical high-performance feed browser inspired by 'Continuous' mode optimizations.
    Features:
    - Zero-Jump Virtual Grid
    - High-speed scroll debouncing
    - Bidirectional pre-fetching (N-1, N+1)
    - Template-based jumping (prevents walking the linked list)
    - Optional Standard Paged Mode (First/Prev/Next/Last)
    """
    item_clicked = pyqtSignal(FeedItem, list)
    navigate_requested = pyqtSignal(str, str) # url, title
    download_requested = pyqtSignal(object, str) # pub, download_url

    def __init__(self, opds_client: OPDS2Client, image_manager: ImageManager, config_manager=None, parent=None, show_labels=True):
        super().__init__(parent)
        self.opds_client = opds_client
        self.image_manager = image_manager
        self.config_manager = config_manager
        self._show_labels = show_labels
        
        s = UIConstants.scale
        # Header Configuration
        # Override base status_label style if needed
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
        
        # Paging Mode Buttons
        from PyQt6.QtWidgets import QButtonGroup
        self.paging_mode_group = QButtonGroup(self)
        self.paging_mode_group.setExclusive(True)
        
        self.btn_mode_scrolled = self.create_header_button("scrolling", "Continuous Scrolling", checkable=True)
        self.btn_mode_paged = self.create_header_button("paging", "Standard Paging", checkable=True)
        
        self.paging_mode_group.addButton(self.btn_mode_scrolled)
        self.paging_mode_group.addButton(self.btn_mode_paged)
        
        self.btn_mode_scrolled.clicked.connect(lambda: self._on_paging_mode_changed("scrolled"))
        self.btn_mode_paged.clicked.connect(lambda: self._on_paging_mode_changed("paged"))
        
        self.btn_mode_scrolled.setVisible(False)
        self.btn_mode_paged.setVisible(False)

        self.btn_select = self.create_header_button("select", "Select Mode", checkable=True)
        self.btn_select.clicked.connect(self.toggle_selection_mode)
        self.btn_select.setVisible(False)
        
        self.btn_facets = self.create_header_button("filter", "Filters")
        self.facet_menu = QMenu(self)
        self.btn_facets.setMenu(self.facet_menu)
        self.btn_facets.setVisible(False)

        self.btn_labels = self.create_header_button("label", "Toggle Labels", checkable=True)
        self.btn_labels.setChecked(self._show_labels)
        self.btn_labels.clicked.connect(self.toggle_labels)
        
        self.header_layout.addWidget(self.status_label)
        self.header_layout.addStretch()
        
        # Navigation Group (Centered)
        self.header_layout.addWidget(self.btn_first)
        self.header_layout.addWidget(self.btn_prev)
        self.header_layout.addWidget(self.page_label)
        self.header_layout.addWidget(self.btn_next)
        self.header_layout.addWidget(self.btn_last)
        
        self.header_layout.addStretch()
        
        # Right Side Controls
        paging_mode_layout = QHBoxLayout()
        paging_mode_layout.setSpacing(0)
        paging_mode_layout.setContentsMargins(0, 0, 0, 0)
        paging_mode_layout.addWidget(self.btn_mode_scrolled)
        paging_mode_layout.addWidget(self.btn_mode_paged)
        self.header_layout.addLayout(paging_mode_layout)
        
        self.header_layout.addSpacing(UIConstants.TOOLBAR_GAP)
        self.header_layout.addWidget(self.btn_labels)
        self.header_layout.addWidget(self.btn_select)
        self.header_layout.addWidget(self.btn_facets)
        
        # Selection Bar Configuration
        self.btn_sel_cancel.clicked.connect(lambda: self.toggle_selection_mode(False))
        self.btn_sel_action = QPushButton("Download Selected")
        self.btn_sel_action.setObjectName("primary_button")
        self.btn_sel_action.setStyleSheet(f"padding: {UIConstants.SECTION_HEADER_MARGIN_TOP}px {UIConstants.LAYOUT_MARGIN_DEFAULT}px; font-size: {UIConstants.FONT_SIZE_STATUS}px; font-weight: bold;")
        self.btn_sel_action.clicked.connect(self._on_bulk_download)
        self.btn_sel_action.setEnabled(False)
        self.selection_layout.addWidget(self.btn_sel_action)

        # Main Components Area
        self.grid_view = QListView()
        self.grid_model = FeedBrowserModel()
        self.grid_delegate = FeedCardDelegate(self, image_manager, show_labels=self._show_labels)
        self.grid_view.setModel(self.grid_model)
        self.grid_view.setItemDelegate(self.grid_delegate)
        self.grid_view.setViewMode(QListView.ViewMode.IconMode)
        self.grid_view.setResizeMode(QListView.ResizeMode.Adjust)
        self.grid_view.setSpacing(UIConstants.GRID_SPACING)
        self.grid_view.setIconSize(QSize(s(120), s(180)))
        self.grid_view.setFrameShape(QFrame.Shape.NoFrame)
        self.grid_view.clicked.connect(self._on_grid_clicked)
        self.grid_view.verticalScrollBar().valueChanged.connect(self._update_status)
        self.grid_view.selectionModel().selectionChanged.connect(self._update_selection_ui)
        
        # Scroll Area for Ribbons
        self.dash_scroll = QScrollArea()
        self.dash_scroll.setWidgetResizable(True)
        self.dash_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.dash_scroll.verticalScrollBar().valueChanged.connect(self._update_status)
        
        self.dash_content = QWidget()
        self.dash_layout = QVBoxLayout(self.dash_content)
        self.dash_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.dash_layout.setSpacing(UIConstants.SECTION_SPACING) # Match Library's grouped spacing
        self.dash_layout.setContentsMargins(0, 0, 0, 0)
        
        # Add a permanent widget-based spacer at the bottom
        # Widgets are more reliable for stretch than QSpacerItem in some layout configurations
        self._dash_spacer = QWidget()
        self._dash_spacer.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        self.dash_layout.addWidget(self._dash_spacer)
        
        self.dash_scroll.setWidget(self.dash_content)
        
        self.stack = QStackedWidget()
        self.stack.addWidget(self.grid_view)
        self.stack.addWidget(self.dash_scroll)
        
        # Use BaseBrowserView helper to add main content
        self.add_content_widget(self.stack)

        # State and Timers
        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._on_debounce_timeout)
        self._pending_page_requests: List[int] = []
        
        self.grid_model.page_request_needed.connect(self._on_sparse_page_triggered)
        self.grid_model.cover_request_needed.connect(self._on_cover_request)
        
        # Status Debounce (for smooth scrolling)
        self._status_timer = QTimer()
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._do_update_status)
        
        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._do_recalculate_section_heights)
        
        # State
        self._current_context_id: float = 0
        self._current_page_title: str = ""
        self._active_sparse_tasks: Dict[str, asyncio.Task] = {}
        self._active_cover_tasks: Dict[str, asyncio.Task] = {}
        self._pagination_template: Optional[str] = None
        self._is_offset_based: bool = False
        self._items_per_page: int = 100
        self._last_loaded_url: Optional[str] = None
        self._loading_lock = asyncio.Lock()
        
        self._selection_mode = False
        self._collapsed_sections: Set[str] = set()
        self._last_page: Optional[FeedPage] = None
        self._page_cache: Dict[str, FeedPage] = {} # For Standard Paging prefetch
        self._section_views: List[QListView] = [] # Track for height recalc
        
        self.current_profile: Optional[FeedProfile] = None
        self._paging_urls: Dict[str, str] = {}

    async def load_url(self, url: str, force_refresh: bool = False):
        self._current_context_id = time.time()
        ctx_id = self._current_context_id
        
        logger.info(f"FeedBrowser: Context Change -> {url} (Token: {ctx_id})")

        self.toggle_selection_mode(False)
        self.opds_client.cancel_all()
        self._cancel_sparse_tasks()
        self._pending_page_requests.clear()
        
        self._last_loaded_url = url
        
        # Check cache for Standard Paging (N+1, N-1 prefetch)
        if not force_refresh and url in self._page_cache:
            logger.debug(f"FeedBrowser: Cache hit for {url}")
            page = self._page_cache[url]
            self._render_page(page)
            asyncio.create_task(self._silent_update_links(url))
            return

        # Miss: Clear old content immediately to avoid artifacts while loading
        self._clear_dynamic_content()
        self._section_views.clear()
        self.status_label.setText("Loading...")
        for w in self.paging_widgets: w.setVisible(False)

        self.progress_bar.setVisible(True)
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
            
            page = FeedReconciler.reconcile(feed, url)
            self._detect_template(feed)
            self._render_page(page)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"FeedBrowser: Failed to load {url}: {e}")
            self._show_error(str(e))
        finally:
            if ctx_id == self._current_context_id:
                self.progress_bar.setVisible(False)

    async def _silent_update_links(self, url: str):
        """Silently refreshes paging links without re-rendering everything."""
        try:
            feed = await self.opds_client.get_feed(url)
            self._paging_urls = {}
            for link in (feed.links or []):
                rel_list = [link.rel] if isinstance(link.rel, str) else (link.rel or [])
                for rel in rel_list:
                    if rel in ["first", "previous", "next", "last"]:
                        self._paging_urls[rel] = urllib.parse.urljoin(url, link.href)
            # Footer might need update
            if self.current_profile and self.current_profile.paging_mode == "paged":
                has_paging = len(self._paging_urls) > 0
                for w in self.paging_widgets: w.setVisible(has_paging)
                
                self.btn_first.setEnabled("first" in self._paging_urls)
                self.btn_prev.setEnabled("previous" in self._paging_urls)
                self.btn_next.setEnabled("next" in self._paging_urls)
                self.btn_last.setEnabled("last" in self._paging_urls)
        except: pass

    def toggle_selection_mode(self, enabled: Optional[bool] = None):
        if enabled is None:
            enabled = not self._selection_mode
            
        super().toggle_selection_mode(enabled)
        self._selection_mode = enabled
        
        mode = QAbstractItemView.SelectionMode.MultiSelection if enabled else QAbstractItemView.SelectionMode.NoSelection
        
        # Apply to all QListViews (main grid + all ribbons)
        for view in self.findChildren(QListView):
            view.setSelectionMode(mode)
            if not enabled:
                view.clearSelection()
        
        if not enabled:
            self._update_selection_ui()

    def toggle_labels(self, enabled: bool):
        """Toggles label visibility for cards in grid and ribbons."""
        self._show_labels = enabled
        
        # 1. Update Grid Delegate
        self.grid_delegate.show_labels = enabled
        
        # 2. Update all QListViews (main grid + all ribbons)
        for view in self.findChildren(QListView):
            delegate = view.itemDelegate()
            if hasattr(delegate, 'show_labels'):
                delegate.show_labels = enabled
                
                # Fix ribbon height for new label state
                if view != self.grid_view:
                    ribbon_h = UIConstants.CARD_HEIGHT if enabled else (UIConstants.CARD_COVER_HEIGHT + UIConstants.CARD_SPACING)
                    view.setFixedHeight(ribbon_h + 10)
            
            view.viewport().update()
            view.doItemsLayout() # Force re-calculation of geometry

    def _update_selection_ui(self):
        if not self._selection_mode: return
        
        total_count = 0
        for view in self.findChildren(QListView):
            if view.isVisible():
                total_count += len(view.selectionModel().selectedIndexes())
        
        self.label_sel_count.setText(f"{total_count} items selected")
        self.btn_sel_action.setEnabled(total_count > 0)
        self.btn_sel_action.setText(f"Download Selected ({total_count})")

    def reapply_theme(self):
        """Refreshes all theme-dependent styles and icons for FeedBrowser."""
        super().reapply_theme()
        theme = ThemeManager.get_current_theme_colors()
        
        # 1. Labels and Containers
        self.page_label.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {theme['text_main']};")
        
        # Ensure scroll areas and grids don't have a white background
        self.grid_view.setStyleSheet(f"QListView {{ border: none; background-color: transparent; }}")
        if hasattr(self, "dash_scroll"):
            self.dash_scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        if hasattr(self, "dash_content"):
            self.dash_content.setStyleSheet(f"background-color: {theme['bg_main']};")

        # 2. Paging Mode Buttons
        if hasattr(self, "btn_mode_scrolled"):
            self.btn_mode_scrolled.setIcon(ThemeManager.get_icon("scrolling", "text_dim"))
            self.btn_mode_paged.setIcon(ThemeManager.get_icon("paging", "text_dim"))
            self._style_segmented_group([self.btn_mode_scrolled, self.btn_mode_paged])

        # 3. Section Headers and Delegates
        for view in self._section_views:
            # Re-update the delegate in each section view
            delegate = view.itemDelegate()
            if hasattr(delegate, 'reapply_theme'):
                delegate.reapply_theme()
            view.viewport().update()

        # Update dynamic section headers
        for w in self.findChildren(QWidget):
            if w.objectName() == "section_header":
                # Force a restyle to pick up new label colors
                w.style().unpolish(w)
                w.style().polish(w)
                for label in w.findChildren(QLabel):
                    label.style().unpolish(label)
                    label.style().polish(label)

    def _on_bulk_download(self):
        from PyQt6.QtWidgets import QMessageBox
        
        items = []
        for view in self.findChildren(QListView):
            model = view.model()
            if isinstance(model, FeedBrowserModel):
                for idx in view.selectionModel().selectedIndexes():
                    item = model.get_item(idx.row())
                    if item and item.raw_pub:
                        items.append(item.raw_pub)
                        
        count = len(items)
        if count == 0: return
        
        reply = QMessageBox.question(
            self, "Confirm Bulk Download",
            f"Are you sure you want to download {count} publication{'s' if count != 1 else ''}?\nThis will be done sequentially.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.toggle_selection_mode(False)
            asyncio.create_task(self._process_bulk_download(items))

    async def _process_bulk_download(self, pubs):
        queued_count = 0
        total_pubs = len(pubs)
        logger.info(f"Starting bulk download processing for {total_pubs} items")
        
        for i, pub in enumerate(pubs):
            download_url = FeedReconciler._find_acquisition_link(pub, self._last_loaded_url)
            
            # If missing, try fetching the full manifest
            if not download_url:
                logger.info(f"Acquisition link missing in summary for '{pub.metadata.title}', fetching full manifest...")
                self.status_label.setText(f"Fetching manifest {i+1}/{total_pubs}: {pub.metadata.title}...")
                
                self_url = None
                for l in (pub.links or []):
                    rel_list = [l.rel] if isinstance(l.rel, str) else (l.rel or [])
                    if any(r == "self" or r == "http://opds-spec.org/self" for r in rel_list):
                        self_url = urllib.parse.urljoin(self._last_loaded_url, l.href)
                        break
                
                if self_url:
                    try:
                        full_pub = await self.opds_client.get_publication(self_url)
                        download_url = FeedReconciler._find_acquisition_link(full_pub, self_url)
                    except Exception as e:
                        logger.error(f"Failed to fetch manifest for {pub.metadata.title}: {e}")
            
            if download_url:
                logger.info(f"Queuing bulk download for '{pub.metadata.title}': {download_url}")
                self.status_label.setText(f"Queued {queued_count+1}/{total_pubs}: {pub.metadata.title}...")
                self.download_requested.emit(pub, download_url)
                queued_count += 1
                await asyncio.sleep(0.05)
                
        if queued_count == 0:
            self.status_label.setText(f"Failed to queue any items. Check logs.")
        else:
            self.status_label.setText(f"Successfully queued {queued_count} item{'s' if queued_count != 1 else ''}.")
            
        QTimer.singleShot(2500, lambda: self._update_status())

    def expand_all(self):
        self._collapsed_sections.clear()
        # Find all section headers and views in the dashboard
        for view in self._section_views:
            view.setVisible(True)
        # Recalculate heights to expand everything
        self._recalculate_section_heights()

    def collapse_all(self):
        if not self._last_page: return
        for s in self._last_page.sections:
            self._collapsed_sections.add(s.section_id)
        # Hide all section views in the dashboard
        for view in self._section_views:
            view.setVisible(False)
            view.setFixedHeight(0)
        # Trigger layout update
        self.dash_content.update()

    def _show_header_context_menu(self, pos):
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.addAction("Expand All").triggered.connect(self.expand_all)
        menu.addAction("Collapse All").triggered.connect(self.collapse_all)
        
        # Determine global position correctly from the sender widget
        sender = self.sender()
        if sender:
            menu.exec(sender.mapToGlobal(pos))
        else:
            menu.exec(self.mapToGlobal(pos))

    def _render_page(self, page: FeedPage):
        self.setUpdatesEnabled(False)
        self._last_page = page
        self._current_page_title = page.title
        self._update_status()
        self._setup_facets(page)
        
        # Show select button if there are any items that can be selected
        has_items = False
        for s in page.sections:
            if s.items:
                has_items = True
                break
        self.btn_select.setVisible(has_items)
        self.btn_mode_scrolled.setVisible(has_items)
        self.btn_mode_paged.setVisible(has_items)
        
        # Mode-based UI configuration
        mode = "scrolled"
        if self.current_profile:
            mode = self.current_profile.paging_mode
            
        if mode == "paged":
            asyncio.create_task(self._prefetch_adjacent_pages())
            
        # Sync buttons
        self.btn_mode_scrolled.setChecked(mode == "scrolled")
        self.btn_mode_paged.setChecked(mode == "paged")
            
        has_paging = any(rel in self._paging_urls for rel in ["first", "previous", "next", "last"])
        
        if mode == "paged" and has_paging:
            for w in self.paging_widgets: w.setVisible(True)
            self._pagination_template = None # Disable infinite scroll logic
            
            # Update Footer Labels
            # Try to find the first section that has valid pagination info
            p_section = None
            for s in page.sections:
                if s.total_items and s.items_per_page:
                    p_section = s
                    break
            
            curr_page = p_section.current_page if p_section else (page.sections[0].current_page if page.sections else 1)
            total_items = p_section.total_items if p_section else 0
            items_per_page = p_section.items_per_page if p_section else 100
            
            if total_items and items_per_page:
                import math
                total_pages = math.ceil(total_items / items_per_page)
                self.page_label.setText(f"Page {curr_page} of {total_pages}")
            else:
                self.page_label.setText(f"Page {curr_page}")
                
            # Update Footer Buttons
            self.btn_first.setEnabled("first" in self._paging_urls)
            self.btn_prev.setEnabled("previous" in self._paging_urls)
            self.btn_next.setEnabled("next" in self._paging_urls)
            self.btn_last.setEnabled("last" in self._paging_urls)
            
        else:
            for w in self.paging_widgets: w.setVisible(False)

        self._section_views.clear()

        if mode == "paged":
            # "No Re-organizing": Render sections exactly as they appear in the feed.
            self._setup_dashboard_mode(page)
            self.stack.setCurrentWidget(self.dash_scroll)
            # Reset scroll position to top for the new page
            self.dash_scroll.verticalScrollBar().setValue(0)
            # Re-enable updates for early return
            QTimer.singleShot(100, lambda: self.setUpdatesEnabled(True))
            return

        # Default "Scrolled" logic: Promote the largest section to the main scrollable grid
        # For now, if we have multiple sections or small sections, use dashboard mode.
        # This simplifies the layout while we refactor the surgical grid.
        self._setup_dashboard_mode(page)
        self.stack.setCurrentWidget(self.dash_scroll)
        self.dash_scroll.verticalScrollBar().setValue(0)
            
        # Re-enable updates once layout is likely done
        QTimer.singleShot(100, lambda: self.setUpdatesEnabled(True))

    def _on_sparse_page_triggered(self, page_index: int):
        """Called by model. Accumulates requests for debouncing."""
        if not self._pagination_template: return
        if page_index not in self._pending_page_requests:
            self._pending_page_requests.append(page_index)
        # 150ms debounce - don't fire network requests if scrolling at high speed
        self._debounce_timer.start(150)

    def _get_visible_row_range(self):
        """Highly optimized sampler to avoid blocking the main thread during scroll."""
        total_items = self.grid_model.rowCount()
        if total_items == 0 or not self.grid_view.isVisible():
            return 0, 0
            
        from PyQt6.QtCore import QPoint
        vp_w = self.grid_view.viewport().width()
        vp_h = self.grid_view.viewport().height()
        
        # Fast sampling: check just the top and bottom corners
        first_row = 0
        idx = self.grid_view.indexAt(QPoint(10, 10))
        if idx.isValid(): first_row = idx.row()
            
        last_row = first_row
        idx = self.grid_view.indexAt(QPoint(vp_w - 10, vp_h - 10))
        if idx.isValid(): 
            last_row = idx.row()
        else:
            # Fallback for sparse bottom or very tall view
            last_row = min(total_items - 1, first_row + 50) 
            
        return first_row, last_row

    def _on_debounce_timeout(self):
        # Redirect to unified status update which now handles fetching too
        self._update_status()

    def _on_task_done(self, key: str):
        self._active_sparse_tasks.pop(key, None)
        self._update_status()

    def _update_status(self):
        # Debounce to keep scrolling buttery smooth
        if not self._status_timer.isActive():
            self._status_timer.start(50)

    def _do_update_status(self):
        ctx_id = self._current_context_id
        active = len(self._active_sparse_tasks)
        status_text = self._current_page_title

        mode = "scrolled"
        if self.current_profile:
            mode = self.current_profile.paging_mode

        if mode == "paged":
            # Standard Paging Info
            if self._last_page and self._last_page.sections:
                p_section = None
                for s in self._last_page.sections:
                    if s.total_items and s.items_per_page:
                        p_section = s
                        break

                curr_page = p_section.current_page if p_section else (self._last_page.sections[0].current_page if self._last_page.sections else 1)
                total_items = p_section.total_items if p_section else 0
                items_per_page = p_section.items_per_page if p_section else 100

                if total_items and items_per_page:
                    import math
                    total_pages = math.ceil(total_items / items_per_page)
                    status_text += f" (Standard Paging - Page {curr_page} of {total_pages})"
                else:
                    status_text += f" (Standard Paging - Page {curr_page})"
                
                # Prefetch covers for visible dashboard sections
                # We only do this if we aren't in the middle of a heavy scroll
                # (handled by the timer debounce already)
                for view in self._section_views:
                    if view.isVisible():
                        # Rough visibility check within the dash_scroll
                        vr = view.visibleRegion()
                        if not vr.isEmpty():
                            # For simplicity in paged mode, we just ensure all covers 
                            # in the visible section are queued.
                            # QListView handles its own optimization for not painting hidden items.
                            m = view.model()
                            if m:
                                for r in range(m.rowCount()):
                                    # Since sections are small in paged mode, this is usually fast
                                    item = m.get_item(r)
                                    if item and item.cover_url:
                                        self._on_cover_request(item.cover_url)
        else:
            # Continuous Scrolling: Update Status AND Handle Sparse Fetching
            if self.grid_view.isVisible() and self.grid_model.rowCount() > 0:
                total_items = self.grid_model.rowCount()
                first_row, last_row = self._get_visible_row_range()

                if total_items > 0:
                    status_text += f" (Showing items {first_row + 1}-{last_row + 1} of {total_items})"

                self._ensure_visible_covers(first_row, last_row)
                
                # SURGICAL FETCHING LOGIC (formerly in _on_debounce_timeout)
                if self._pagination_template and self._pending_page_requests:
                    first_page = (first_row // self._items_per_page) + 1
                    last_page = (last_row // self._items_per_page) + 1
                    visible_pages = set(range(max(1, first_page - 1), last_page + 2))
                    
                    to_fetch = []
                    for p in reversed(self._pending_page_requests):
                        if p in visible_pages and p not in to_fetch:
                            if len(to_fetch) < 3: to_fetch.append(p)
                    
                    self._pending_page_requests.clear()
                    
                    for page_idx in to_fetch:
                        val = (page_idx - 1) * self._items_per_page if self._is_offset_based else page_idx
                        url = self._pagination_template.replace("{page}", str(val))
                        task_key = f"{ctx_id}_{page_idx}"
                        if task_key not in self._active_sparse_tasks:
                            task = asyncio.create_task(self._fetch_sparse_page_to_model(self.grid_model, page_idx, url, ctx_id))
                            self._active_sparse_tasks[task_key] = task
                            task.add_done_callback(lambda t, k=task_key: self._on_task_done(k))

        if active > 0:
            status_text += f" [Loading {active}...]"

        self.status_label.setText(status_text)
    def _ensure_visible_covers(self, first_row: int, last_row: int):
        if first_row < 0 or last_row < 0: return
        for row in range(first_row, last_row + 1):
            item = self.grid_model.get_item(row)
            if item and item.cover_url:
                self._on_cover_request(item.cover_url)

    async def _fetch_sparse_page_to_model(self, model: FeedBrowserModel, page_index: int, url: str, ctx_id: float):
        async with self._loading_lock:
            if ctx_id != self._current_context_id:
                logger.debug(f"FeedBrowser: Ignoring sparse fetch for Page {page_index} (Context Changed)")
                return
            try:
                logger.info(f"FeedBrowser: Requesting Page {page_index}: {url}")
                feed = await self.opds_client.get_feed(url)
                if ctx_id != self._current_context_id:
                    logger.debug(f"FeedBrowser: Discarding Page {page_index} response (Context Changed)")
                    return
                
                page = FeedReconciler.reconcile(feed, url)
                
                main_section = None
                for s in page.sections:
                    if (s.total_items or 0) > 50 or len(s.items) > 50:
                        main_section = s
                        break
                if not main_section and page.sections:
                    main_section = max(page.sections, key=lambda s: len(s.items))
                    
                new_items = main_section.items if main_section else []
                
                logger.debug(f"FeedBrowser: Injected {len(new_items)} items for Page {page_index}")
                model.set_items_for_page(page_index, new_items)
                        
            except asyncio.CancelledError:
                logger.debug(f"FeedBrowser: Page {page_index} fetch was cancelled.")
            except Exception as e:
                logger.error(f"FeedBrowser: Sparse fetch failed for page {page_index}: {e}")

    def _on_cover_request(self, url: str):
        if url not in self._active_cover_tasks:
            # Quick sync check to avoid async overhead if already downloaded
            if not self.image_manager._get_cache_path(url).exists():
                task = asyncio.create_task(self._fetch_cover(url, self._current_context_id))
                self._active_cover_tasks[url] = task
                task.add_done_callback(lambda t, u=url: self._active_cover_tasks.pop(u, None))

    async def _fetch_cover(self, url: str, ctx_id: float):
        if ctx_id != self._current_context_id: return
        try:
            await self.image_manager.get_image_b64(url)
            if ctx_id == self._current_context_id:
                # Trigger a repaint so the newly cached image is drawn
                self.grid_view.viewport().update()
                self.dash_content.update()
        except Exception as e:
            logger.debug(f"FeedBrowser: Failed to fetch cover {url}: {e}")

    async def _prefetch_adjacent_pages(self):
        """Standard Paging Prefetch (N+1, N-1, and Last)."""
        urls_to_fetch = []
        if "next" in self._paging_urls: urls_to_fetch.append(self._paging_urls["next"])
        if "previous" in self._paging_urls: urls_to_fetch.append(self._paging_urls["previous"])
        if "last" in self._paging_urls: urls_to_fetch.append(self._paging_urls["last"])
        
        ctx_id = self._current_context_id
        
        for url in urls_to_fetch:
            if url in self._page_cache: continue
            if ctx_id != self._current_context_id: break
            
            try:
                logger.debug(f"FeedBrowser: Prefetching {url}...")
                feed = await self.opds_client.get_feed(url)
                if ctx_id != self._current_context_id: break
                
                page = FeedReconciler.reconcile(feed, url)
                self._page_cache[url] = page
                
                # Pre-fetch covers for this page too
                for section in page.sections:
                    for item in section.items:
                        if item.cover_url:
                            self._on_cover_request(item.cover_url)
                            
            except Exception as e:
                logger.debug(f"FeedBrowser: Prefetch failed for {url}: {e}")

    def _detect_template(self, feed):
        """Robust template guessing inspired by Continuous mode."""
        self._items_per_page = feed.metadata.itemsPerPage or 100
        self._is_offset_based = False
        
        links = feed.links or []
        next_href = None
        last_href = None
        for l in links:
            if l.rel == "next": next_href = l.href
            if l.rel == "last": last_href = l.href
            
        if not next_href:
            self._pagination_template = None
            return

        next_href = urllib.parse.urljoin(self._last_loaded_url, next_href)
        
        # Pattern 1: Codex/Komga path-based (/p/0/1 -> /p/0/{page})
        # Look for the last numeric segment in the path
        match = re.search(r'/(?P<prefix>[a-z])/(?P<group>\d+)/(?P<page>\d+)', next_href)
        if match:
            pre, grp, page = match.groups()
            self._pagination_template = next_href.replace(f"/{pre}/{grp}/{page}", f"/{pre}/{grp}/{{page}}")
            logger.info(f"FeedBrowser: Detected PATH template: {self._pagination_template}")
            return

        # Pattern 2: Query-based (?page=2 or &offset=100)
        match = re.search(r'(?P<key>page|offset)=(?P<val>\d+)', next_href)
        if match:
            key, val = match.groups()
            if key == 'offset':
                self._is_offset_based = True
                
            self._pagination_template = next_href.replace(f"{key}={val}", f"{key}={{page}}")
            logger.info(f"FeedBrowser: Detected QUERY template (offset={self._is_offset_based}): {self._pagination_template}")
            return

    def _cancel_sparse_tasks(self):
        count = len(self._active_sparse_tasks)
        for task in self._active_sparse_tasks.values():
            task.cancel()
        self._active_sparse_tasks.clear()
        
        count_covers = len(self._active_cover_tasks)
        for task in self._active_cover_tasks.values():
            task.cancel()
        self._active_cover_tasks.clear()
        
        if count > 0 or count_covers > 0: 
            logger.debug(f"FeedBrowser: Aborted {count} background tasks, {count_covers} cover tasks.")

    def _add_section_to_layout(self, section: FeedSection, layout: QVBoxLayout, index: int = -1):
        s = UIConstants.scale
        
        # 1. Container Widget (Mirrors SeriesSection in local_library.py)
        container = QWidget()
        container.setObjectName("series_section")
        container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, UIConstants.SECTION_MARGIN_BOTTOM)
        container_layout.setSpacing(0)

        # 2. Header Area
        header_widget = QWidget()
        header_widget.setObjectName("section_header")
        header_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        header_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header_widget.customContextMenuRequested.connect(self._show_header_context_menu)

        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, UIConstants.SECTION_HEADER_MARGIN_TOP, 0, 0)
        header_layout.setSpacing(UIConstants.SECTION_HEADER_SPACING)

        is_collapsed = section.section_id in self._collapsed_sections

        btn_toggle = QPushButton()
        btn_toggle.setIcon(ThemeManager.get_icon("chevron_down" if not is_collapsed else "chevron_right"))
        btn_toggle.setFixedSize(UIConstants.TOGGLE_BUTTON_SIZE, UIConstants.TOGGLE_BUTTON_SIZE)
        btn_toggle.setFlat(True)
        btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        header_layout.addWidget(btn_toggle)

        title_text = section.title
        if title_text.lower() == "items":
            title_text = "All Items"
            
        header_label = QLabel(title_text)
        header_label.setStyleSheet(f"font-size: {UIConstants.FONT_SIZE_SECTION_HEADER}px; font-weight: bold;")
        header_label.setCursor(Qt.CursorShape.PointingHandCursor)
        header_layout.addWidget(header_label)
        
        header_layout.addStretch()
        
        if getattr(section, 'self_url', None):
            btn_all = QPushButton("See All")
            btn_all.setFlat(True)
            btn_all.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_all.setObjectName("see_all_button")
            btn_all.clicked.connect(lambda _, u=section.self_url, t=section.title: self.navigate_requested.emit(u, t))
            header_layout.addWidget(btn_all)
            
        container_layout.addWidget(header_widget)
        
        # 3. View Area
        mode = "scrolled"
        if self.current_profile:
            mode = self.current_profile.paging_mode
            
        if mode == "paged":
            total_count = len(section.items)
        else:
            total_count = section.total_items or len(section.items)
            
        model = FeedBrowserModel(total_count=total_count)
        delegate = FeedCardDelegate(self, self.image_manager, show_labels=self._show_labels)

        if section.layout == SectionLayout.RIBBON:
            view = BaseCardRibbon(self, show_labels=self._show_labels)
        else:
            view = QListView()
            view.setViewMode(QListView.ViewMode.IconMode)
            view.setResizeMode(QListView.ResizeMode.Adjust)
            view.setSpacing(s(10))
            view.setIconSize(QSize(s(120), s(180)))
            view.setFrameShape(QFrame.Shape.NoFrame)
            view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        view.setModel(model)
        view.setItemDelegate(delegate)
        self._section_views.append(view)
        container_layout.addWidget(view)
        
        if index == -1:
            layout.addWidget(container)
        else:
            layout.insertWidget(index, container)
            
        # State
        if is_collapsed:
            view.setVisible(False)
            
        def toggle(event=None):
            if event and hasattr(event, "button") and event.button() != Qt.MouseButton.LeftButton:
                return
            sid = section.section_id
            if sid in self._collapsed_sections:
                self._collapsed_sections.discard(sid)
                view.setVisible(True)
                btn_toggle.setIcon(ThemeManager.get_icon("chevron_down"))
                if view.viewMode() == QListView.ViewMode.IconMode:
                    self._recalculate_single_view_height(view)
                else:
                    view.update_ribbon_height()
            else:
                self._collapsed_sections.add(sid)
                view.setVisible(False)
                view.setFixedHeight(0)
                btn_toggle.setIcon(ThemeManager.get_icon("chevron_right"))
                
        btn_toggle.clicked.connect(toggle)
        header_label.mousePressEvent = toggle

        model.set_items_for_page(1, section.items)
        ctx_id = self._current_context_id
        
        def on_page_req(page_idx, m=model):
            if mode == "scrolled" and ctx_id == self._current_context_id and self._pagination_template:
                url = self._pagination_template.replace("{page}", str(page_idx))
                asyncio.create_task(self._fetch_sparse_page_to_model(m, page_idx, url, ctx_id))
        
        model.page_request_needed.connect(on_page_req)
        model.cover_request_needed.connect(self._on_cover_request)
        
        view.clicked.connect(lambda index, m=model: self._on_ribbon_clicked(index, m))
        view.selectionModel().selectionChanged.connect(self._update_selection_ui)
        
        if self._selection_mode:
            view.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)

    def _on_ribbon_clicked(self, index, model):
        if self._selection_mode: return
        item = model.get_item(index.row())
        if item: self._on_item_action(item, model)

    def _clear_dynamic_content(self):
        """Standardized way to clear all dynamic view content while keeping the base shell."""
        # Reset the stack indices to empty states if possible, or clear widgets
        self.grid_model.clear()
        
        # Clear dashboard ribbons
        while self.dash_layout.count():
            item = self.dash_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # Recursively clear sub-layouts
                while item.layout().count():
                    si = item.layout().takeAt(0)
                    if si.widget(): si.widget().deleteLater()
                item.layout().deleteLater()

    def refresh_icons(self):
        theme = ThemeManager.get_current_theme_colors()
        
        # 1. Update navigation buttons
        self.btn_first.setIcon(ThemeManager.get_icon("chevrons_left", "text_dim"))
        self.btn_prev.setIcon(ThemeManager.get_icon("chevron_left", "text_dim"))
        self.btn_next.setIcon(ThemeManager.get_icon("chevron_right", "text_dim"))
        self.btn_last.setIcon(ThemeManager.get_icon("chevrons_right", "text_dim"))
        
        # 2. Update style for hover effect
        btn_style = f"""
            QPushButton {{ border: none; padding: 4px; }}
            QPushButton:hover {{ background-color: {theme['bg_item_hover']}; border-radius: 4px; }}
            QPushButton:disabled {{ opacity: 0.2; }}
        """
        for btn in [self.btn_first, self.btn_prev, self.btn_next, self.btn_last, self.btn_select, self.btn_facets, self.btn_labels, self.btn_mode_scrolled, self.btn_mode_paged]:
            btn.setStyleSheet(btn_style)
            
        # 3. Paging buttons and other actions
        self.btn_mode_scrolled.setIcon(ThemeManager.get_icon("scrolling", "text_dim"))
        self.btn_mode_paged.setIcon(ThemeManager.get_icon("paging", "text_dim"))
        self._style_segmented_group([self.btn_mode_scrolled, self.btn_mode_paged])
        
        self.btn_select.setIcon(ThemeManager.get_icon("select", "text_dim"))
        self.btn_facets.setIcon(ThemeManager.get_icon("filter", "text_dim"))
        self.btn_labels.setIcon(ThemeManager.get_icon("label", "text_dim"))
        
        # 4. Refresh existing ribbons in dash_layout
        for i in range(self.dash_layout.count()):
            item = self.dash_layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                # If it's a section header or ribbon, it might need restyling
                w.style().unpolish(w)
                w.style().polish(w)
                for label in w.findChildren(QLabel):
                    label.style().unpolish(label)
                    label.style().polish(label)
                if w.objectName() == "section_header":
                    # Force a restyle to pick up new label colors
                    w.style().unpolish(w)
                    w.style().polish(w)
                    for label in w.findChildren(QLabel):
                        label.style().unpolish(label)
                        label.style().polish(label)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._recalculate_section_heights()

    def _recalculate_section_heights(self):
        # Debounce to avoid thrashing
        if not self._resize_timer.isActive():
            self._resize_timer.start(50)

    def _do_recalculate_section_heights(self):
        """Dynamically adjusts the height of GRID sections to show all items based on current width."""
        if not self._section_views:
            return

        # The scroll area width is the primary constraint
        s = UIConstants.scale
        vp_width = self.dash_scroll.viewport().width() - s(20) # account for padding
        if vp_width < s(100): return
        for view in self._section_views:
            self._recalculate_single_view_height(view, vp_width)

    def _recalculate_single_view_height(self, view, vp_width=None):
        if not view.isVisible():
            view.setFixedHeight(0)
            return

        s = UIConstants.scale
        if vp_width is None:
            vp_width = self.dash_scroll.viewport().width() - s(20)
        if vp_width < s(100): return

        delegate = view.itemDelegate()
        spacing = view.spacing()

        # Reset fixed height for visible ribbons (handled separately)
        if view.viewMode() == QListView.ViewMode.ListMode:
            # Use delegate sizeHint for height
            h = view.sizeHintForRow(0) + view.horizontalScrollBar().height() + UIConstants.LAYOUT_MARGIN_DEFAULT
            if h < UIConstants.scale(200): h = UIConstants.scale(235) # Fallback
            view.setFixedHeight(h)
            return

        if view.viewMode() == QListView.ViewMode.IconMode:
            model = view.model()
            if not model: return
            count = model.rowCount()
            if count == 0: return

            # Dynamic items_per_row calculation
            card_w = UIConstants.CARD_WIDTH
            card_h = UIConstants.CARD_HEIGHT if self._show_labels else (UIConstants.CARD_COVER_HEIGHT + UIConstants.GRID_SPACING)
            if hasattr(delegate, 'card_width'): card_w = delegate.card_width
            if hasattr(delegate, 'card_height'): card_h = delegate.card_height

            # Total width per item including spacing
            item_w = card_w + spacing
            items_per_row = max(1, vp_width // item_w)

            rows = math.ceil(count / items_per_row)

            # Total height = (rows * card_height) + ((rows-1) * spacing) + safety
            # We use (rows * (card_h + spacing)) for simplicity and extra padding
            h = (rows * (card_h + spacing)) + UIConstants.LAYOUT_MARGIN_DEFAULT
            view.setMinimumHeight(h)
            view.setMaximumHeight(h)
            
            # Lock vertical scroll range for child views
            view.verticalScrollBar().setRange(0, 0)
    def _setup_dashboard_mode(self, page: FeedPage):
        self._section_views.clear()
        # Clear all widgets except the permanent spacer at the end
        while self.dash_layout.count() > 1:
            item = self.dash_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # recursively delete layouts if any
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget(): sub.widget().deleteLater()
                item.layout().deleteLater()

        for section in page.sections:
            # Insert before the spacer
            self._add_section_to_layout(section, self.dash_layout, index=self.dash_layout.count()-1)

        # Ensure spacer has huge stretch
        self.dash_layout.setStretch(self.dash_layout.count() - 1, 100)

        # Trigger initial height calc
        QTimer.singleShot(50, self._recalculate_section_heights)


    def _on_grid_clicked(self, index):
        if self._selection_mode: return
        item = self.grid_model.get_item(index.row())
        if item: self._on_item_action(item, self.grid_model)

    def _setup_facets(self, page: FeedPage):
        self.facet_menu.clear()
        if not page.facets:
            self.btn_facets.setVisible(False)
            return
        self.btn_facets.setVisible(True)
        for group in page.facets:
            is_dict = isinstance(group, dict)
            metadata = group.get("metadata") if is_dict else getattr(group, "metadata", None)
            
            # Safety: handle missing metadata
            if metadata:
                title = metadata.get("title") if isinstance(metadata, dict) else getattr(metadata, "title", "Filter")
            else:
                title = "Filter"
                
            self.facet_menu.addAction(title).setEnabled(False)
            
            links = []
            if is_dict:
                links = group.get("navigation") or group.get("links") or []
            else:
                links = getattr(group, "navigation", None) or getattr(group, "links", None) or []
                
            for link in links:
                if is_dict:
                    l_title = link.get("title", "Option")
                    l_href = link.get("href")
                else:
                    l_title = getattr(link, "title", "Option")
                    l_href = getattr(link, "href", None)
                if l_href:
                    url = urllib.parse.urljoin(self._last_loaded_url, l_href)
                    self.facet_menu.addAction(f"  {l_title}").triggered.connect(lambda checked, u=url, t=l_title: self.navigate_requested.emit(u, t))
            self.facet_menu.addSeparator()

    def _on_item_action(self, item, model: FeedBrowserModel = None):
        if not item: return
        context_pubs = []
        if model:
            # Gather up to a reasonable limit to avoid massive arrays in memory, but enough for reading context
            # We'll gather all loaded publications from the model, ordered by row index
            for row in sorted(model._items.keys()):
                itm = model._items[row]
                if itm and itm.raw_pub:
                    context_pubs.append(itm.raw_pub)
                    
        self.item_clicked.emit(item, context_pubs)

    def _show_error(self, message: str):
        self.status_label.setText(f"Error: {message}")

    def _on_paging_mode_changed(self, new_mode: str):
        if not self.current_profile: return
        
        if self.current_profile.paging_mode == new_mode:
            return
            
        self.current_profile.paging_mode = new_mode
            
        if self.config_manager:
            self.config_manager.update_feed(self.current_profile)
            
        # Reset to Page 1 for the current context
        url = self._paging_urls.get("first") or self._last_loaded_url or self.current_profile.url
        
        # If we had to fallback to _last_loaded_url, try to strip pagination manually
        if "first" not in self._paging_urls:
            url = re.sub(r'(/[a-z]/\d+/)\d+', r'\g<1>1', url)
            url = re.sub(r'([?&](?:page|offset))=\d+', r'\1=1', url)

        asyncio.create_task(self.load_url(url, force_refresh=True))

    def _on_nav_clicked(self, rel: str):
        url = self._paging_urls.get(rel)
        if url:
            asyncio.create_task(self.load_url(url))
