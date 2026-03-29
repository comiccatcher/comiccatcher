from typing import Set, List
from PyQt6.QtWidgets import QWidget, QListView, QFrame, QAbstractItemView
from PyQt6.QtCore import Qt, pyqtSignal
from ui.theme_manager import UIConstants
from ui.components.feed_browser_model import FeedBrowserModel
from ui.components.feed_card_delegate import FeedCardDelegate

from models.feed_page import FeedPage, FeedSection, FeedItem

class BaseFeedSubView(QWidget):
    """
    Common base class for Feed sub-views (Paged and Scrolled).
    Centralizes shared UI configuration, signals, and context gathering logic.
    """
    item_clicked = pyqtSignal(FeedItem, list) # item, context_pubs
    navigate_requested = pyqtSignal(str, str, bool) # url, title, replace

    def __init__(self, image_manager, collapsed_sections: Set[str], parent=None):
        super().__init__(parent)
        self.image_manager = image_manager
        self._collapsed_sections = collapsed_sections
        self._show_labels = True

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

    def get_grid_layout_info(self, vp_w: int):
        """Returns (cols, row_h, spacing) for grid sections."""
        sp = UIConstants.GRID_GUTTER
        
        # We account for a bit of horizontal padding to avoid tight fits
        effective_w = UIConstants.CARD_WIDTH + sp
        cols = max(1, vp_w // effective_w)
        
        if self._show_labels:
            row_h = UIConstants.CARD_HEIGHT + sp
        else:
            row_h = UIConstants.CARD_COVER_HEIGHT + UIConstants.CARD_SPACING + sp
            
        return cols, row_h, sp

    def get_ribbon_height(self) -> int:
        """Returns consistent height for ribbon sections."""
        # Use the centralized metric from UIConstants
        scrollbar_h = UIConstants.SCROLLBAR_SIZE
        
        if self._show_labels:
            return UIConstants.CARD_HEIGHT + scrollbar_h + UIConstants.GRID_SPACING
        return (UIConstants.CARD_COVER_HEIGHT
                + UIConstants.CARD_PADDING * 2 + scrollbar_h
                + UIConstants.GRID_SPACING)

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

    def _on_cover_request(self, url: str):
        """Pass-through to the parent FeedBrowser's cover manager."""
        if hasattr(self.parent(), '_on_cover_request'):
            self.parent()._on_cover_request(url)
