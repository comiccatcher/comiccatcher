# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

import math
from typing import List, Set
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QListView, QScrollArea, QSizePolicy, QFrame
)
from PyQt6.QtCore import Qt, QSize, QTimer, QPoint, QRect

from comiccatcher.models.feed_page import FeedPage, FeedSection, FeedItem, SectionLayout, ItemType
from comiccatcher.ui.theme_manager import UIConstants, ThemeManager
from comiccatcher.ui.components.feed_browser_model import FeedBrowserModel
from comiccatcher.ui.components.feed_card_delegate import FeedCardDelegate
from comiccatcher.ui.components.base_ribbon import FeedCardRibbon
from comiccatcher.ui.components.collapsible_section import CollapsibleSection
from comiccatcher.ui.views.base_feed_subview import BaseFeedSubView
from comiccatcher.logger import get_logger

logger = get_logger("ui.paged_feed_view")

class PagedFeedView(BaseFeedSubView):
    """
    Renders a feed page using the Dashboard approach (vertical stack of widgets).
    Strictly paged: only shows what the server provided in the current payload.
    """
    
    def __init__(self, image_manager, collapsed_sections: Set[str], parent=None, card_size="medium"):
        super().__init__(image_manager, collapsed_sections, parent)
        self._section_views: List[QListView] = []
        self._card_size = card_size
        
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
        
        self.scroll_area.verticalScrollBar().valueChanged.connect(self.scrolled.emit)
        
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

    def set_card_size(self, size: str):
        self._card_size = size
        for view in self._section_views:
            if hasattr(view, 'card_size'):
                view.card_size = size
            
            delegate = view.itemDelegate()
            if hasattr(delegate, 'card_size'):
                delegate.card_size = size
            
            if not hasattr(view, 'update_ribbon_height'): # Is grid
                view.setIconSize(QSize(UIConstants.get_card_width(size), UIConstants.get_card_height(self._show_labels, reserve_progress_space=False, card_size=size)))
            
            view.viewport().update()
            view.doItemsLayout()
        
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
        if layout == SectionLayout.RIBBON:
            view = FeedCardRibbon(self, self.image_manager, show_labels=self._show_labels, reserve_progress_space=False, card_size=self._card_size)
            model = view.model()
            view.mini_detail_requested.connect(self.mini_detail_requested)
            # Register for unified wheel/cursor handling
            view.viewport().installEventFilter(self)
        else:
            view = QListView()
            self.configure_list_view(view)
            model = FeedBrowserModel(items_per_page=len(section.items) or UIConstants.DEFAULT_PAGING_STRIDE)
            delegate = FeedCardDelegate(view, self.image_manager, show_labels=self._show_labels, card_size=self._card_size)
            view.setModel(model)
            view.setItemDelegate(delegate)
            # Override base set by configure_list_view if needed, but we already set it to False
            view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            view.setIconSize(QSize(UIConstants.get_card_width(self._card_size), UIConstants.get_card_height(self._show_labels, reserve_progress_space=False, card_size=self._card_size)))

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
                lambda _, u=section.self_url, t=section.title: self.navigate_requested.emit(u, t, False, "")
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

        self.mini_detail_requested.emit(item, index, view, model)
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
        """Returns a set of all cover URLs currently visible in any section."""
        urls = set()
        viewport_rect = self.scroll_area.viewport().rect()
        
        for view in self._section_views:
            if not view.isVisible(): continue
            
            # Map view's local rect to the scroll area's viewport coordinates
            global_topleft = view.mapToGlobal(QPoint(0, 0))
            local_topleft = self.scroll_area.viewport().mapFromGlobal(global_topleft)
            
            # Find the intersection of this specific view and the window's viewport
            # (e.g., if the view is 1000px high but only the bottom 200px is on screen)
            view_rect_in_viewport = QRect(local_topleft, view.size())
            intersection = viewport_rect.intersected(view_rect_in_viewport)
            
            if intersection.isEmpty():
                continue

            # Convert that intersection back to the view's internal coordinates
            visible_in_view = intersection.translated(-local_topleft.x(), -local_topleft.y())
            
            # Identify items in this specific slice
            fi = view.indexAt(visible_in_view.topLeft() + QPoint(10, 10))
            li = view.indexAt(visible_in_view.bottomRight() - QPoint(10, 10))
            
            model = view.model()
            if not model: continue
            
            first = fi.row() if fi.isValid() else 0
            last = li.row() if li.isValid() else (model.rowCount() - 1)
            
            for row in range(first, last + 1):
                item = model.get_item(row)
                if isinstance(item, FeedItem) and item.cover_url:
                    urls.add(item.cover_url)
        return urls

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
        
        # Grid height matches the exact content height
        h = (rows * row_h)
        view.setFixedHeight(h)
