from typing import Set, List
from PyQt6.QtWidgets import QWidget, QListView, QFrame, QAbstractItemView
from PyQt6.QtCore import Qt, pyqtSignal, QEvent
from comiccatcher.ui.theme_manager import UIConstants
from comiccatcher.ui.components.feed_browser_model import FeedBrowserModel
from comiccatcher.ui.components.feed_card_delegate import FeedCardDelegate

from comiccatcher.models.feed_page import FeedPage, FeedSection, FeedItem

class BaseFeedSubView(QWidget):
    """
    Common base class for Feed sub-views (Paged and Scrolled).
    Centralizes shared UI configuration, signals, and context gathering logic.
    """
    item_clicked = pyqtSignal(FeedItem, list) # item, context_pubs
    navigate_requested = pyqtSignal(str, str, bool, str) # url, title, replace, icon_name
    cover_request_needed = pyqtSignal(str)
    selection_changed = pyqtSignal()
    scrolled = pyqtSignal()
    mini_detail_requested = pyqtSignal(object, object, object, object) # item, index, view, model

    def __init__(self, image_manager, collapsed_sections: Set[str], parent=None):
        super().__init__(parent)
        self.image_manager = image_manager
        self._collapsed_sections = collapsed_sections
        self._show_labels = True
        self._selection_mode = False

    def configure_list_view(self, view: QListView):
        """Applies standardized settings to a QListView for consistent card rendering."""
        s = UIConstants.scale
        view.setViewMode(QListView.ViewMode.IconMode)
        view.setResizeMode(QListView.ResizeMode.Adjust)
        view.setUniformItemSizes(False) # Must be False to support mixed header/card widths
        view.setSpacing(s(10))
        view.setFrameShape(QFrame.Shape.NoFrame)
        view.setContentsMargins(0, 0, 0, 0)
        view.viewport().setContentsMargins(0, 0, 0, 0)
        view.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        view.setMouseTracking(True)
        view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        view.viewport().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # Register for unified event handling
        view.viewport().installEventFilter(self)

    def eventFilter(self, source, event):
        """Unified handling for wheel forwarding and cursor management across all feed sub-views."""
        # 1. Forward wheel events to the primary vertical scrollbar to prevent "wobble"
        if event.type() == QEvent.Type.Wheel:
            dy = event.angleDelta().y()
            if dy != 0:
                sb = self._get_target_scrollbar()
                if sb:
                    step = UIConstants.scale(20)
                    sb.setValue(sb.value() - (dy * step) // 120)
                    return True # Eat the event so the internal widget doesn't nudge

        # 2. Shared cursor management for all list viewports
        if event.type() == QEvent.Type.MouseMove:
            # Find which view this viewport belongs to
            views = self._get_all_subviews()
            for view in views:
                if source is view.viewport():
                    index = view.indexAt(event.pos())
                    view.setCursor(
                        Qt.CursorShape.PointingHandCursor if index.isValid()
                        else Qt.CursorShape.ArrowCursor)
                    break

        return super().eventFilter(source, event)

    def _get_target_scrollbar(self):
        """Returns the vertical scrollbar that should handle global scrolling."""
        # For ScrolledFeedView
        if hasattr(self, '_sb'):
            return self._sb
        # For PagedFeedView
        if hasattr(self, 'scroll_area'):
            return self.scroll_area.verticalScrollBar()
        return None

    def _get_all_subviews(self) -> List[QListView]:
        """Helper to collect all list widgets managed by the subview."""
        views = []
        if hasattr(self, '_section_views'): views.extend(self._section_views)
        if hasattr(self, '_grids'): views.extend(list(self._grids.values()))
        if hasattr(self, '_ribbons'): views.extend(list(self._ribbons.values()))
        return views

    def get_grid_layout_info(self, vp_w: int):
        """Returns (cols, row_h, spacing) for grid sections."""
        sp = UIConstants.GRID_GUTTER

        # We account for a bit of horizontal padding to avoid tight fits
        effective_w = UIConstants.CARD_WIDTH + sp
        cols = max(1, vp_w // effective_w)

        # Use the centralized height helper - disable progress space for feeds
        row_h = UIConstants.get_card_height(self._show_labels, reserve_progress_space=False) + sp

        return cols, row_h, sp

    def get_ribbon_height(self) -> int:
        """Returns consistent height for ribbon sections."""
        # Use the centralized metric from UIConstants
        scrollbar_h = UIConstants.SCROLLBAR_SIZE
        # Feed ribbons NEVER show progress bars
        card_h = UIConstants.get_card_height(self._show_labels, reserve_progress_space=False)

        # Ribbon height = Card + Gutter + Scrollbar
        return card_h + UIConstants.RIBBON_SCROLLBAR_GUTTER + scrollbar_h
    def update_header_margins(self, scroll_bar):
        """Standardized helper to update header margins for scrollbar awareness."""
        if not scroll_bar: return

        sb_width = scroll_bar.width() if scroll_bar.isVisible() else 0
        header_margin = sb_width + UIConstants.scale(10)

        from comiccatcher.ui.components.section_header import SectionHeader
        from comiccatcher.ui.components.collapsible_section import CollapsibleSection

        for hdr in self.findChildren(SectionHeader):
            hdr.set_right_margin(header_margin)
        for section in self.findChildren(CollapsibleSection):
            section.set_right_margin(header_margin)

    def gather_context_pubs(self, model: FeedBrowserModel) -> List[object]:

        """Collects raw publication objects from a model to provide reading context."""
        context_pubs = []
        # Support both sparse items (dict) and logical items (list)
        if hasattr(model, '_sparse_items'):
            for row in sorted(model._sparse_items.keys()):
                itm = model._sparse_items[row]
                if itm and itm.raw_pub:
                    context_pubs.append(itm.raw_pub)
        return context_pubs

    def toggle_selection_mode(self, enabled: bool):
        """Standardized selection mode toggle for sub-views."""
        self._selection_mode = enabled
        mode = QAbstractItemView.SelectionMode.MultiSelection if enabled else QAbstractItemView.SelectionMode.NoSelection
        
        # Collect all active views (grids, ribbons, or paged sections)
        views = []
        if hasattr(self, '_section_views'):
            views = self._section_views
        
        if hasattr(self, '_grids'):
            views.extend(list(self._grids.values()))
        if hasattr(self, '_ribbons'):
            views.extend(list(self._ribbons.values()))
            
        for view in views:
            if hasattr(view, 'setSelectionMode'):
                view.setSelectionMode(mode)
                if not enabled:
                    view.clearSelection()
                
                # Connect/Disconnect selection changes
                try: 
                    view.selectionModel().selectionChanged.disconnect(self.selection_changed.emit)
                except: 
                    pass
                
                if enabled:
                    view.selectionModel().selectionChanged.connect(self.selection_changed.emit)
            
            if hasattr(view, 'viewport'):
                view.viewport().update()

    def get_selected_items(self) -> List[FeedItem]:
        """Returns a list of all currently selected FeedItems across all internal views."""
        selected = []
        views = []
        if hasattr(self, '_section_views'):
            views.extend(self._section_views)
        
        if hasattr(self, '_grids'):
            views.extend(list(self._grids.values()))
        if hasattr(self, '_ribbons'):
            views.extend(list(self._ribbons.values()))
            
        for view in views:
            model = view.model()
            if not model: continue
            for index in view.selectionModel().selectedIndexes():
                # For FeedBrowserModel, the item is stored in UserRole + 1
                item = index.data(Qt.ItemDataRole.UserRole + 1)
                if isinstance(item, FeedItem):
                    selected.append(item)
        return selected
