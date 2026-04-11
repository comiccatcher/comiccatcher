import asyncio
import math
from typing import List, Optional, Set, Any
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QListView, QScrollArea, QSizePolicy, QPushButton, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer

from comiccatcher.models.feed_page import FeedPage, FeedSection, SectionLayout, ItemType
from comiccatcher.ui.theme_manager import UIConstants, ThemeManager
from comiccatcher.ui.components.feed_browser_model import FeedBrowserModel
from comiccatcher.ui.components.feed_card_delegate import FeedCardDelegate
from comiccatcher.ui.components.base_ribbon import BaseCardRibbon
from comiccatcher.ui.components.collapsible_section import CollapsibleSection
from comiccatcher.ui.views.base_feed_subview import BaseFeedSubView
from comiccatcher.logger import get_logger

logger = get_logger("ui.paged_feed_view")

class PagedFeedView(BaseFeedSubView):
    """
    Renders a feed page using the Dashboard approach (vertical stack of widgets).
    Strictly paged: only shows what the server provided in the current payload.
    """
    
    def __init__(self, image_manager, collapsed_sections: Set[str], parent=None):
        super().__init__(image_manager, collapsed_sections, parent)
        self._section_views: List[QListView] = []
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.content_layout.setSpacing(UIConstants.SECTION_SPACING)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        
        self.scroll_area.setWidget(self.content)
        self.layout.addWidget(self.scroll_area)
        
        self._spacer = QWidget()
        self._spacer.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        self.content_layout.addWidget(self._spacer)
        
        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(UIConstants.RESIZE_DEBOUNCE_MS)
        self._resize_timer.timeout.connect(self._do_recalculate_heights)

    def set_show_labels(self, show: bool):
        self._show_labels = show
        for view in self._section_views:
            # Sync ribbon's internal show_labels if applicable
            if hasattr(view, 'show_labels'):
                view.show_labels = show
                
            delegate = view.itemDelegate()
            if hasattr(delegate, 'show_labels'):
                delegate.show_labels = show
            
            # Fix ribbon height for new label state
            if hasattr(view, 'update_ribbon_height'):
                view.update_ribbon_height()
            
            view.viewport().update()
            view.doItemsLayout()
        
        # Immediate update instead of debounced
        self._do_recalculate_heights()

    def reapply_theme(self):
        """Refreshes themed elements in all active sections."""
        theme = ThemeManager.get_current_theme_colors()
        bg = theme.get("bg_main", "#1e1e1e")
        self.setStyleSheet(f"background-color: {bg};")
        
        from comiccatcher.ui.components.collapsible_section import CollapsibleSection
        for section in self.findChildren(CollapsibleSection):
            if hasattr(section, 'header_label'):
                section.header_label.setStyleSheet(f"font-size: {UIConstants.FONT_SIZE_SECTION_HEADER}px; font-weight: bold; color: {theme['text_main']};")
            if hasattr(section, 'btn_toggle'):
                section._update_ui_state()
        
        for view in self._section_views:
            view.viewport().update()
        self.update()

    def render(self, page: FeedPage):
        self._clear_content()
        self._section_views.clear()
        
        # UI-side Layout Heuristics
        main_sec = page.main_section
        main_sec = page.main_section
        
        logger.debug(f"PagedFeedView: Rendering '{page.title}' with {len(page.sections)} sections")

        for section in page.sections:
            layout = section.layout
            source_info = f" (source={section.source_element})" if section.source_element else ""
            logger.debug(f"  Section '{section.title}': layout={'GRID' if layout == SectionLayout.GRID else 'RIBBON'} (items={len(section.items)}){source_info}")
            self._add_section(section, layout)
            
        self.content_layout.addWidget(self._spacer)
        self.content_layout.setStretch(self.content_layout.count() - 1, 100)
        
        self._do_recalculate_heights()
        self.scroll_area.verticalScrollBar().setValue(0)

    def _add_section(self, section: FeedSection, layout: SectionLayout):
        # Paged views typically show one static page at a time.
        # We use the actual item count as the stride to ensure local rows map correctly to this page.
        model = FeedBrowserModel(items_per_page=len(section.items) or UIConstants.DEFAULT_PAGING_STRIDE)
        
        if layout == SectionLayout.RIBBON:
            view = BaseCardRibbon(self, show_labels=self._show_labels)
            view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            view.viewport().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        else:
            view = QListView()
            self.configure_list_view(view)
            # Override base set by configure_list_view if needed, but we already set it to False
            view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        delegate = FeedCardDelegate(view, self.image_manager, show_labels=self._show_labels)
        view.setModel(model)
        view.setItemDelegate(delegate)
        view.viewport().installEventFilter(self)
        view._section_id = section.section_id
        self._section_views.append(view)

        # Correctly find the FeedBrowser parent
        # This is more robust than self.parent() as we might be nested.
        browser = self.parent()
        while browser and not hasattr(browser, 'create_action_button'):
            browser = browser.parent()

        # Wrapping
        action_widget = None
        if getattr(section, 'self_url', None) and browser:
            label = "See All"
            if getattr(section, 'total_items', None) and section.total_items > len(section.items):
                label = f"See All ({section.total_items})"
                
            btn_all = browser.create_action_button(
                label,
                lambda _, u=section.self_url, t=section.title: self.navigate_requested.emit(u, t, False)
            )
            action_widget = btn_all

        on_ctx = browser._show_header_context_menu if browser and hasattr(browser, '_show_header_context_menu') else None
        is_collapsed = section.section_id in self._collapsed_sections
        collapsible = CollapsibleSection(
            title=section.title,
            content_widget=view,
            action_widget=action_widget,
            is_collapsed=is_collapsed,
            on_context_menu=on_ctx
        )
        collapsible._section_id = section.section_id
        
        def _on_toggled(collapsed: bool, sid=section.section_id, v=view):
            if collapsed: self._collapsed_sections.add(sid)
            else:
                self._collapsed_sections.discard(sid)
                self._recalculate_single_height(v)
        collapsible.toggled.connect(_on_toggled)

        self.content_layout.insertWidget(self.content_layout.count() - 1, collapsible)
        
        model.set_sections([section])
        model.set_items_for_page(1, section.items)
        model.cover_request_needed.connect(self.cover_request_needed.emit)
        
        view.clicked.connect(lambda idx, m=model: self._on_item_clicked(idx, m))
        view.customContextMenuRequested.connect(lambda pos, v=view, m=model: self._on_custom_context_menu(pos, v, m))

    def _on_custom_context_menu(self, pos, view, model):
        if self._selection_mode: return
        
        index = view.indexAt(pos)
        if not index.isValid(): return
        item = model.get_item(index.row())
        if not item or item.type == ItemType.FOLDER: return
        
        # Emit global position for the popover
        global_pos = view.viewport().mapToGlobal(pos)
        self.mini_detail_requested.emit(item, global_pos, model)

    def eventFilter(self, source, event):
        """Dynamic cursor change when hovering over items."""
        if event.type() == event.Type.MouseMove:
            for view in self._section_views:
                if source is view.viewport():
                    index = view.indexAt(event.pos())
                    if index.isValid():
                        view.setCursor(Qt.CursorShape.PointingHandCursor)
                    else:
                        view.setCursor(Qt.CursorShape.ArrowCursor)
                    break
        return super().eventFilter(source, event)

    def _on_item_clicked(self, index, model):
        item = model.get_item(index.row())
        if not item: return
        self.item_clicked.emit(item, self.gather_context_pubs(model))

    def _clear_content(self):
        while self.content_layout.count() > 1: # Keep spacer
            item = self.content_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._recalculate_heights()

    def _recalculate_heights(self):
        if not self._resize_timer.isActive():
            self._resize_timer.start()

    def _do_recalculate_heights(self):
        s = UIConstants.scale
        vp_width = self.scroll_area.viewport().width()
        if vp_width < s(100): vp_width = self.width()
        
        # Adjust headers for scrollbar
        self.update_header_margins(self.scroll_area.verticalScrollBar())

        vp_width -= UIConstants.VIEWPORT_MARGIN
        if vp_width < s(100): return
        
        for view in self._section_views:
            self._recalculate_single_height(view, vp_width)

    def _ensure_visible_covers(self):
        """Triggers cover request for all items currently in the viewport."""
        viewport_rect = self.scroll_area.viewport().rect()
        
        for view in self._section_views:
            if not view.isVisible():
                continue
            
            model = view.model()
            if not model:
                continue

            # Map viewport coordinates to the view's coordinate system
            view_rect = view.rect()
            global_pos = view.mapToGlobal(view_rect.topLeft())
            local_to_viewport = self.scroll_area.viewport().mapFromGlobal(global_pos)
            
            # Intersection of view and scroll viewport
            visible_in_view = viewport_rect.translated(-local_to_viewport.x(), -local_to_viewport.y()).intersected(view_rect)
            
            if visible_in_view.isEmpty():
                continue

            # Identify indices within the visible rectangle
            # For simplicity in grid/ribbon, we can just check a range of rows
            # Based on standard grid logic
            fi = view.indexAt(visible_in_view.topLeft())
            li = view.indexAt(visible_in_view.bottomRight())
            
            first = fi.row() if fi.isValid() else 0
            last = li.row() if li.isValid() else (model.rowCount() - 1)
            
            for row in range(first, last + 1):
                item = model.get_item(row)
                if item and item.cover_url:
                    self.cover_request_needed.emit(item.cover_url)

    def _recalculate_single_height(self, view, vp_width=None):
        sid = getattr(view, '_section_id', None)
        if sid in self._collapsed_sections: return
        
        if hasattr(view, 'update_ribbon_height'):
            view.update_ribbon_height()
            return
            
        s = UIConstants.scale
        if vp_width is None:
            vp_width = self.scroll_area.viewport().width()
            if vp_width < s(100): vp_width = self.width()
            vp_width -= UIConstants.VIEWPORT_MARGIN
            
        model = view.model()
        if not model or model.rowCount() == 0: return
        
        cols, row_h, sp = self.get_grid_layout_info(vp_width)
        rows = math.ceil(model.rowCount() / cols)
        
        h = (rows * row_h) + UIConstants.VIEWPORT_MARGIN
        view.setFixedHeight(h)
