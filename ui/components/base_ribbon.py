from PyQt6.QtWidgets import QListView, QFrame, QAbstractItemView
from PyQt6.QtCore import Qt, QSize
from ui.theme_manager import UIConstants

class BaseCardRibbon(QListView):
    """
    Standardized horizontal scrolling ribbon for cards.
    Handles consistent flow, wrapping, and dynamic height sizing.
    """
    def __init__(self, parent=None, show_labels=True):
        super().__init__(parent)
        self._show_labels = show_labels
        
        # Standard configuration
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMouseTracking(True)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(False)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        
        # Eliminate all internal padding that could cause vertical overflow
        self.setContentsMargins(0, 0, 0, 0)
        
        from ui.theme_manager import UIConstants
        s = UIConstants.scale
        self.setSpacing(s(10))
        self.setIconSize(QSize(s(120), s(180)))
        
        # Scroll policies
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        
        # Selection behavior
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        
        # Force the vertical scrollbar range to 0 and lock it permanently
        self.verticalScrollBar().setRange(0, 0)
        self.verticalScrollBar().rangeChanged.connect(lambda: self.verticalScrollBar().setRange(0, 0))
        
        # Initial height
        self.update_ribbon_height()

    @property
    def show_labels(self):
        return self._show_labels

    @show_labels.setter
    def show_labels(self, enabled: bool):
        self._show_labels = enabled
        self.update_ribbon_height()
        
        # Sync delegate if it exists
        delegate = self.itemDelegate()
        if hasattr(delegate, 'show_labels'):
            delegate.show_labels = enabled
            
        self.viewport().update()
        self.doItemsLayout()

    def update_ribbon_height(self):
        """Calculates and sets the fixed height based on label visibility and OS scrollbar height."""
        from ui.theme_manager import UIConstants
        if self._show_labels:
            h = UIConstants.CARD_HEIGHT
        else:
            h = UIConstants.CARD_COVER_HEIGHT + (UIConstants.CARD_PADDING * 2)
            
        # Use the centralized metric from UIConstants
        scrollbar_h = UIConstants.SCROLLBAR_SIZE
        
        # Total height = Content + Scrollbar + Themed Spacing (breathing room)
        total_h = h + scrollbar_h + UIConstants.GRID_SPACING
        
        self.setFixedHeight(total_h)
        self.setMinimumHeight(total_h)
        self.setMaximumHeight(total_h)
        
        # Ensure range is 0
        self.verticalScrollBar().setRange(0, 0)

    def setModel(self, model):
        super().setModel(model)
        self.update_ribbon_height()

    def mouseMoveEvent(self, event):
        """Change cursor to pointing hand only when hovering over a valid item."""
        index = self.indexAt(event.pos())
        if index.isValid():
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def wheelEvent(self, event):
        """Redirect vertical scroll events to parent to prevent internal jitter."""
        if event.angleDelta().y() != 0:
            # This is a vertical scroll. We want the main scroll area to handle it.
            # QListView's default wheelEvent might 'eat' it even if policy is AlwaysOff.
            event.ignore()
            return
        super().wheelEvent(event)

    def itemFromIndex(self, index):
        """Helper for compatibility with QListWidget-style handlers."""
        model = self.model()
        if hasattr(model, 'itemFromIndex'):
            return model.itemFromIndex(index)
        # If it's a QStandardItemModel or similar, this works.
        # But FeedBrowserModel might not have it.
        return None
