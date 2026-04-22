# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

from PyQt6.QtWidgets import QListView, QFrame, QAbstractItemView, QApplication
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QPoint, QTimer, QElapsedTimer
from comiccatcher.ui.theme_manager import UIConstants

class BaseCardRibbon(QListView):
    """
    Standardized horizontal scrolling ribbon for cards.
    Handles consistent flow, wrapping, and dynamic height sizing.
    Supports pan-scrolling with inertia.
    """
    def __init__(self, parent=None, show_labels=True, reserve_progress_space=True, card_size="medium"):
        super().__init__(parent)
        self._show_labels = show_labels
        self._reserve_progress_space = reserve_progress_space
        self._card_size = card_size
        
        # Pan-scroll state
        self._is_dragging = False
        self._drag_start_pos = QPoint()
        self._drag_start_scroll = 0
        self._last_mouse_pos = QPoint()
        self._velocity = 0
        self._last_drag_time = QElapsedTimer()
        
        self._inertia_timer = QTimer(self)
        self._inertia_timer.setInterval(16) # ~60 FPS
        self._inertia_timer.timeout.connect(self._on_inertia_tick)
        
        # Standard configuration
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMouseTracking(True)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(False)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        
        # Eliminate all internal padding that could cause vertical overflow
        self.setContentsMargins(0, 0, 0, 0)
        
        from comiccatcher.ui.theme_manager import UIConstants
        s = UIConstants.scale
        self.setSpacing(s(10))
        self.setIconSize(QSize(UIConstants.get_card_width(card_size), UIConstants.get_card_height(show_labels, reserve_progress_space, card_size)))
        
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
        
        # Apply slim scrollbar style
        self._apply_scrollbar_style()
        
        # Suppress wheel events on the scrollbar itself so they bubble to the page
        self.horizontalScrollBar().installEventFilter(self)
        
        # Initial height
        self.update_ribbon_height()

    def eventFilter(self, source, event):
        """Ignore wheel events on the horizontal scrollbar so they bubble up to the vertical view."""
        from PyQt6.QtCore import QEvent
        if source is self.horizontalScrollBar() and event.type() == QEvent.Type.Wheel:
            event.ignore()
            return True # Stop the scrollbar from handling it
        return super().eventFilter(source, event)

    def _apply_scrollbar_style(self):
        """Applies a surgical QSS override to the horizontal scrollbar to make it slimmer."""
        from comiccatcher.ui.theme_manager import UIConstants, ThemeManager
        theme = ThemeManager.get_current_theme_colors()
        h = UIConstants.scale(UIConstants.RIBBON_SCROLLBAR_HEIGHT)
        radius = h // 2
        
        # We target ONLY this widget's horizontal scrollbar
        self.horizontalScrollBar().setStyleSheet(f"""
            QScrollBar:horizontal {{
                border: none;
                background: transparent;
                height: {h}px;
                margin: 0px;
            }}
            QScrollBar::handle:horizontal {{
                background: {theme['border']};
                min-width: {h * 4}px;
                border-radius: {radius}px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {theme['text_dim']};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
        """)

    @property
    def card_size(self):
        return self._card_size

    @card_size.setter
    def card_size(self, size: str):
        if self._card_size == size: return
        self._card_size = size
        self.setIconSize(QSize(UIConstants.get_card_width(size), 
                               UIConstants.get_card_height(self._show_labels, self._reserve_progress_space, size)))
        self.update_ribbon_height()
        
        # Sync delegate if it exists
        delegate = self.itemDelegate()
        if hasattr(delegate, 'card_size'):
            delegate.card_size = size
            
        self.viewport().update()
        self.doItemsLayout()

    @property
    def show_labels(self):
        return self._show_labels

    @show_labels.setter
    def show_labels(self, enabled: bool):
        if self._show_labels == enabled: return
        self._show_labels = enabled
        self.setIconSize(QSize(UIConstants.get_card_width(self._card_size), 
                               UIConstants.get_card_height(enabled, self._reserve_progress_space, self._card_size)))
        self.update_ribbon_height()
        
        # Sync delegate if it exists
        delegate = self.itemDelegate()
        if hasattr(delegate, 'show_labels'):
            delegate.show_labels = enabled
            
        self.viewport().update()
        self.doItemsLayout()

    def update_ribbon_height(self):
        """Calculates and sets the fixed height based on label visibility and slim scrollbar height."""
        from comiccatcher.ui.theme_manager import UIConstants
        h = UIConstants.get_card_height(self._show_labels, self._reserve_progress_space, self._card_size)
            
        # Use the pre-scaled ribbon scrollbar height
        scrollbar_h = UIConstants.RIBBON_SCROLLBAR_HEIGHT
        
        # Total height = Card + Gutter + Scrollbar
        total_h = h + UIConstants.RIBBON_SCROLLBAR_GUTTER + scrollbar_h
        
        self.setFixedHeight(total_h)
        self.setMinimumHeight(total_h)
        self.setMaximumHeight(total_h)
        
        # Ensure range is 0
        self.verticalScrollBar().setRange(0, 0)

    def setModel(self, model):
        super().setModel(model)
        self.update_ribbon_height()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = False
            self._drag_start_pos = event.pos()
            self._last_mouse_pos = event.pos()
            self._drag_start_scroll = self.horizontalScrollBar().value()
            self._velocity = 0
            self._inertia_timer.stop()
            self._last_drag_time.start()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle both the pointer cursor update and pan-scrolling."""
        if event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.pos().x() - self._drag_start_pos.x()
            
            # Start dragging only if threshold reached
            if not self._is_dragging and abs(delta) > QApplication.startDragDistance():
                self._is_dragging = True
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            
            if self._is_dragging:
                # Calculate instantaneous velocity for inertia
                dt = self._last_drag_time.restart()
                if dt > 0:
                    inst_v = (self._last_mouse_pos.x() - event.pos().x()) / (dt / 1000.0)
                    # Low pass filter for velocity
                    self._velocity = self._velocity * 0.7 + inst_v * 0.3
                
                self._last_mouse_pos = event.pos()
                self.horizontalScrollBar().setValue(self._drag_start_scroll - delta)
                return # Consume event to prevent item selection/click highlights

        # Normal cursor update when not dragging
        index = self.indexAt(event.pos())
        if index.isValid():
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._is_dragging:
            self._is_dragging = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            
            # Start inertia if velocity is significant
            if abs(self._velocity) > 100:
                self._inertia_timer.start()
            
            # Suppress the click by not calling super() for release
            # if we actually moved the view.
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def _on_inertia_tick(self):
        """Continuously scrolls the view based on velocity, with friction decay."""
        if abs(self._velocity) < 10:
            self._inertia_timer.stop()
            return
            
        # Move scrollbar
        sb = self.horizontalScrollBar()
        current = sb.value()
        # 16ms tick -> v * 0.016
        move = int(self._velocity * 0.016)
        sb.setValue(current + move)
        
        # Friction (decay)
        self._velocity *= 0.92
        
        # Stop if we hit boundaries
        if sb.value() == 0 or sb.value() == sb.maximum():
            self._inertia_timer.stop()

    def wheelEvent(self, event):
        """
        Ignore all wheel events so they bubble to the parent vertical scroll area.
        Ribbons are scrolled horizontally via pan-drag or the scrollbar only.
        """
        event.ignore()

    def itemFromIndex(self, index):
        """Helper for compatibility with QListWidget-style handlers."""
        model = self.model()
        if hasattr(model, 'itemFromIndex'):
            return model.itemFromIndex(index)
        # If it's a QStandardItemModel or similar, this works.
        # But FeedBrowserModel might not have it.
        return None

class FeedCardRibbon(BaseCardRibbon):
    """
    Specialized ribbon for Feed items.
    Encapsulates the FeedBrowserModel and FeedCardDelegate setup.
    """
    mini_detail_requested = pyqtSignal(object, object, object, object) # item, index, view, model

    def __init__(self, parent=None, image_manager=None, show_labels=True, 
                 reserve_progress_space=True, card_size="medium"):
        super().__init__(parent, show_labels, reserve_progress_space, card_size)
        self.image_manager = image_manager
        
        # Setup Model
        from comiccatcher.ui.components.feed_browser_model import FeedBrowserModel
        self._model = FeedBrowserModel()
        self.setModel(self._model)
        
        # Setup Delegate
        from comiccatcher.ui.components.feed_card_delegate import FeedCardDelegate
        self._delegate = FeedCardDelegate(self, self.image_manager, 
                                        show_labels=show_labels, 
                                        card_size=card_size)
        self.setItemDelegate(self._delegate)
        
        # Context Menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_custom_context_menu)
        
    def _on_custom_context_menu(self, pos):
        index = self.indexAt(pos)
        if not index.isValid(): return
        item = self._model.get_item(index.row())
        if not item: return
        self.mini_detail_requested.emit(item, index, self, self._model)
