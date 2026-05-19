# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

"""
BaseReaderView — shared comic reader UI for OPDS and local CBZ sources.

Features:
  - Auto-hiding header / footer overlays (mouse-activity timer)
  - Page slider with on-demand thumbnail previews (toggleable)
  - Fit modes: Fit Page, Fit Width, Fit Height, 1:1
  - Page layout: 1-page, 2-page spread, or Auto (viewport-aspect-driven)
  - LtR / RtL reading direction (flips arrow-key and click-zone behaviour)
  - Mouse-wheel page navigation (passthrough in scroll modes)
  - Click-zone navigation: left third = prev, right third = next, centre = toggle overlays
  - Cursor auto-hide after inactivity
  - Keyboard: arrows, Space, PgUp/Dn, Home/End, Escape, F (fit), R (dir), L (layout)
  - Fullscreen: F11 / ⛶ button; Escape exits fullscreen before exiting reader
"""

from __future__ import annotations
import asyncio
import enum
from typing import Optional, Callable, Any

from PyQt6.QtCore import (
    Qt, QEvent, QPoint, QTimer, QSize, QRectF, QPropertyAnimation, 
    pyqtProperty, QVariantAnimation, QEasingCurve, QPointF, QAbstractAnimation,
    QParallelAnimationGroup
)
from PyQt6.QtGui import QKeyEvent, QPainter, QPixmap, QAction, QActionGroup, QColor, QCloseEvent, QLinearGradient, QBrush, QTransform, QPen
from PyQt6.QtWidgets import (
    QFrame, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView,
    QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget, QMenu,
    QGraphicsDropShadowEffect, QApplication, 
    QColorDialog, QPinchGesture, QGestureEvent, QGraphicsRectItem
)

import sys
import os
import time
from comiccatcher.logger import get_logger
from comiccatcher.api.image_manager import ImageManager
from comiccatcher.ui.theme_manager import ThemeManager, UIConstants, THEMES
from comiccatcher.ui.components.mini_detail_popover import MiniDetailPopover
from comiccatcher.ui.components.nav_indicator import NavIndicator
from comiccatcher.ui.components.popover_mixin import BubbleMixin
from comiccatcher.ui.win_utils import apply_windows_popover_fix

logger = get_logger("ui.base_reader")
input_logger = get_logger("input")
cont_logger = get_logger("cont")
phys_logger = get_logger("phys")

# ---------------------------------------------------------------------------

# Fit mode
# ---------------------------------------------------------------------------

class FitMode(enum.Enum):
    FIT_PAGE   = "fit_page"
    FIT_WIDTH  = "fit_width"
    FIT_HEIGHT = "fit_height"
    ORIGINAL   = "original"
    CUSTOM     = "custom"


_FIT_LABELS = {
    FitMode.FIT_PAGE:   "Fit to Window",
    FitMode.FIT_WIDTH:  "Full Width",
    FitMode.FIT_HEIGHT: "Full Height",
    FitMode.ORIGINAL:   "Original Size",
    FitMode.CUSTOM:     "Custom Zoom",
}
_FIT_CYCLE = [FitMode.FIT_PAGE, FitMode.FIT_WIDTH, FitMode.FIT_HEIGHT, FitMode.ORIGINAL]


# ---------------------------------------------------------------------------
# Page layout
# ---------------------------------------------------------------------------

class PageLayout(enum.Enum):
    SINGLE = "single"
    DOUBLE = "double"
    AUTO   = "auto"
    CONTINUOUS = "continuous"


_LAYOUT_LABELS = {
    PageLayout.SINGLE: "Single Page",
    PageLayout.DOUBLE: "Two-Page Spread",
    PageLayout.AUTO:   "Automatic Layout",
    PageLayout.CONTINUOUS: "Continuous Vertical",
}
_LAYOUT_CYCLE = [PageLayout.SINGLE, PageLayout.DOUBLE, PageLayout.AUTO]


# Trackpad Constants
# ---------------------------------------------------------------------------

class TrackpadConstants:
    PINCH_COOLDOWN_MS = 250         # ms to ignore wheel events after a pinch ends
    GESTURE_RESET_MS = 300          # ms of inactivity to assume a new gesture started
    
    INCREMENTAL_SENSITIVITY = 0.8   # Zoom multiplier for incremental delta systems
    INCREMENTAL_DEADZONE = 0.001    # Min delta to trigger incremental zoom
    
    ABSOLUTE_MIN = 0.7              # Min value for absolute ratio mode detection
    ABSOLUTE_MAX = 1.3              # Max value for absolute ratio mode detection
    
    MIN_SCALE_FALLBACK = 0.1        # Fallback scale if dimensions are invalid
    DEFAULT_ASPECT_RATIO = 1.5      # Average comic page aspect ratio (H/W)
    
    SCALE_EPSILON = 0.0001          # Minimum scale change to apply
    ZOOM_LEVELS = [1.0, 1.5, 2.5, 4.0] # Predefined zoom levels for cycling
    CONTINUOUS_VIEW_PAGES = 1.5      # Number of page-heights to fit in viewport at min zoom


class KineticConstants:
    # PPS (Pixels Per Second) Model
    DECAY_FACTOR = 0.96             # Velocity multiplier per 16ms tick
    MIN_VELOCITY_PPS = 50.0         # Pixels per second below which we stop
    TRACKPAD_VEL_WEIGHT = 0.4       # Weight of newest sample (lower = smoother/heavier)
    TICK_MS = 16                    # ~60 FPS update interval
    CLICK_DEADZONE = 5              # Manhattan length to distinguish click vs drag
    WHEEL_STEP_MULTIPLIER = 0.8     # Sensitivity for non-pixel-based wheels
    MOUSE_DRAG_BOOST = 1.0          # 1:1 physical tracking
    VELOCITY_STALE_MS = 100         # Time after which velocity is considered zero if no movement
    MIN_DRAG_DT = 0.008             # Min time delta in seconds to guard mouse velocity calculations


class OverscrollConstants:
    MAX_LOGICAL_STRETCH = 250       # Max pixels to buffer past the edge
    PULL_DAMPING = 0.35             # Multiplier for input movement while overscrolled
    VISUAL_DAMPING = 0.35           # Multiplier for the final scene translation
    MOMENTUM_FRICTION = 0.80         # Decay factor while overscrolled (applied every tick)
    SNAP_BACK_MS = 250              # Duration of the snap-back animation
    SNAP_EASING = QEasingCurve.Type.OutQuad
    PULL_THRESHOLD = 150            # Distance past edge to trigger a page turn


# Background mode
# ---------------------------------------------------------------------------

class BackgroundMode(enum.Enum):
    BLACK   = "black"
    WHITE   = "white"
    CUSTOM  = "custom"
    MEDIAN  = "median"
    VIBRANT   = "vibrant"
    CONTRAST  = "contrast"
    SMOOTH    = "smooth"
    GRADIENT  = "gradient"
    CLEAN     = "clean"
    VIBE      = "vibe"
    VIBE_GRADIENT = "vibe_gradient"
    TEMPORAL_VIBE = "temporal_vibe"


_BG_LABELS = {
    BackgroundMode.BLACK: "Black",
    BackgroundMode.WHITE: "White",
    BackgroundMode.CUSTOM: "Custom Color...",
    BackgroundMode.MEDIAN: "Sampling: Edge Median",
    BackgroundMode.VIBRANT: "Sampling: Edge Vibrant",
    BackgroundMode.CONTRAST: "Sampling: Edge Contrast Frame",
    BackgroundMode.SMOOTH: "Sampling: Edge Temporal Mean",
    BackgroundMode.GRADIENT: "Sampling: Edge 4-Way Gradient",
    BackgroundMode.CLEAN: "Sampling: Edge Clean Margin",
    BackgroundMode.VIBE: "Sampling: Vibe Solid",
    BackgroundMode.VIBE_GRADIENT: "Sampling: Vibe Gradient",
    BackgroundMode.TEMPORAL_VIBE: "Sampling: Temporal Vibe",
}


def _compose_spread(pm1: QPixmap, pm2: QPixmap) -> QPixmap:
    """Composite two pages side-by-side, centred vertically, on a transparent canvas."""
    total_w = pm1.width() + pm2.width()
    max_h   = max(pm1.height(), pm2.height())
    result  = QPixmap(total_w, max_h)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.drawPixmap(0,           (max_h - pm1.height()) // 2, pm1)
    painter.drawPixmap(pm1.width(), (max_h - pm2.height()) // 2, pm2)
    painter.end()
    return result


# ---------------------------------------------------------------------------
# Adjacent Book Popover
# ---------------------------------------------------------------------------

class AdjacentBookPopover(QFrame, BubbleMixin):
    """
    A popover that appears when reaching the start/end of a book,
    suggesting the next or previous book in the current context.
    """
    def __init__(self, parent=None, on_clicked: Callable[[], None] = None):
        super().__init__(parent)
        self.on_clicked = on_clicked
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        s = UIConstants.scale
        # Room for the arrow in the margins
        self.setFixedWidth(s(340))
        self.setFixedHeight(s(440))
        
        self.arrow_side = None # "left", "right", "top", "bottom"
        self.direction = 0
        
        # Main container (now just a layout holder, styling moved to paintEvent)
        self.container = QFrame(self)
        self.container.setObjectName("adjacent_container")
        self.container.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(s(30), s(30), s(30), s(30))
        self.root_layout.addWidget(self.container)
        
        self.inner_layout = QVBoxLayout(self.container)
        self.inner_layout.setContentsMargins(s(20), s(20), s(20), s(20))
        self.inner_layout.setSpacing(s(15))
        
        # Header (e.g. Next Comic)
        self.hdr_label = QLabel("")
        self.hdr_label.setObjectName("header_label")
        self.hdr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.inner_layout.addWidget(self.hdr_label)
        
        # Cover
        self.cover_label = QLabel()
        self.cover_label.setFixedSize(s(180), s(270))
        self.cover_label.setScaledContents(True)
        self.inner_layout.addWidget(self.cover_label, 0, Qt.AlignmentFlag.AlignCenter)
        
        # Title
        self.title_label = QLabel("")
        self.title_label.setObjectName("title_label")
        self.title_label.setWordWrap(True)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.inner_layout.addWidget(self.title_label)

        self.reapply_theme()

    def reapply_theme(self):
        """Standardized method to update styles when theme changes."""
        self.theme = ThemeManager.get_current_theme_colors()
        s = UIConstants.scale
        
        self.container.setStyleSheet(f"""
            QFrame#adjacent_container {{
                background-color: transparent;
                border: none;
            }}
            QLabel {{ color: {self.theme['content_primary']}; background: transparent; }}
            QLabel#header_label {{ font-weight: bold; font-size: {s(14)}px; color: {self.theme['brand_primary']}; }}
            QLabel#title_label {{ font-weight: bold; font-size: {s(15)}px; color: {self.theme['content_primary']}; }}
        """)
        self.cover_label.setStyleSheet(f"border: {max(1, s(1))}px solid {self.theme['layout_divider']}; border-radius: {s(4)}px; background: {self.theme['bg_main']};")
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        if sys.platform == "win32":
            apply_windows_popover_fix(self.winId())
            QTimer.singleShot(5, lambda: apply_windows_popover_fix(self.winId()))
        
    def set_arrow(self, side: str):
        self.arrow_side = side
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        self.paint_bubble(
            painter, 
            QRectF(self.rect()), 
            QRectF(self.container.geometry()), 
            self.theme, 
            self.arrow_side
        )

    def populate(self, direction: int, title: str, cover: QPixmap):
        self.direction = direction
        if direction > 0:
            self.hdr_label.setText("Next Comic")
        else:
            self.hdr_label.setText("Previous Comic")
            
        self.title_label.setText(title)
        if cover and not cover.isNull():
            self.cover_label.setPixmap(cover)
        else:
            self.cover_label.setText("No Cover")
            
    def mousePressEvent(self, event):
        # Only trigger transition if clicking INSIDE the container
        if self.container.geometry().contains(event.pos()):
            if self.on_clicked:
                self.on_clicked()
        
        self.hide()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        key = event.key()
        
        # Proper direction key triggers transition based on visual position.
        # This automatically handles RtL and Continuous modes correctly.
        should_trigger = False
        if self.arrow_side == "right" and key == Qt.Key.Key_Right:
            should_trigger = True
        elif self.arrow_side == "left" and key == Qt.Key.Key_Left:
            should_trigger = True
        elif self.arrow_side == "bottom" and (key == Qt.Key.Key_Down or key == Qt.Key.Key_PageDown):
            should_trigger = True
        elif self.arrow_side == "top" and (key == Qt.Key.Key_Up or key == Qt.Key.Key_PageUp):
            should_trigger = True
            
        if should_trigger:
            if self.on_clicked:
                self.on_clicked()
        
        self.hide()
        event.accept()

    def show_at(self, pos: QPoint):
        self.move(pos)
        self.show()


# ---------------------------------------------------------------------------
# Help Popover
# ---------------------------------------------------------------------------

class HelpPopover(QFrame):
    """
    A modal-ish popover displaying reader controls.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        s = UIConstants.scale
        self.setFixedWidth(s(450))
        
        self.container = QFrame(self)
        self.container.setObjectName("help_container")
        
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(s(30))
        shadow.setColor(QColor(0, 0, 0, 150))
        self.container.setGraphicsEffect(shadow)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(s(10), s(10), s(10), s(10))
        layout.addWidget(self.container)
        
        self.inner = QVBoxLayout(self.container)
        self.inner.setContentsMargins(s(25), s(25), s(25), s(25))
        self.inner.setSpacing(s(8))
        
        self.hdr = QLabel("Reader Controls")
        self.hdr.setObjectName("header")
        self.hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.inner.addWidget(self.hdr)
        self.inner.addSpacing(s(10))
        
        self._add_section("NAVIGATION")
        self._add_row("Left / Right", "Pan or Turn Page (LtR/RtL)")
        self._add_row("Up / Down", "Pan or Next / Prev Page")
        self._add_row("PgUp / PgDn", "Step Pan or Next / Prev Page")
        self._add_row("Enter / Return", "Toggle UI Overlays")
        self._add_row("I", "Show Book Information")
        self._add_row("M", "Show Reader Settings Menu")
        self._add_row("Home / End", "First / Last Page")
        self._add_row("[ / ]", "Previous / Next Book (Flow sensitive)")
        self._add_row("F / F11", "Toggle Fullscreen")
        self._add_row("Esc", "Exit Reader")
        
        self._add_section("ZOOM & PAN")
        self._add_row("Ctrl + Wheel", "Dynamic Zoom")
        self._add_row("+ / -", "Step Zoom")
        self._add_row("0", "Reset Zoom (Fit Page)")
        self._add_row("Double Click", "Cycle Zoom Levels")
        self._add_row("Click + Drag", "Pan when Zoomed In")
        
        self._add_section("FLOW & LAYOUT")
        self._add_row("R", "Cycle Reading Flow (LtR > RtL > Cont)")
        self._add_row("L", "Cycle Page Layout (Single > Double > Auto)")
        self._add_row("C", "Cycle Fit Mode (Fit > Width > Height > 1:1)")
        
        self._add_section("SMART SCROLL")
        self._add_row("Space / Wheel Dn", "Pan in flow direction, then page turn")
        self._add_row("Shift+Space / Up", "Pan opposite flow, then page turn")
        self._add_row("Page Edge", "Navigation bumper requires second press")

        self.inner.addSpacing(s(10))
        self.footer_label = QLabel("Click anywhere or press any key to close")
        self.footer_label.setObjectName("help_footer")
        self.footer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.inner.addWidget(self.footer_label)

        self.reapply_theme()

    def _add_row(self, key, desc):
        row = QHBoxLayout()
        k_lbl = QLabel(key)
        k_lbl.setObjectName("key")
        d_lbl = QLabel(desc)
        row.addWidget(k_lbl)
        row.addWidget(d_lbl, 1)
        self.inner.addLayout(row)

    def _add_section(self, text):
        lbl = QLabel(text)
        lbl.setObjectName("section")
        self.inner.addWidget(lbl)

    def reapply_theme(self):
        """Standardized method to update styles when theme changes."""
        theme = ThemeManager.get_current_theme_colors()
        s = UIConstants.scale
        
        self.container.setStyleSheet(f"""
            QFrame#help_container {{
                background-color: {theme['bg_header']};
                border: {max(1, s(2))}px solid {theme['brand_primary']};
                border-radius: {s(15)}px;
            }}
            QLabel {{ color: {theme['content_primary']}; background: transparent; font-size: {s(13)}px; }}
            QLabel#header {{ font-weight: bold; font-size: {s(18)}px; color: {theme['brand_primary']}; }}
            QLabel#section {{ font-weight: bold; font-size: {s(14)}px; color: {theme['brand_primary']}; margin-top: {s(10)}px; }}
            QLabel#key {{ font-family: monospace; font-weight: bold; color: {theme['content_primary']}; background: rgba(128,128,128,40); border-radius: {s(3)}px; padding: 0 {s(4)}px; }}
            QLabel#help_footer {{ color: {theme['content_secondary']}; font-style: italic; font-size: {s(11)}px; }}
        """)

    def mousePressEvent(self, event):
        self.hide()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        self.hide()
        event.accept()

    def show_at_center(self, parent_widget: QWidget):
        self.adjustSize()
        # Calculate global center of the parent
        global_top_left = parent_widget.mapToGlobal(QPoint(0, 0))
        parent_global_rect = QRectF(
            global_top_left.x(), 
            global_top_left.y(), 
            parent_widget.width(), 
            parent_widget.height()
        ).toRect()
            
        target_center = parent_global_rect.center()
        
        # Initial target position
        x = target_center.x() - self.width() // 2
        y = target_center.y() - self.height() // 2
        
        # Adjust to stay on screen
        screen = QApplication.screenAt(target_center) or QApplication.primaryScreen()
        if screen:
            screen_rect = screen.availableGeometry()
            # Clamp x
            x = max(screen_rect.left(), min(x, screen_rect.right() - self.width()))
            # Clamp y
            y = max(screen_rect.top(), min(y, screen_rect.bottom() - self.height()))
            
        self.move(x, y)
        self.show()


# ---------------------------------------------------------------------------
# Thumbnail slider
# ---------------------------------------------------------------------------

class ThumbnailSlider(QWidget):
    """
    A horizontal QSlider with a floating thumbnail popup that appears while
    the user hovers or drags over the slider track.

    The popup widget is parented to `popup_parent` (the reader window) so it
    can float above the footer overlay.
    """

    def __init__(self, popup_parent: QWidget):
        super().__init__(popup_parent)
        self._popup_parent = popup_parent
        self._cache: dict[int, QPixmap] = {}   # idx -> scaled thumbnail
        self._loading: set[int] = set()
        self._thumb_loader = None              # async callable: idx -> Optional[QPixmap]

        s = UIConstants.scale
        self.setFixedHeight(s(30))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # We use theme-aware colors for the slider
        self.slider.setObjectName("reader_slider")
        layout.addWidget(self.slider)

        # Popup label — child of popup_parent for correct z-order
        self._popup = QLabel(popup_parent)
        self._popup.setFixedSize(s(100), s(150))
        self._popup.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._popup.setStyleSheet(
            f"background: rgba(0,0,0,230); border: {max(1, s(1))}px solid #555; border-radius: {s(4)}px;"
            f"color: white; font-size: {s(11)}px;"
        )
        self._popup.setVisible(False)

        self.slider.installEventFilter(self)

    def set_thumb_loader(self, fn):
        """Set an async callable ``async def fn(idx) -> Optional[QPixmap]``."""
        self._thumb_loader = fn

    def clear(self):
        """Clear the thumbnail cache and loading state."""
        self._cache.clear()
        self._loading.clear()
        self._popup.setPixmap(QPixmap())
        self._popup.setText("")

    def store_thumb(self, idx: int, pixmap: QPixmap):
        if not pixmap.isNull():
            s = UIConstants.scale
            self._cache[idx] = pixmap.scaled(
                s(96), s(136),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

    def hide_popup(self):
        self._popup.setVisible(False)

    # ------------------------------------------------------------------ #

    def eventFilter(self, source, event):
        if source is self.slider:
            t = event.type()
            if t == QEvent.Type.MouseButtonPress:
                # Immediate jump to click position
                idx = self._page_at(event.position().x())
                self.slider.setValue(idx)
                self._show_at(event.position().x())
            elif t == QEvent.Type.MouseMove:
                self._show_at(event.position().x())
            elif t in (QEvent.Type.Leave, QEvent.Type.MouseButtonRelease):
                self._popup.setVisible(False)
        return super().eventFilter(source, event)

    def _page_at(self, x: float) -> int:
        mx = self.slider.maximum()
        if mx <= 0:
            return 0
        ratio = max(0.0, min(1.0, x / max(1, self.slider.width())))
        if self.slider.invertedAppearance():
            ratio = 1.0 - ratio
            
        # Evenly bucketize based on total pages (mx + 1)
        # Use int() for floor-based bucketing, ensuring every page has an equal-width zone.
        total = mx + 1
        idx = int(ratio * total)
        return max(0, min(idx, mx))

    def _show_at(self, x: float):
        idx = self._page_at(x)

        thumb = self._cache.get(idx)
        if thumb:
            self._popup.setPixmap(thumb)
            self._popup.setText("")
        else:
            self._popup.setPixmap(QPixmap())
            self._popup.setText(f"Page\n{idx + 1}")
            if self._thumb_loader and idx not in self._loading:
                asyncio.create_task(self._async_load(idx))

        # Position popup above the hover point in the parent's coordinate space
        s = UIConstants.scale
        pos_in_parent = self.slider.mapTo(self._popup_parent, QPoint(int(x), 0))
        px = max(0, min(pos_in_parent.x() - s(50),
                        self._popup_parent.width() - self._popup.width()))
        py = max(0, pos_in_parent.y() - self._popup.height() - s(10))
        self._popup.move(px, py)
        self._popup.setVisible(True)
        self._popup.raise_()

    async def _async_load(self, idx: int):
        if idx in self._loading:
            return
        self._loading.add(idx)
        try:
            pixmap = await self._thumb_loader(idx)
            if pixmap and not pixmap.isNull():
                self.store_thumb(idx, pixmap)
                # Refresh popup if it's currently showing this page
                if self._popup.isVisible():
                    thumb = self._cache.get(idx)
                    if thumb:
                        self._popup.setPixmap(thumb)
                        self._popup.setText("")
        except Exception:
            pass
        finally:
            self._loading.discard(idx)


# ---------------------------------------------------------------------------
# Mipmap Pixmap Item
# ---------------------------------------------------------------------------

class MipmapPixmapItem(QGraphicsPixmapItem):
    """
    A QGraphicsPixmapItem that dynamically swaps between full-resolution and 
    downscaled mipmaps based on the current view scale, improving visual quality 
    when zoomed out and reducing aliasing artifacts.
    """
    def __init__(self, pixmap=None):
        super().__init__()
        self._mipmaps: dict[float, QPixmap] = {}
        self._current_level = 1.0
        self._base_scale = 1.0
        self._base_width = 0
        self._base_height = 0
        self._task = None
        self._is_smooth = True
        self._last_known_view_scale = 1.0
        
        # Default to smooth for high quality comics
        self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        
        if pixmap:
            self.setPixmap(pixmap)

    def set_base_scale(self, scale: float):
        """Set a base scale (e.g. to normalize widths) that persists across mipmap updates."""
        self._base_scale = scale
        # Re-apply the scale using the current mipmap level
        self.setScale((1.0 / self._current_level) * self._base_scale)

    def set_smooth(self, is_smooth: bool):
        if self._is_smooth == is_smooth:
            return
        self._is_smooth = is_smooth
        if not is_smooth:
            self._current_level = 1.0
            if 1.0 in self._mipmaps:
                super().setPixmap(self._mipmaps[1.0])
                self.setScale(self._base_scale)
        else:
            if self.scene() and self.scene().views():
                view = self.scene().views()[0]
                self.update_mipmap_level(view.transform().m11())

    def setPixmap(self, pixmap: QPixmap):
        # Cancel any pending mipmap generation for a previous pixmap
        if self._task and not self._task.done():
            self._task.cancel()

        super().setPixmap(pixmap)
        self.setScale(self._base_scale)
        self._mipmaps.clear()
        self._current_level = 1.0
        
        if pixmap.isNull():
            self._base_width = 0
            self._base_height = 0
            return
            
        self._base_width = pixmap.width()
        self._base_height = pixmap.height()
        self._mipmaps[1.0] = pixmap

        # Dispatch background generation of mipmaps
        self._generate_mipmaps(pixmap.toImage())

    def _generate_mipmaps(self, qimage):
        import asyncio
        from PyQt6.QtCore import Qt

        qimage = qimage.copy()
        item_id = id(self)

        def scale_images():
            if qimage.isNull(): return None
            cont_logger.debug(f"MIPMAP [{item_id}]: Generating 0.5x and 0.25x for {qimage.width()}x{qimage.height()}")
            img50 = qimage.scaled(max(1, int(qimage.width() * 0.5)), max(1, int(qimage.height() * 0.5)), 
                                  Qt.AspectRatioMode.KeepAspectRatio, 
                                  Qt.TransformationMode.SmoothTransformation)
            img25 = qimage.scaled(max(1, int(qimage.width() * 0.25)), max(1, int(qimage.height() * 0.25)), 
                                  Qt.AspectRatioMode.KeepAspectRatio, 
                                  Qt.TransformationMode.SmoothTransformation)
            return img50, img25

        async def worker():
            try:
                res = await asyncio.to_thread(scale_images)
                if not res: return
                img50, img25 = res
                self._mipmaps[0.5] = QPixmap.fromImage(img50)
                self._mipmaps[0.25] = QPixmap.fromImage(img25)
                cont_logger.debug(f"MIPMAP [{item_id}]: Generation complete. Re-checking level for scale {self._last_known_view_scale:.3f}")
                # Apply if needed using the last known scale
                self.update_mipmap_level(self._last_known_view_scale)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Error generating mipmaps: {e}")

        self._task = asyncio.create_task(worker())


    @property
    def base_width(self) -> int: return self._base_width

    @property
    def base_height(self) -> int: return self._base_height

    def update_mipmap_level(self, view_scale: float):
        if not self._base_width or not self._base_height or not self._is_smooth:
            return
        
        self._last_known_view_scale = view_scale

        # Determine appropriate target mipmap level considering our base scale.
        # We check in descending order (largest to smallest) and pick the 
        # smallest level that is still >= our effective scale. 
        # This ensures we always downscale to the target size, never upscale
        # (which causes blurriness).
        effective_scale = view_scale * self._base_scale
        target_level = 1.0
        
        # If we are at or below 50% scale, 0.5x is a candidate
        if 0.50 in self._mipmaps and effective_scale <= 0.50:
            target_level = 0.50
            
        # If we are at or below 25% scale, 0.25x is a better candidate
        if 0.25 in self._mipmaps and effective_scale <= 0.25:
            target_level = 0.25

        item_id = id(self)
        if target_level != self._current_level:
            cont_logger.debug(f"MIPMAP [{item_id}]: SWAP {self._current_level} -> {target_level} (ViewScale={view_scale:.3f}, EffScale={effective_scale:.3f})")
            self._current_level = target_level
            pm = self._mipmaps[target_level]
            super().setPixmap(pm)
            
            # Re-enforce smoothing on the new pixmap
            t_mode = Qt.TransformationMode.SmoothTransformation if self._is_smooth else Qt.TransformationMode.FastTransformation
            self.setTransformationMode(t_mode)

            # Adjust internal scale to match the physical size of 1.0, preserving our base scale
            self.setScale((1.0 / target_level) * self._base_scale)
        else:
            # Verbose debug for no-change cases
            pass # cont_logger.debug(f"MIPMAP [{item_id}]: No swap needed. Level={self._current_level} (EffScale={effective_scale:.3f})")


# ---------------------------------------------------------------------------
# Base reader
# ---------------------------------------------------------------------------

class BaseReaderView(QWidget):
    """
    Shared reader base.  Subclasses implement:
      - ``async _load_page_pixmap(idx) -> Optional[QPixmap]``
      - ``async _do_prefetch(idx)``          (optional, default no-op)
      - ``_on_page_changed(idx)``            (optional hook, e.g. progression sync)
    """

    OVERLAY_HIDE_MS = 8000
    CURSOR_HIDE_MS  = 5000
    PREFETCH_AHEAD  = 3
    PREFETCH_BEHIND = 1
    
    # Zoom Settings
    ZOOM_STEP_IN = 1.05
    ZOOM_STEP_OUT = 0.95
    
    # Smart Panning Settings
    SMART_PAN_STEP_H_PCT = 0.15
    SMART_PAN_STEP_V_PCT = 0.4
    SMART_PAN_SKIP_THRESHOLD_H_PCT = 0.1
    SMART_PAN_SKIP_THRESHOLD_V_PCT = 0.05
    
    # Interaction Settings
    CLICK_ZONE_PCT = 0.20 # Percentage of width for side page-turn zones
    CLICK_GUARD_MS = 150  # Max delay to distinguish single/double click

    def __init__(
        self,
        on_exit,        image_manager: ImageManager = None, 
        on_title_clicked: Callable[[], None] = None,
        on_get_adjacent: Callable[[int], Any] = None,
        on_transition: Callable[[Any], None] = None,
        config_manager=None
    ):
        super().__init__()
        self.on_exit = on_exit
        self.on_title_clicked = on_title_clicked
        self.on_get_adjacent = on_get_adjacent
        self.on_transition = on_transition
        self.config_manager = config_manager

        self._index   = 0
        self._total   = 0
        self._bumper_key = None # Tracks if we hit a boundary to require a second press
        
        # Load persisted settings
        self._fit_mode = FitMode(config_manager.get_reader_fit_mode()) if config_manager else FitMode.FIT_PAGE
        
        flow = config_manager.get_reader_flow() if config_manager else "ltr"
        self._rtl = (flow == "rtl")
        
        if flow == "continuous":
            self._page_layout = PageLayout.CONTINUOUS
        else:
            self._page_layout = PageLayout(config_manager.get_reader_layout()) if config_manager else PageLayout.SINGLE

        self._overlays_visible = True
        self._auto_hide_controls = config_manager.get_reader_auto_hide_controls() if config_manager else True
        self._slider_dragging  = False
        self._thumb_visible    = config_manager.get_reader_thumbs_visible() if config_manager else True
        
        # Background color settings
        self._bg_mode = BackgroundMode(config_manager.get_reader_bg_mode()) if config_manager else BackgroundMode.BLACK
        self._custom_bg_color = QColor(config_manager.get_reader_bg_color()) if config_manager else QColor(Qt.GlobalColor.black)
        self._current_bg_color = QColor(Qt.GlobalColor.black) # Computed color
        
        self._bg_anim = QPropertyAnimation(self, b"bg_color")
        self._bg_anim.setDuration(400) # 400ms for smooth transition
        
        self._continuous_items: dict[int, MipmapPixmapItem] = {}
        self._continuous_y_offsets: dict[int, float] = {}
        self._continuous_strip_width: float = 1000.0
        self._continuous_min_y: float = 0.0
        self._continuous_max_y: float = 0.0
        self._continuous_loading: set[int] = set()
        self._continuous_task_lock = asyncio.Lock()
        self._continuous_session_id: int = 0
        self._is_closing       = False
        self._ignore_next_release = False # Suppress click handling after a double-click
        
        # Image Filters (Session only)
        self._filter_deyellow = False
        
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._on_click_timer_timeout)
        self._pending_click_pos = None

        # Gesture / Pinch state
        self._is_pinching = False
        self._last_pinch_val = 0.0
        self._last_wheel_time = 0
        self._last_trackpad_time = 0
        self._pinch_cooldown_timer = QTimer(self)
        self._pinch_cooldown_timer.setSingleShot(True)
        self._pinch_cooldown_timer.timeout.connect(self._clear_pinching)

        # Custom kinetic scroller for continuous mode
        self._custom_scroll_velocity_y = 0.0
        self._custom_scroll_velocity_x = 0.0
        self._custom_scroll_y = 0.0 # Logical scroll position
        self._custom_scroll_x = 0.0
        self._last_drag_y = None
        self._last_drag_x = None
        self._last_drag_time = 0
        self._kinetic_timer = QTimer(self)
        self._kinetic_timer.setInterval(KineticConstants.TICK_MS)
        self._kinetic_timer.timeout.connect(self._on_kinetic_tick)

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Meta Popover
        self.meta_popover = MiniDetailPopover(self)
        
        # Help Popover
        self.help_popover = HelpPopover(self)
        
        # Adjacent Popover
        self.adjacent_popover = AdjacentBookPopover(self, on_clicked=self._on_adjacent_clicked)
        self._current_adjacent_ref = None


        # --- Graphics view (fills the whole widget) ---
        self.scene = QGraphicsScene()
        self.view  = QGraphicsView(self.scene)
        self.view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.view.setStyleSheet("border: none; background-color: transparent;")
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setMouseTracking(True)
        self.view.viewport().setMouseTracking(True)
        self.view.viewport().setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self._is_transforming = False
        self._overscroll_x = 0.0
        self._overscroll_y = 0.0
        self._snap_anim = None

        # --- Graphics view (fills the whole widget) ---
        self.scene = QGraphicsScene()
        
        # content_container holds all pages to allow for visual overscroll translation
        self.content_container = QGraphicsRectItem()
        self.content_container.setPen(QPen(Qt.PenStyle.NoPen))
        self.scene.addItem(self.content_container)

        self.view  = QGraphicsView(self.scene)
        self.view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.view.setStyleSheet("border: none; background-color: transparent;")
        
        # Scrollbars are permanently hidden for a native feel; range is still tracked internally.
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.view.setMouseTracking(True)
        self.view.viewport().setMouseTracking(True)
        self.view.viewport().setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self._mouse_press_pos = None
        self._zoom_cycle_idx = 0

        self.pixmap_item = MipmapPixmapItem()
        self.pixmap_item.setParentItem(self.content_container)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.view)

        # --- Header overlay ---
        self.header = QFrame(self)
        s = UIConstants.scale
        self.header.setFixedHeight(s(60))
        hdr = QHBoxLayout(self.header)
        hdr.setContentsMargins(s(10), s(5), s(10), s(5))
        hdr.setSpacing(s(15))

        self.btn_back = QPushButton()
        self.btn_back.setFixedSize(UIConstants.READER_BTN_SIZE, UIConstants.READER_BTN_SIZE)
        self.btn_back.setIconSize(QSize(UIConstants.READER_ICON_SIZE, UIConstants.READER_ICON_SIZE))
        self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back.setToolTip("Exit Reader")
        self.btn_back.clicked.connect(self._do_exit)

        self.title_label = QLabel("")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setTextFormat(Qt.TextFormat.RichText)
        self.title_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.title_label.mousePressEvent = lambda e: self._on_title_pressed(e)

        self.zoom_label = QLabel("")
        self.zoom_label.setFixedWidth(UIConstants.scale(60))
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        # Only show zoom level if debug is on
        is_debug = bool(os.environ.get("DEBUG"))
        self.zoom_label.setVisible(is_debug)

        self.btn_settings = QPushButton()
        self.btn_settings.setFixedSize(UIConstants.READER_BTN_SIZE, UIConstants.READER_BTN_SIZE)
        self.btn_settings.setIconSize(QSize(UIConstants.READER_ICON_SIZE + UIConstants.scale(2), UIConstants.READER_ICON_SIZE + UIConstants.scale(2)))
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.setToolTip("Reader Settings")
        self.settings_menu = QMenu(self)
        self.btn_settings.setMenu(self.settings_menu)
        self._update_settings_menu()

        hdr.addWidget(self.btn_back)
        hdr.addWidget(self.title_label, 1)
        hdr.addWidget(self.zoom_label)
        hdr.addWidget(self.btn_settings)

        self.counter_label = QLabel("0 / 0")
        self.counter_label.setFixedWidth(UIConstants.scale(95))
        self.counter_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
        )

        # --- Footer overlay ---
        self.footer = QFrame(self)
        ftr = QVBoxLayout(self.footer)
        s = UIConstants.scale
        ftr.setContentsMargins(s(10), s(6), s(10), s(8))
        ftr.setSpacing(s(5))

        slider_row = QHBoxLayout()
        slider_row.setSpacing(s(10))
        
        self.thumb_slider = ThumbnailSlider(self)
        self.thumb_slider.setStyleSheet("background: transparent; border: none;")
        self._update_slider_direction()
        self.thumb_slider.slider.sliderPressed.connect(self._on_slider_pressed)
        self.thumb_slider.slider.sliderReleased.connect(self._on_slider_released)
        self.thumb_slider.slider.valueChanged.connect(self._on_slider_value_changed)
        
        slider_row.addWidget(self.counter_label)
        slider_row.addWidget(self.thumb_slider)
        ftr.addLayout(slider_row)

        for b in (self.btn_back, self.btn_settings):
            b.setObjectName("reader_button")
            b.style().unpolish(b)
            b.style().polish(b)

        # --- Timers ---
        self._overlay_timer = QTimer(self)
        self._overlay_timer.setSingleShot(True)
        self._overlay_timer.setInterval(self.OVERLAY_HIDE_MS)
        self._overlay_timer.timeout.connect(self._hide_overlays)

        self._cursor_timer = QTimer(self)
        self._cursor_timer.setSingleShot(True)
        self._cursor_timer.setInterval(self.CURSOR_HIDE_MS)
        self._cursor_timer.timeout.connect(self._hide_cursor)

        self.grabGesture(Qt.GestureType.PinchGesture)
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents)

        self.view.viewport().installEventFilter(self)
        self.view.viewport().setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents)
        self.view.installEventFilter(self)
        self.header.installEventFilter(self)
        self.footer.installEventFilter(self)
        for b in (self.btn_back, self.btn_settings):
            b.installEventFilter(self)
        self.installEventFilter(self)
        
        self.view.verticalScrollBar().valueChanged.connect(self._on_vscroll_changed)
        self.view.horizontalScrollBar().valueChanged.connect(self._on_hscroll_changed)

        self._nav_pull_x = 0.0
        self.nav_left = NavIndicator(self.view, direction="left")
        self.nav_right = NavIndicator(self.view, direction="right")
        self.nav_left.raise_()
        self.nav_right.raise_()

        self._bump_activity()

        # Initial theme application
        QTimer.singleShot(0, self.reapply_theme)

    @pyqtProperty(QColor)
    def bg_color(self) -> QColor:
        return self._current_bg_color

    @bg_color.setter
    def bg_color(self, color: QColor):
        self._current_bg_color = color
        self._apply_background_style()

    def _apply_background_style(self):
        """Actually apply the color/gradient to the widget and view."""
        if not self._current_bg_color:
            return
        
        color = self._current_bg_color
        
        effective_mode = self._bg_mode
        if self._page_layout == PageLayout.CONTINUOUS and effective_mode not in (BackgroundMode.BLACK, BackgroundMode.WHITE, BackgroundMode.CUSTOM):
            effective_mode = BackgroundMode.BLACK
            
        is_gradient = effective_mode in (BackgroundMode.GRADIENT, BackgroundMode.VIBE_GRADIENT) and hasattr(self, '_current_bg_gradient')
        
        if is_gradient:
            grad = self._current_bg_gradient
            # CSS doesn't easily support complex multi-way QGradients, 
            # so we'll just use the view's background brush for the gradient.
            self.view.setBackgroundBrush(QBrush(grad))
            # Use top color for shell to prevent major contrast clash
            bg_name = grad.stops()[0][1].name()
            self.setStyleSheet(f"QWidget#reader_shell {{ background-color: {bg_name}; }}")
        else:
            self.view.setBackgroundBrush(QBrush(color))
            self.setStyleSheet(f"QWidget#reader_shell {{ background-color: {color.name()}; }}")

    def event(self, event: QEvent) -> bool:
        t = event.type()
        
        # Raw Touch Debugging
        if t in (QEvent.Type.TouchBegin, QEvent.Type.TouchUpdate, QEvent.Type.TouchEnd):
            pts = event.points()
            input_logger.debug(f"TOUCH {t.name}: points={len(pts)} {[p.id() for p in pts]}")

        # High-level Gesture Handling
        if t == QEvent.Type.Gesture:
            input_logger.debug(f"GESTURE EVENT: {[g.gestureType().name for g in event.gestures()]}")
            return self._handle_gesture(event)
            
        return super().event(event)

    def reapply_theme(self):
        """Standardized reader theme application."""
        theme = ThemeManager.get_current_theme_colors()
        s = UIConstants.scale
        
        # 1. Main Background - Dynamic based on settings
        self._update_background() # Ensure current color is computed
        
        # Use a specific ID to prevent CSS inheritance leakage into popups/menus
        self.setObjectName("reader_shell")
        self._apply_background_style()
        
        self.setStyleSheet(self.styleSheet() + f"""
            /* Explicitly force the menu to follow the global theme, 
               overriding the reader's shell inheritance. */
            QMenu {{
                background-color: {theme['bg_header']};
                color: {theme['content_primary']};
                border: {max(1, s(1))}px solid {theme['layout_divider']};
            }}
            QMenu::item:selected {{
                background-color: {theme['bg_item_hover']};
                color: {theme['content_primary']};
            }}
            QMenu::separator {{
                background-color: {theme['layout_divider']};
            }}
        """)
        
        # 2. Overlays (Header/Footer) - Always dark/translucent in reader
        overlay_qss = "background-color: rgba(0, 0, 0, 160); border: none;"
        self.header.setStyleSheet(overlay_qss)
        self.footer.setStyleSheet(overlay_qss)
        
        # 3. Text and Icons on Overlays - Must stay text_on_accent to contrast with dark overlay
        self.title_label.setStyleSheet(f"color: white; background: transparent; font-weight: bold; font-size: {s(15)}px;")
        self.counter_label.setStyleSheet(f"color: white; background: transparent; font-size: {UIConstants.READER_FONT_COUNTER}px; font-weight: bold;")
        self.zoom_label.setStyleSheet(f"color: white; background: transparent; font-size: {s(12)}px; font-weight: bold;")

        # Use pure white for reader overlays since they are hardcoded dark
        self.btn_back.setIcon(ThemeManager.get_icon("back", "#ffffff"))
        self.btn_settings.setIcon(ThemeManager.get_icon("menu", "#ffffff"))
        
        # 4. Sub-Popovers - These DO follow the global theme
        if hasattr(self, 'meta_popover'):
            self.meta_popover.reapply_theme()
        if hasattr(self, 'help_popover'):
            self.help_popover.reapply_theme()
        if hasattr(self, 'adjacent_popover'):
            self.adjacent_popover.reapply_theme()
            
        # 5. Menu - Follows theme
        self._update_settings_menu()

    def _update_background(self, pixmap: QPixmap = None):
        """Recompute the effective background color based on current mode and optionally a pixmap."""
        old_color = self._current_bg_color
        new_color = QColor(Qt.GlobalColor.black)

        # Force static black for dynamic modes in continuous flow, but allow White/Custom
        effective_mode = self._bg_mode
        if self._page_layout == PageLayout.CONTINUOUS and effective_mode not in (BackgroundMode.BLACK, BackgroundMode.WHITE, BackgroundMode.CUSTOM):
            effective_mode = BackgroundMode.BLACK

        if effective_mode == BackgroundMode.BLACK:
            new_color = QColor(Qt.GlobalColor.black)
        elif effective_mode == BackgroundMode.WHITE:
            new_color = QColor(Qt.GlobalColor.white)
        elif effective_mode == BackgroundMode.CUSTOM:
            new_color = self._custom_bg_color
        elif effective_mode in (
            BackgroundMode.MEDIAN, BackgroundMode.VIBRANT, BackgroundMode.CONTRAST,
            BackgroundMode.SMOOTH, BackgroundMode.GRADIENT, BackgroundMode.CLEAN,
            BackgroundMode.VIBE, BackgroundMode.VIBE_GRADIENT, BackgroundMode.TEMPORAL_VIBE
        ):
            target = pixmap
            if target is None or target.isNull():
                if self._page_layout == PageLayout.CONTINUOUS and self._continuous_items:
                    # Try to sample current index
                    if self._index in self._continuous_items:
                        target = self._continuous_items[self._index].pixmap()
                    else:
                        # Fallback to first available
                        first_idx = min(self._continuous_items.keys())
                        target = self._continuous_items[first_idx].pixmap()
                else:
                    target = self.pixmap_item.pixmap()
                
            if target and not target.isNull():
                if effective_mode in (BackgroundMode.VIBE, BackgroundMode.VIBE_GRADIENT, BackgroundMode.TEMPORAL_VIBE):
                    new_color = self._get_vibe_color(target, gradient=(effective_mode == BackgroundMode.VIBE_GRADIENT))
                else:
                    new_color = self._get_edge_color(target)
            else:
                new_color = QColor(Qt.GlobalColor.black)
        
        if self._bg_mode in (BackgroundMode.SMOOTH, BackgroundMode.TEMPORAL_VIBE):
            self._bg_anim.stop()
            self._bg_anim.setStartValue(old_color)
            self._bg_anim.setEndValue(new_color)
            self._bg_anim.start()
        else:
            self.bg_color = new_color # Uses setter for immediate apply

    def _get_vibe_color(self, pixmap: QPixmap, gradient: bool = False) -> QColor:
        """Sample the interior of the image to find the dominant vibrant color (the 'vibe')."""
        if pixmap.isNull():
            return QColor(Qt.GlobalColor.black)

        # Fast downsample to a tiny thumbnail (lightning fast in C++)
        thumb = pixmap.scaled(64, 64, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
        image = thumb.toImage()

        def extract_vibe(startY, endY):
            bins = {}
            noise_lightness_sum = 0
            noise_count = 0

            for y in range(startY, endY):
                for x in range(64):
                    c = image.pixelColor(x, y)
                    h, s, v = c.hsvHue(), c.hsvSaturation(), c.value()
                    l = c.lightness()
                    
                    # Filter out noise (blacks, whites, grays)
                    if s < 30 or v < 30 or v > 225 or l < 30 or l > 225:
                        noise_lightness_sum += l
                        noise_count += 1
                        continue
                    
                    # Put into 12 hue bins (360/30 = 12)
                    hue_bin = (h // 30) * 30
                    if hue_bin not in bins:
                        bins[hue_bin] = []
                    bins[hue_bin].append(c)
            
            if not bins:
                # Snap to black or white based on overall image lightness
                avg_l = (noise_lightness_sum // noise_count) if noise_count > 0 else 0
                return QColor(Qt.GlobalColor.white) if avg_l > 128 else QColor(Qt.GlobalColor.black)
            
            # Find the bin with the most pixels
            biggest_bin = max(bins.values(), key=len)
            
            # Average the colors in the biggest bin
            r = sum(c.red() for c in biggest_bin) // len(biggest_bin)
            g = sum(c.green() for c in biggest_bin) // len(biggest_bin)
            b = sum(c.blue() for c in biggest_bin) // len(biggest_bin)
            return QColor(r, g, b)

        if gradient:
            c_top = extract_vibe(0, 32)
            c_bot = extract_vibe(32, 64)
            
            grad = QLinearGradient(0, 0, 0, 1)
            grad.setCoordinateMode(QLinearGradient.CoordinateMode.ObjectBoundingMode)
            grad.setColorAt(0, c_top)
            grad.setColorAt(1, c_bot)
            self._current_bg_gradient = grad
            
            # Return overall average for contrast calculations
            return QColor((c_top.red() + c_bot.red()) // 2,
                          (c_top.green() + c_bot.green()) // 2,
                          (c_top.blue() + c_bot.blue()) // 2)
        else:
            return extract_vibe(0, 64)

    def _get_edge_color(self, pixmap: QPixmap) -> QColor:
        """Sample edge pixels and compute mean, median, or mode."""
        image = pixmap.toImage()
        w, h = image.width(), image.height()
        if w < 2 or h < 2:
            return QColor(Qt.GlobalColor.black)
            
        pixels = []
        # Sample points around the perimeter
        step_x = max(1, w // 25)
        step_y = max(1, h // 25)
        
        for x in range(0, w, step_x):
            pixels.append(image.pixelColor(x, 0))
            pixels.append(image.pixelColor(x, h - 1))
        for y in range(step_y, h - step_y, step_y):
            pixels.append(image.pixelColor(0, y))
            pixels.append(image.pixelColor(w - 1, y))
            
        if not pixels:
            return QColor(Qt.GlobalColor.black)
            
        if self._bg_mode == BackgroundMode.MEDIAN:
            rs = sorted(p.red() for p in pixels)
            gs = sorted(p.green() for p in pixels)
            bs = sorted(p.blue() for p in pixels)
            mid = len(pixels) // 2
            return QColor(rs[mid], gs[mid], bs[mid])

        elif self._bg_mode == BackgroundMode.VIBRANT:
            # Weight average by saturation
            r_sum = g_sum = b_sum = weight_sum = 0
            for p in pixels:
                s = p.saturation() + 1 # Avoid zero weight
                # Square weight to favor vibrancy more heavily
                weight = s * s
                r_sum += p.red() * weight
                g_sum += p.green() * weight
                b_sum += p.blue() * weight
                weight_sum += weight
            return QColor(int(r_sum / weight_sum), int(g_sum / weight_sum), int(b_sum / weight_sum))

        elif self._bg_mode == BackgroundMode.CONTRAST:
            # Get mode, then shift luminance to opposite pole
            from collections import Counter
            counts = Counter((p.red(), p.green(), p.blue()) for p in pixels)
            most_common = counts.most_common(1)[0][0]
            c = QColor(*most_common)
            # If it's light, make it darker; if dark, make it lighter (offset)
            lum = c.lightness()
            shift = -30 if lum > 128 else 30
            return QColor.fromHsl(c.hslHue(), c.hslSaturation(), max(0, min(255, lum + shift)))

        elif self._bg_mode == BackgroundMode.CLEAN:
            # Mean with outlier removal (brightness)
            sorted_px = sorted(pixels, key=lambda p: p.lightness())
            margin = len(sorted_px) // 10
            # Trim 10% brightest and 10% darkest
            cleaned = sorted_px[margin:-margin]
            if not cleaned: cleaned = pixels
            r = sum(p.red() for p in cleaned) // len(cleaned)
            g = sum(p.green() for p in cleaned) // len(cleaned)
            b = sum(p.blue() for p in cleaned) // len(cleaned)
            return QColor(r, g, b)

        elif self._bg_mode == BackgroundMode.SMOOTH:
            # Just use Mean for the target, transition is handled in _update_background
            r = sum(p.red() for p in pixels) // len(pixels)
            g = sum(p.green() for p in pixels) // len(pixels)
            b = sum(p.blue() for p in pixels) // len(pixels)
            return QColor(r, g, b)

        elif self._bg_mode == BackgroundMode.GRADIENT:
            # Sample 4 sides separately with higher density
            POINTS = 40
            t_px = [image.pixelColor(x, 0) for x in range(0, w, max(1, w // POINTS))]
            b_px = [image.pixelColor(x, h - 1) for x in range(0, w, max(1, w // POINTS))]
            l_px = [image.pixelColor(0, y) for y in range(0, h, max(1, h // POINTS))]
            r_px = [image.pixelColor(w - 1, y) for y in range(0, h, max(1, h // POINTS))]
            
            def mean_c(plist):
                if not plist: return QColor(0, 0, 0)
                return QColor(sum(p.red() for p in plist) // len(plist),
                              sum(p.green() for p in plist) // len(plist),
                              sum(p.blue() for p in plist) // len(plist))
            
            c_top, c_bot = mean_c(t_px), mean_c(b_px)
            
            # Use top/bottom for a vertical gradient. 
            # In ObjectBoundingMode, 0.0 is top, 1.0 is bottom.
            grad = QLinearGradient(0, 0, 0, 1)
            grad.setCoordinateMode(QLinearGradient.CoordinateMode.ObjectBoundingMode)
            grad.setColorAt(0, c_top)
            grad.setColorAt(1, c_bot)
            self._current_bg_gradient = grad
            
            # Return overall average for contrast calculations
            all_px = t_px + b_px + l_px + r_px
            return mean_c(all_px)
            
        return QColor(Qt.GlobalColor.black)

    # ------------------------------------------------------------------ #
    # Subclass contract                                                    #
    # ------------------------------------------------------------------ #

    async def _load_page_pixmap(self, idx: int) -> Optional[QPixmap]:
        raise NotImplementedError

    async def _do_prefetch(self, idx: int):
        pass

    def _on_page_changed(self, idx: int):
        pass

    # ------------------------------------------------------------------ #
    # Geometry                                                             #
    # ------------------------------------------------------------------ #

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_overlays()
        self._apply_fit()

    def _layout_overlays(self):
        w     = self.width()
        s = UIConstants.scale
        ftr_h = s(78) if self._thumb_visible else s(50)
        self.header.setGeometry(0, 0, w, s(38))
        self.footer.setGeometry(0, self.height() - ftr_h, w, ftr_h)

    def _on_adjacent_clicked(self):
        if self.on_transition and self._current_adjacent_ref:
            self.on_transition(self._current_adjacent_ref)

    async def _handle_boundary(self, direction: int):
        """Called when trying to go past first/last page."""
        logger.debug(f"Reader _handle_boundary: direction={direction}")
        
        # Reset pull visuals even if we don't have an adjacent book
        self._reset_navigation_state()

        if not self.on_get_adjacent: 
            logger.debug("Reader: No on_get_adjacent callback registered")
            return
        
        try:
            # Subclass or AppLayout provides this
            info = await self.on_get_adjacent(direction)
            if not info: 
                logger.debug(f"Reader: No adjacent book found in direction {direction}")
                return
            
            title, pixmap, book_ref = info
            self._current_adjacent_ref = book_ref
            logger.debug(f"Reader: Found adjacent book: {title}")
            
            self.adjacent_popover.populate(direction, title, pixmap)
            
            # Position
            s = UIConstants.scale
            is_continuous = self._page_layout == PageLayout.CONTINUOUS
            
            if is_continuous:
                # Top/Bottom center
                x = (self.width() - self.adjacent_popover.width()) // 2
                if direction > 0:
                    # Next: Bottom
                    y = self.height() - self.adjacent_popover.height() - s(80)
                    self.adjacent_popover.set_arrow("bottom")
                else:
                    # Prev: Top
                    y = s(80)
                    self.adjacent_popover.set_arrow("top")
            else:
                # Left/Right sides
                is_on_right = (direction > 0)
                if self._rtl:
                    is_on_right = not is_on_right

                if is_on_right:
                    # Right side
                    x = self.width() - self.adjacent_popover.width() - s(40)
                    self.adjacent_popover.set_arrow("right")
                else:
                    # Left side
                    x = s(40)
                    self.adjacent_popover.set_arrow("left")
                y = (self.height() - self.adjacent_popover.height()) // 2
            
            self._bump_activity()
            self.adjacent_popover.show_at(self.mapToGlobal(QPoint(x, y)))
            
        except Exception as e:
            logger.error(f"Error getting adjacent book: {e}")

    async def _jump_to_adjacent(self, direction: int):
        if not self.on_get_adjacent or not self.on_transition:
            return
        try:
            info = await self.on_get_adjacent(direction)
            if info:
                title, pixmap, book_ref = info
                self.on_transition(book_ref)
        except Exception as e:
            logger.error(f"Error jumping to adjacent book: {e}")

    # ------------------------------------------------------------------ #
    # Activity / overlay visibility                                        #
    # ------------------------------------------------------------------ #

    def _update_reader_cursor(self):
        # If we are in "hidden" state, don't change anything, _hide_cursor handles it
        if self.cursor().shape() == Qt.CursorShape.BlankCursor:
            return

        h_scrollable = self.view.horizontalScrollBar().maximum() > 0
        v_scrollable = self.view.verticalScrollBar().maximum() > 0
        
        if h_scrollable or v_scrollable:
            self.view.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.view.viewport().unsetCursor()

    def _hide_cursor(self):
        # Do not hide if any menus or popovers are active
        if (self.settings_menu.isVisible() or 
            self.help_popover.isVisible() or 
            self.meta_popover.isVisible() or 
            self.adjacent_popover.isVisible() or
            self.thumb_slider._popup.isVisible()):
            self._cursor_timer.start() # Check again later
            return

        self.setCursor(Qt.CursorShape.BlankCursor)
        self.view.setCursor(Qt.CursorShape.BlankCursor)
        self.view.viewport().setCursor(Qt.CursorShape.BlankCursor)
        # Apply to all child widgets that might have their own cursor (buttons, slider, etc.)
        for child in self.findChildren(QWidget):
            child.setCursor(Qt.CursorShape.BlankCursor)

    def _bump_cursor(self):
        if self.cursor().shape() == Qt.CursorShape.BlankCursor:
            self.unsetCursor()
            self.view.unsetCursor()
            self.view.viewport().unsetCursor()
            # Restore cursors for buttons/interactive elements
            for child in self.findChildren(QWidget):
                child.unsetCursor()
                
            self._update_reader_cursor()
        self._cursor_timer.start()

    def _bump_activity(self, show_cursor: bool = True, ensure_overlays: bool = True):
        if show_cursor:
            self._bump_cursor()
            
        if ensure_overlays and not self._overlays_visible:
            self._show_overlays()

        if self._auto_hide_controls:
            self._overlay_timer.start()
        else:
            self._overlay_timer.stop()

    def _show_overlays(self):
        self._overlays_visible = True
        self.header.setVisible(True)
        self.footer.setVisible(True)

    def _on_title_pressed(self, event):
        self._bump_cursor()
        if self.on_title_clicked:
            self.on_title_clicked()

    def _toggle_help(self):
        self._bump_activity()
        if self.help_popover.isVisible():
            self.help_popover.hide()
        else:
            self.help_popover.show_at_center(self)

    def _toggle_auto_hide(self):
        self._auto_hide_controls = not self._auto_hide_controls
        if self.config_manager:
            self.config_manager.set_reader_auto_hide_controls(self._auto_hide_controls)
        self._update_settings_menu()
        if self._auto_hide_controls:
            self._overlay_timer.start() # Start hide timer
        else:
            self._overlay_timer.stop() # Keep visible
            self._bump_activity(show_cursor=False) # Ensure they are shown

    def _hide_overlays(self):
        if self._slider_dragging:
            # Don't hide while dragging, restart timer if enabled
            if self._auto_hide_controls:
                self._overlay_timer.start()
            return

        self._overlays_visible = False
        self.header.setVisible(False)
        self.footer.setVisible(False)
        self.thumb_slider.hide_popup()
        self.meta_popover.hide()

    def _handle_gesture(self, event: QGestureEvent) -> bool:
        # Handle Pinch (Zoom)
        pinch = event.gesture(Qt.GestureType.PinchGesture)
        if pinch:
            state = pinch.state()
            input_logger.debug(f"  -> PINCH: state={state.name} scale={pinch.scaleFactor():.4f} center={pinch.centerPoint().x():.1f}")
            
            if state == Qt.GestureState.GestureStarted:
                self._is_pinching = True
                self._pinch_cooldown_timer.stop()
                return True
            
            elif state == Qt.GestureState.GestureUpdated:
                factor = pinch.scaleFactor()
                if abs(factor - 1.0) > 0.001:
                    self._zoom(factor)
                return True
                
            elif state in (Qt.GestureState.GestureFinished, Qt.GestureState.GestureCanceled):
                self._is_pinching = False
                self._pinch_cooldown_timer.start(TrackpadConstants.PINCH_COOLDOWN_MS)
                return True

        # Always consume other gestures (like Swipe) to prevent OS-level native page turns
        # which bypass our custom trackpad logic.
        return True

    # ------------------------------------------------------------------ #
    # Event handling                                                       #
    # ------------------------------------------------------------------ #

    def eventFilter(self, source, event):
        t = event.type()
        vp = self.view.viewport()

        if t == QEvent.Type.ContextMenu:
            self._bump_activity(ensure_overlays=False)
            self._update_settings_menu()
            self.settings_menu.exec(event.globalPos())
            return True

        if t == QEvent.Type.NativeGesture and source is vp:
            # OS confirmed a gesture, block normal wheel events and stop cooldown timer
            self._is_pinching = True
            self._pinch_cooldown_timer.stop()
            
            g_type = event.gestureType()
            val = event.value()
            input_logger.debug(f"GESTURE: type={g_type.name} val={val:.4f}")
            
            if g_type == Qt.NativeGestureType.BeginNativeGesture:
                self._last_pinch_val = val
                return True

            elif g_type == Qt.NativeGestureType.ZoomNativeGesture:
                # Platform-Agnostic Mode Detection:
                low = TrackpadConstants.ABSOLUTE_MIN
                high = TrackpadConstants.ABSOLUTE_MAX
                if low < val < high and low < self._last_pinch_val < high:
                    # Absolute Ratio (macOS/Windows)
                    factor = val / self._last_pinch_val
                else:
                    # Incremental Delta (Linux/Wayland)
                    # Inverted sign based on user feedback.
                    factor = 1.0 + (val * TrackpadConstants.INCREMENTAL_SENSITIVITY)
                
                input_logger.debug(f"  -> Zoom Calc: val={val:.4f} last={self._last_pinch_val:.4f} factor={factor:.4f}")
                
                if 0.5 < factor < 1.5 and abs(factor - 1.0) > 0.001:
                    self._zoom(factor)
                    self._last_pinch_val = val
                return True

            elif g_type == Qt.NativeGestureType.EndNativeGesture:
                self._pinch_cooldown_timer.start(TrackpadConstants.PINCH_COOLDOWN_MS)
                self._last_pinch_val = 0.0
                return True

            return True

        if t == QEvent.Type.Wheel and source is vp:
            dy = event.angleDelta().y()
            dx = event.angleDelta().x()
            phase = event.phase()
            input_logger.debug(f"WHEEL RAW: dy={dy} dx={dx} phase={phase.name} pinching={self._is_pinching}")

            if self._is_pinching:
                return True
            
            # Ctrl+Wheel for zooming (Standard Mouse Zoom / Windows Pinch Fallback)
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                if dy > 0:
                    self._zoom(self.ZOOM_STEP_IN)
                elif dy < 0:
                    self._zoom(self.ZOOM_STEP_OUT)
                return True

            # Detect high-res trackpad vs standard mouse wheel
            phase = event.phase()
            
            # Qt6 often synthesizes pixelDelta for standard mouse wheels. 
            # A true standard mouse wheel scroll event has NoScrollPhase, dx=0, and dy as a multiple of 120.
            is_standard_wheel = (phase == Qt.ScrollPhase.NoScrollPhase) and (dx == 0) and (dy != 0 and dy % 120 == 0)
            
            now_sec = time.time()
            # Sticky trackpad check: if we saw a definitive trackpad event in the last 300ms, 
            # ignore the 120-notch rule to prevent glitches mid-swipe.
            if is_standard_wheel and (now_sec - getattr(self, '_last_trackpad_time', 0) < 0.3):
                is_standard_wheel = False

            is_trackpad = not is_standard_wheel
            
            if is_trackpad:
                self._last_trackpad_time = now_sec
                has_pixel = not event.pixelDelta().isNull()
                vbar = self.view.verticalScrollBar()
                hbar = self.view.horizontalScrollBar()

                if getattr(self, '_trackpad_locked', False):
                    if phase in (Qt.ScrollPhase.ScrollBegin, Qt.ScrollPhase.NoScrollPhase):
                        self._trackpad_locked = False
                    else:
                        return True

                is_new_gesture = phase == Qt.ScrollPhase.ScrollBegin
                
                if is_new_gesture or not self._last_wheel_time:
                    dt = KineticConstants.TICK_MS / 1000.0  # Default ~16ms tick interval
                else:
                    dt = now_sec - self._last_wheel_time
                    if dt <= 0.001:
                        dt = KineticConstants.TICK_MS / 1000.0
                
                self._last_wheel_time = now_sec

                if phase == Qt.ScrollPhase.ScrollBegin:
                    self._kinetic_timer.stop()
                    self._custom_scroll_velocity_y = 0.0
                    self._custom_scroll_velocity_x = 0.0
                    self._custom_scroll_y = float(vbar.value())
                    self._custom_scroll_x = float(hbar.value())
                
                px_y, px_x = 0, 0
                if has_pixel:
                    px = event.pixelDelta()
                    px_y, px_x = px.y(), px.x()
                else:
                    px_y, px_x = int(dy * KineticConstants.WHEEL_STEP_MULTIPLIER), int(dx * KineticConstants.WHEEL_STEP_MULTIPLIER)

                inst_vel_y = -px_y / dt
                inst_vel_x = -px_x / dt

                basic_emulation = self.config_manager.get_reader_trackpad_basic_emulation() if self.config_manager else False
                self._add_scroll_delta(px_x, px_y, allow_overscroll=not basic_emulation)

                if self._page_layout == PageLayout.CONTINUOUS:
                    if (px_y > 0 and self._custom_scroll_y < vbar.minimum()) or (px_y < 0 and self._custom_scroll_y > vbar.maximum()):
                        self._check_continuous_virtualization()

                weight = KineticConstants.TRACKPAD_VEL_WEIGHT
                self._custom_scroll_velocity_y = (self._custom_scroll_velocity_y * (1.0 - weight)) + (inst_vel_y * weight)
                self._custom_scroll_velocity_x = (self._custom_scroll_velocity_x * (1.0 - weight)) + (inst_vel_x * weight)

                momentum_enabled = self.config_manager.get_reader_trackpad_momentum() if self.config_manager else False
                if momentum_enabled:
                    if phase in (Qt.ScrollPhase.ScrollEnd, Qt.ScrollPhase.ScrollMomentum):
                        if abs(self._custom_scroll_velocity_y) > KineticConstants.MIN_VELOCITY_PPS or abs(self._custom_scroll_velocity_x) > KineticConstants.MIN_VELOCITY_PPS:
                            phys_logger.debug(f"KINETIC: Starting trackpad momentum. VelY={self._custom_scroll_velocity_y:.1f} VelX={self._custom_scroll_velocity_x:.1f}")
                            self._kinetic_timer.start()

                if phase == Qt.ScrollPhase.ScrollEnd:
                    threshold = UIConstants.scale(OverscrollConstants.PULL_THRESHOLD)
                    basic_emulation = self.config_manager.get_reader_trackpad_basic_emulation() if self.config_manager else False
                    can_pull = not basic_emulation
                    if can_pull and self._effective_layout() != PageLayout.CONTINUOUS:
                        if self._overscroll_x <= -threshold:
                            self._prev()
                            return True
                        elif self._overscroll_x >= threshold:
                            self._next()
                            return True
                    
                    if not self._kinetic_timer.isActive():
                        self._start_snap_back()

                return True

            # Standard scroll
            return self._smart_scroll(dy)

        if t == QEvent.Type.MouseMove:
            self._bump_cursor() # Just show cursor, don't show overlays
            
            if source is vp and self._last_drag_y is not None:
                # Custom drag scrolling
                pos = event.position()
                dy = pos.y() - self._last_drag_y
                dx = pos.x() - self._last_drag_x
                
                self._add_scroll_delta(dx, dy)
                
                # Estimate mouse drag velocity using weighted average (unify with trackpad feel)
                now = time.time()
                dt = now - self._last_drag_time
                if dt > 0:
                    dt_clamped = max(dt, KineticConstants.MIN_DRAG_DT)
                    # Logic: Estimate mouse drag velocity in pixels per second (PPS)
                    # to match the physics loop unit and trackpad velocity tracking.
                    inst_vel_y = (-dy / dt_clamped) * KineticConstants.MOUSE_DRAG_BOOST
                    inst_vel_x = (-dx / dt_clamped) * KineticConstants.MOUSE_DRAG_BOOST
                    
                    weight = KineticConstants.TRACKPAD_VEL_WEIGHT
                    self._custom_scroll_velocity_y = (self._custom_scroll_velocity_y * (1.0 - weight)) + (inst_vel_y * weight)
                    self._custom_scroll_velocity_x = (self._custom_scroll_velocity_x * (1.0 - weight)) + (inst_vel_x * weight)
                    
                    input_logger.debug(f"MOUSE DRAG: dy={dy:.1f}, dt={dt:.4f}, inst_v={inst_vel_y:.1f}, avg_v={self._custom_scroll_velocity_y:.1f}")
                
                self._last_drag_y = pos.y()
                self._last_drag_x = pos.x()
                self._last_drag_time = now
                return True

        if t == QEvent.Type.Resize and source is vp:
            if self._fit_mode != FitMode.CUSTOM:
                self._apply_fit()
            if hasattr(self, 'nav_left'):
                self.nav_left.update_position()
                self.nav_right.update_position()

        if t == QEvent.Type.MouseButtonPress and source is vp:
            if event.button() == Qt.MouseButton.LeftButton:
                if hasattr(self, '_snap_anim') and self._snap_anim and self._snap_anim.state() == QAbstractAnimation.State.Running:
                    self._snap_anim.stop()

                self._mouse_press_pos = event.position()
                
                self._kinetic_timer.stop()
                self._custom_scroll_velocity_y = 0.0
                self._custom_scroll_velocity_x = 0.0
                self._last_drag_y = event.position().y()
                self._last_drag_x = event.position().x()
                self._last_drag_time = time.time()
                
                # Sync logical position to physical
                vbar = self.view.verticalScrollBar()
                hbar = self.view.horizontalScrollBar()
                self._custom_scroll_y = float(vbar.value())
                self._custom_scroll_x = float(hbar.value())
                
                return True # Claim event for custom drag
            else:
                self._mouse_press_pos = None
                self._last_drag_y = None
                self._last_drag_x = None
            return False # Let QGraphicsView start drag if not handled

        if t == QEvent.Type.MouseButtonDblClick and source is vp:
            if event.button() != Qt.MouseButton.LeftButton:
                return False

            w = vp.width()
            x = event.position().x()
            
            # Stop any pending single click (UI toggle or page turn)
            self._click_timer.stop()
            self._pending_click_pos = None
            self._ignore_next_release = True # Swallow the second release too

            # 1. In navigation zones: do NOTHING else (already stopped the timer).
            if x < w * self.CLICK_ZONE_PCT or x > w * (1 - self.CLICK_ZONE_PCT):
                return True 
            
            # 2. In center: Cycle zoom.
            self._cycle_zoom()
            return True

        if t == QEvent.Type.MouseButtonRelease and source is vp:
            if self._ignore_next_release:
                self._ignore_next_release = False
                self._mouse_press_pos = None
                self._last_drag_y = None
                self._last_drag_x = None
                return True

            if self._last_drag_y is not None:
                # Check for velocity staleness (pausing before release kills momentum)
                now = time.time()
                if (now - self._last_drag_time) > (KineticConstants.VELOCITY_STALE_MS / 1000.0):
                    self._custom_scroll_velocity_y = 0
                    self._custom_scroll_velocity_x = 0

                # Trigger Page Turn if Pull Threshold Reached (Hybrid Model)
                threshold = UIConstants.scale(OverscrollConstants.PULL_THRESHOLD)
                if self._effective_layout() != PageLayout.CONTINUOUS and self._overscroll_x <= -threshold: # Pull from Left
                    self._prev()
                    self._last_drag_y = None
                    self._last_drag_x = None
                    self._mouse_press_pos = None
                    return True
                elif self._effective_layout() != PageLayout.CONTINUOUS and self._overscroll_x >= threshold: # Pull from Right
                    self._next()
                    self._last_drag_y = None
                    self._last_drag_x = None
                    self._mouse_press_pos = None
                    return True
                else:
                    # Start momentum if either axis has sufficient velocity
                    if abs(self._custom_scroll_velocity_y) > KineticConstants.MIN_VELOCITY_PPS or \
                       abs(self._custom_scroll_velocity_x) > KineticConstants.MIN_VELOCITY_PPS:
                        phys_logger.debug(f"KINETIC: Starting mouse momentum. VelY={self._custom_scroll_velocity_y:.1f} VelX={self._custom_scroll_velocity_x:.1f}")
                        self._kinetic_timer.start()
                    else:
                        self._start_snap_back()

                self._last_drag_y = None
                self._last_drag_x = None
                
                # If we moved significantly, ignore click
                if self._mouse_press_pos and (event.position() - self._mouse_press_pos).manhattanLength() >= KineticConstants.CLICK_DEADZONE:
                    self._mouse_press_pos = None
                    return True

            if self._mouse_press_pos and event.button() == Qt.MouseButton.LeftButton:
                diff = event.position() - self._mouse_press_pos
                if diff.manhattanLength() < KineticConstants.CLICK_DEADZONE:
                    self._handle_click(event)
            self._mouse_press_pos = None
            return False

        if t == QEvent.Type.KeyPress:
            self.keyPressEvent(event)
            return True # Consume key

        return super().eventFilter(source, event)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            self._update_settings_menu()
        super().changeEvent(event)

    def _on_kinetic_tick(self):
        vbar = self.view.verticalScrollBar()
        hbar = self.view.horizontalScrollBar()
        
        tick_sec = KineticConstants.TICK_MS / 1000.0
        
        # Apply velocity (PPS) to logical position
        move_y = self._custom_scroll_velocity_y * tick_sec
        move_x = self._custom_scroll_velocity_x * tick_sec
        self._custom_scroll_y += move_y
        self._custom_scroll_x += move_x
        
        min_y, max_y = vbar.minimum(), vbar.maximum()
        min_x, max_x = hbar.minimum(), hbar.maximum()

        # Hard limit for overscroll logical buffering
        max_logical = UIConstants.scale(OverscrollConstants.MAX_LOGICAL_STRETCH)
        
        # Clamp logical positions and kill velocity if hitting hard limits
        hit_limit = False
        if self._custom_scroll_y < min_y - max_logical:
            self._custom_scroll_y = min_y - max_logical
            self._custom_scroll_velocity_y = 0
            hit_limit = True
        elif self._custom_scroll_y > max_y + max_logical:
            self._custom_scroll_y = max_y + max_logical
            self._custom_scroll_velocity_y = 0
            hit_limit = True
            
        if self._custom_scroll_x < min_x - max_logical:
            self._custom_scroll_x = min_x - max_logical
            self._custom_scroll_velocity_x = 0
            hit_limit = True
        elif self._custom_scroll_x > max_x + max_logical:
            self._custom_scroll_x = max_x + max_logical
            self._custom_scroll_velocity_x = 0
            hit_limit = True
        
        # Calculate overshoot
        clamped_y = max(min_y, min(max_y, self._custom_scroll_y))
        clamped_x = max(min_x, min(max_x, self._custom_scroll_x))
        
        self._overscroll_y = self._custom_scroll_y - clamped_y
        self._overscroll_x = self._custom_scroll_x - clamped_x
        
        # Update physical scrollbars
        vbar.setValue(int(clamped_y))
        hbar.setValue(int(clamped_x))
        self._apply_overscroll()
        
        # Decay (Friction) per axis
        fric_y = OverscrollConstants.MOMENTUM_FRICTION if abs(self._overscroll_y) > 1.0 else KineticConstants.DECAY_FACTOR
        fric_x = OverscrollConstants.MOMENTUM_FRICTION if abs(self._overscroll_x) > 1.0 else KineticConstants.DECAY_FACTOR
        
        self._custom_scroll_velocity_y *= fric_y
        self._custom_scroll_velocity_x *= fric_x
        
        phys_logger.debug(f"KINETIC TICK: v_y={self._custom_scroll_velocity_y:.1f} v_x={self._custom_scroll_velocity_x:.1f} "
                          f"move=[{move_x:.1f},{move_y:.1f}] over=[{self._overscroll_x:.1f},{self._overscroll_y:.1f}] "
                          f"fric_x={fric_x:.2f} fric_y={fric_y:.2f} {'LIMIT' if hit_limit else ''}")

        # Stop if slow
        if abs(self._custom_scroll_velocity_y) < KineticConstants.MIN_VELOCITY_PPS and \
           abs(self._custom_scroll_velocity_x) < KineticConstants.MIN_VELOCITY_PPS:
            phys_logger.debug(f"KINETIC: Velocity threshold reached. Stopping. OverX={self._overscroll_x:.1f} OverY={self._overscroll_y:.1f}")
            self._kinetic_timer.stop()
            self._custom_scroll_velocity_y = 0
            self._custom_scroll_velocity_x = 0
            if self._overscroll_y != 0 or self._overscroll_x != 0:
                self._start_snap_back()

    def _add_scroll_delta(self, dx, dy, allow_overscroll=True):
        """Standardized scroll/panning logic with elastic edge bounce."""
        if hasattr(self, '_snap_group') and self._snap_group and self._snap_group.state() == QAbstractAnimation.State.Running:
            self._snap_group.stop()
        elif hasattr(self, '_snap_anim') and self._snap_anim and self._snap_anim.state() == QAbstractAnimation.State.Running:
            self._snap_anim.stop()

        vbar = self.view.verticalScrollBar()
        hbar = self.view.horizontalScrollBar()
        
        min_y, max_y = vbar.minimum(), vbar.maximum()
        min_x, max_x = hbar.minimum(), hbar.maximum()

        # Physical pull limit (clamping the logical buffer)
        max_logical = UIConstants.scale(OverscrollConstants.MAX_LOGICAL_STRETCH)
        
        # Y-axis: Only allow overscroll if there's a range to scroll through
        if max_y > min_y:
            delta_y = dy
            if allow_overscroll:
                if self._custom_scroll_y < min_y and dy > 0: 
                    delta_y = dy * OverscrollConstants.PULL_DAMPING
                elif self._custom_scroll_y > max_y and dy < 0:
                    delta_y = dy * OverscrollConstants.PULL_DAMPING
            
            self._custom_scroll_y -= delta_y
            if allow_overscroll:
                self._custom_scroll_y = max(min_y - max_logical, min(max_y + max_logical, self._custom_scroll_y))
            else:
                self._custom_scroll_y = max(min_y, min(max_y, self._custom_scroll_y))
        else:
            self._custom_scroll_y = min_y
            
        # X-axis damping
        delta_x = dx
        if allow_overscroll:
            if self._custom_scroll_x < min_x and dx > 0:
                delta_x = dx * OverscrollConstants.PULL_DAMPING
            elif self._custom_scroll_x > max_x and dx < 0:
                delta_x = dx * OverscrollConstants.PULL_DAMPING

        self._custom_scroll_x -= delta_x
        if allow_overscroll:
            self._custom_scroll_x = max(min_x - max_logical, min(max_x + max_logical, self._custom_scroll_x))
        else:
            self._custom_scroll_x = max(min_x, min(max_x, self._custom_scroll_x))

        clamped_y = max(min_y, min(max_y, self._custom_scroll_y))
        clamped_x = max(min_x, min(max_x, self._custom_scroll_x))

        self._overscroll_y = self._custom_scroll_y - clamped_y
        self._overscroll_x = self._custom_scroll_x - clamped_x

        vbar.setValue(int(clamped_y))
        hbar.setValue(int(clamped_x))
        self._apply_overscroll()

    def _apply_overscroll(self):
        """Visually translates content and updates nav indicators based on overscroll deficit."""
        if not hasattr(self, "content_container"): return
        
        scale_x = self.view.transform().m11()
        scale_y = self.view.transform().m22()

        # 1. Hybrid Visual Stretch
        dx = 0
        hbar = self.view.horizontalScrollBar()
        if hbar.maximum() > hbar.minimum():
            dx = -(self._overscroll_x * OverscrollConstants.VISUAL_DAMPING) / scale_x if scale_x else 0
            
        dy = -(self._overscroll_y * OverscrollConstants.VISUAL_DAMPING) / scale_y if scale_y else 0
        self.content_container.setPos(dx, dy)
        
        # 2. Update Nav Indicators
        is_mouse_drag = self._last_drag_x is not None
        basic_emulation = self.config_manager.get_reader_trackpad_basic_emulation() if self.config_manager else False
        can_pull = is_mouse_drag or not basic_emulation
        if can_pull and self._effective_layout() != PageLayout.CONTINUOUS and hasattr(self, 'nav_left') and self.nav_left:
            if self._overscroll_x < 0:
                self.nav_left.pull_distance = abs(self._overscroll_x)
                self.nav_right.pull_distance = 0
            elif self._overscroll_x > 0:
                self.nav_right.pull_distance = abs(self._overscroll_x)
                self.nav_left.pull_distance = 0
            else:
                self.nav_left.pull_distance = 0
                self.nav_right.pull_distance = 0
        elif hasattr(self, 'nav_left') and self.nav_left:
            self.nav_left.pull_distance = 0
            self.nav_right.pull_distance = 0

    def _start_snap_back(self):
        """Animates logical scroll positions and nav pull back to physical limits."""
        if hasattr(self, '_snap_group') and self._snap_group and self._snap_group.state() == QAbstractAnimation.State.Running:
            self._snap_group.stop()

        if self._overscroll_x == 0 and self._overscroll_y == 0 and self._nav_pull_x == 0:
            return

        phys_logger.debug(f"SNAP BACK: Starting animation. OverX={self._overscroll_x:.1f} OverY={self._overscroll_y:.1f}")

        vbar = self.view.verticalScrollBar()
        hbar = self.view.horizontalScrollBar()

        target_y = max(vbar.minimum(), min(vbar.maximum(), self._custom_scroll_y))
        target_x = max(hbar.minimum(), min(hbar.maximum(), self._custom_scroll_x))

        # Use a group to animate both physical overscroll and nav pull
        self._snap_group = QParallelAnimationGroup(self)

        # 1. Physical Snap Animation
        self._snap_anim = QVariantAnimation(self)
        self._snap_anim.setDuration(OverscrollConstants.SNAP_BACK_MS)
        self._snap_anim.setEasingCurve(OverscrollConstants.SNAP_EASING)
        self._snap_anim.setStartValue(QPointF(self._custom_scroll_x, self._custom_scroll_y))
        self._snap_anim.setEndValue(QPointF(target_x, target_y))

        def on_physical_step(val):
            self._custom_scroll_x = val.x()
            self._custom_scroll_y = val.y()
            cvbar = self.view.verticalScrollBar()
            chbar = self.view.horizontalScrollBar()
            self._overscroll_x = self._custom_scroll_x - max(chbar.minimum(), min(chbar.maximum(), self._custom_scroll_x))
            self._overscroll_y = self._custom_scroll_y - max(cvbar.minimum(), min(cvbar.maximum(), self._custom_scroll_y))
            self._apply_overscroll()

        self._snap_anim.valueChanged.connect(on_physical_step)
        self._snap_group.addAnimation(self._snap_anim)

        self._snap_group.start()

    def _reset_navigation_state(self):
        """Clears overscroll, pull-to-turn indicators, and kills kinetic momentum."""
        self._kinetic_timer.stop()
        self._custom_scroll_velocity_y = 0.0
        self._custom_scroll_velocity_x = 0.0
        
        self._overscroll_x = 0.0
        self._overscroll_y = 0.0
        self._nav_pull_x = 0.0
        
        # Sync logical position to physical to prevent "jumps" on the next input
        hbar = self.view.horizontalScrollBar()
        vbar = self.view.verticalScrollBar()
        self._custom_scroll_x = float(hbar.value())
        self._custom_scroll_y = float(vbar.value())
        
        # Reset trackpad state
        self._trackpad_acc_x = 0
        self._trackpad_acc_y = 0
        self._trackpad_locked = True # Block further movement until next gesture
        
        if hasattr(self, 'nav_left') and self.nav_left:
            self.nav_left.pull_distance = 0
            self.nav_left.hide()
        if hasattr(self, 'nav_right') and self.nav_right:
            self.nav_right.pull_distance = 0
            self.nav_right.hide()
            
        if hasattr(self, 'content_container') and self.content_container:
            self.content_container.setPos(0, 0)
            
        # Stop any active snap-back animations
        if hasattr(self, '_snap_group') and self._snap_group and self._snap_group.state() == QAbstractAnimation.State.Running:
            self._snap_group.stop()
        if hasattr(self, '_snap_anim') and self._snap_anim and self._snap_anim.state() == QAbstractAnimation.State.Running:
            self._snap_anim.stop()

    def _smart_scroll(self, dy: int) -> bool:
        """Shared logic for mouse wheel and Space/Shift+Space 'smart' navigation."""
        if dy == 0: return False
        
        vbar = self.view.verticalScrollBar()
        hbar = self.view.horizontalScrollBar()
        vp_h = self.view.viewport().height()
        vp_w = self.view.viewport().width()
        
        input_logger.debug(f"  -> _smart_scroll(dy={dy}): VBar={vbar.value()} [{vbar.minimum()}..{vbar.maximum()}] HBar={hbar.value()}/{hbar.maximum()}")

        # 1. Typewriter flow (Fit Width/Height, Not Continuous)
        if self._fit_mode in (FitMode.FIT_WIDTH, FitMode.FIT_HEIGHT, FitMode.ORIGINAL, FitMode.CUSTOM) and self._page_layout != PageLayout.CONTINUOUS:
            scroll_amount_h = int(vp_w * self.SMART_PAN_STEP_H_PCT)
            v_jump = int(vp_h * self.SMART_PAN_STEP_V_PCT) # Overlap percentage
            h_skip_threshold = int(vp_w * self.SMART_PAN_SKIP_THRESHOLD_H_PCT)
            v_skip_threshold = int(vp_h * self.SMART_PAN_SKIP_THRESHOLD_V_PCT)
            
            if dy < 0: # Scroll "Down" / Forward
                # 1a. Try Horizontal panning first (if it has range)
                if hbar.maximum() > 0:
                    if not self._rtl: # LtR
                        remaining = hbar.maximum() - hbar.value()
                        if remaining > h_skip_threshold:
                            hbar.setValue(hbar.value() + scroll_amount_h)
                            return True
                    else: # RtL
                        remaining = hbar.value() - hbar.minimum()
                        if remaining > h_skip_threshold:
                            hbar.setValue(hbar.value() - scroll_amount_h)
                            return True

                # 1b. Try Vertical panning next
                if vbar.maximum() > 0:
                    remaining_v = vbar.maximum() - vbar.value()
                    if remaining_v > v_skip_threshold:
                        vbar.setValue(min(vbar.maximum(), vbar.value() + v_jump))
                        # Reset horizontal to start of line
                        hbar.setValue(hbar.maximum() if self._rtl else hbar.minimum())
                        return True
                
                # 1c. If at bottom-right (or bottom-left for RtL), Next Page
                input_logger.debug(" >> EXECUTE: _next()")
                self._next()
                return True

            elif dy > 0: # Scroll "Up" / Backward
                # 1a. Try Horizontal panning first (if it has range)
                if hbar.maximum() > 0:
                    if not self._rtl: # LtR
                        remaining = hbar.value() - hbar.minimum()
                        if remaining > h_skip_threshold:
                            hbar.setValue(hbar.value() - scroll_amount_h)
                            return True
                    else: # RtL
                        remaining = hbar.maximum() - hbar.value()
                        if remaining > h_skip_threshold:
                            hbar.setValue(hbar.value() + scroll_amount_h)
                            return True

                # 1b. Try Vertical panning next
                if vbar.maximum() > 0:
                    remaining_v = vbar.value() - vbar.minimum()
                    if remaining_v > v_skip_threshold:
                        vbar.setValue(max(vbar.minimum(), vbar.value() - v_jump))
                        # Reset horizontal to end of line
                        hbar.setValue(hbar.minimum() if self._rtl else hbar.maximum())
                        return True
                
                # 1c. If at top-left (or top-right for RtL), Prev Page
                input_logger.debug(" >> EXECUTE: _prev(is_back=True)")
                self._prev(is_back=True)
                return True
            
            return False

        # 2. Continuous Mode: pass through for native scrolling, but handle boundaries
        if self._page_layout == PageLayout.CONTINUOUS:
            if dy < 0 and vbar.value() >= vbar.maximum():
                self._next()
                return True
            elif dy > 0 and vbar.value() <= vbar.minimum():
                self._prev(is_back=True)
                return True
            return False

        # 3. Default (Fit Page): Simple next/prev page
        if dy < 0:
            self._next()
        else:
            self._prev()
        return True

    def _clear_pinching(self):
        self._is_pinching = False
        


    def _on_click_timer_timeout(self):
        if self._pending_click_pos:
            pos = self._pending_click_pos
            self._pending_click_pos = None
            self._execute_click(pos)

    def _handle_click(self, event):
        self._bump_cursor() # Restore cursor on any click
        pos = event.position()
        
        # Always use the click timer to distinguish single vs double clicks.
        # This prevents the UI from toggling when the user intends to double-click zoom.
        self._pending_click_pos = pos
        self._click_timer.start(self.CLICK_GUARD_MS)

    def _execute_click(self, pos):
        w = self.view.viewport().width()
        x = pos.x()
        
        zone_w = w * self.CLICK_ZONE_PCT
        is_left = x < zone_w
        is_right = x > w - zone_w
        
        if is_left:
            # Page turn or boundary
            if self._rtl:
                self._next()
            else:
                self._prev()
        elif is_right:
            # Page turn or boundary
            if self._rtl:
                self._prev()
            else:
                self._next()
        else:
            # Centre tap: toggle overlay visibility
            if self._overlays_visible:
                self._hide_overlays()
                self._overlay_timer.stop()
            else:
                self._bump_activity(show_cursor=True)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()

        hbar = self.view.horizontalScrollBar()
        vbar = self.view.verticalScrollBar()
        # Use a reasonable step for panning (1/10 of viewport)
        step_h = self.view.viewport().width() // 10
        step_v = self.view.viewport().height() // 10

        nav_keys = (Qt.Key.Key_Right, Qt.Key.Key_Left, Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_PageDown, Qt.Key.Key_PageUp, Qt.Key.Key_Space)

        if key == Qt.Key.Key_Right:
            if hbar.maximum() > 0 and hbar.value() < hbar.maximum():
                hbar.setValue(hbar.value() + step_h)
                self._bumper_key = None
            else:
                if hbar.maximum() == 0 or self._bumper_key == key:
                    if self._rtl: self._prev()
                    else: self._next()
                    self._bumper_key = None
                else:
                    self._bumper_key = key
            return

        elif key == Qt.Key.Key_Left:
            if hbar.maximum() > 0 and hbar.value() > hbar.minimum():
                hbar.setValue(hbar.value() - step_h)
                self._bumper_key = None
            else:
                if hbar.maximum() == 0 or self._bumper_key == key:
                    if self._rtl: self._next()
                    else: self._prev()
                    self._bumper_key = None
                else:
                    self._bumper_key = key
            return

        elif key == Qt.Key.Key_Down:
            if vbar.maximum() > 0 and vbar.value() < vbar.maximum():
                vbar.setValue(vbar.value() + step_v)
                self._bumper_key = None
            else:
                if vbar.maximum() == 0 or self._bumper_key == key:
                    self._next()
                    self._bumper_key = None
                else:
                    self._bumper_key = key
            return

        elif key == Qt.Key.Key_Up:
            if vbar.maximum() > 0 and vbar.value() > vbar.minimum():
                vbar.setValue(vbar.value() - step_v)
                self._bumper_key = None
            else:
                if vbar.maximum() == 0 or self._bumper_key == key:
                    self._prev()
                    self._bumper_key = None
                else:
                    self._bumper_key = key
            return

        elif key == Qt.Key.Key_PageDown:
            if vbar.maximum() > 0 and vbar.value() < vbar.maximum():
                vbar.setValue(vbar.value() + vbar.pageStep())
                self._bumper_key = None
            else:
                if vbar.maximum() == 0 or self._bumper_key == key:
                    self._next()
                    self._bumper_key = None
                else:
                    self._bumper_key = key
            return

        elif key == Qt.Key.Key_PageUp:
            if vbar.maximum() > 0 and vbar.value() > vbar.minimum():
                vbar.setValue(vbar.value() - vbar.pageStep())
                self._bumper_key = None
            else:
                if vbar.maximum() == 0 or self._bumper_key == key:
                    self._prev()
                    self._bumper_key = None
                else:
                    self._bumper_key = key
            return

        if key not in nav_keys:
            self._bumper_key = None

        if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self._zoom(self.ZOOM_STEP_IN)
        elif key == Qt.Key.Key_Minus:
            self._zoom(self.ZOOM_STEP_OUT)
        elif key == Qt.Key.Key_0:
            self._set_fit_mode(FitMode.FIT_PAGE)
        elif key == Qt.Key.Key_Space:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._smart_scroll(120) # Scroll Up
            else:
                self._smart_scroll(-120) # Scroll Down
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # Enter toggles overlays
            if self._overlays_visible:
                self._hide_overlays()
                self._overlay_timer.stop()
            else:
                self._bump_activity(show_cursor=False) # Only show overlays, not cursor
        elif key in (Qt.Key.Key_F11, Qt.Key.Key_F):
            # Let this bubble to MainWindow for global handling
            event.ignore()
            return
        elif key == Qt.Key.Key_Escape:
            self._do_exit()
            event.accept()
            return
        elif key == Qt.Key.Key_C:
            self._cycle_fit()
        elif key == Qt.Key.Key_H:
            self._toggle_help()
        elif key == Qt.Key.Key_I:
            # Show overlays and metadata
            self._bump_activity()
            if self.on_title_clicked:
                self.on_title_clicked()
        elif key == Qt.Key.Key_M:
            self._bump_activity(ensure_overlays=False)
            self._update_settings_menu()
            self.settings_menu.adjustSize()
            
            # Center of reader window
            center = self.rect().center()
            global_center = self.mapToGlobal(center)
            
            # Adjust so the menu center is at the reader center
            pos = QPoint(
                global_center.x() - self.settings_menu.width() // 2,
                global_center.y() - self.settings_menu.height() // 2
            )
            self.settings_menu.exec(pos)
        elif key == Qt.Key.Key_R:
            # Cycle through Reading Flows: LtR -> RtL -> Continuous
            if not self._rtl and self._page_layout != PageLayout.CONTINUOUS:
                self._set_reading_flow("rtl")
            elif self._rtl and self._page_layout != PageLayout.CONTINUOUS:
                self._set_reading_flow("continuous")
            else:
                self._set_reading_flow("ltr")
        elif key == Qt.Key.Key_L:
            self._cycle_layout()
        elif key == Qt.Key.Key_Home:
            self._go_to(0)
        elif key == Qt.Key.Key_End:
            self._go_to(self._total - 1)
        elif key == Qt.Key.Key_BracketLeft:
            # Left bracket = Previous book (LtR), Next book (RtL)
            asyncio.create_task(self._jump_to_adjacent(1 if self._rtl else -1))
        elif key == Qt.Key.Key_BracketRight:
            # Right bracket = Next book (LtR), Previous book (RtL)
            asyncio.create_task(self._jump_to_adjacent(-1 if self._rtl else 1))
        super().keyPressEvent(event)

    # ------------------------------------------------------------------ #
    # Fullscreen / exit                                                    #
    # ------------------------------------------------------------------ #

    def _do_exit(self):
        self._is_closing = True
        self.on_exit()

    def closeEvent(self, event: QCloseEvent):
        self._is_closing = True
        try:
            self.view.verticalScrollBar().valueChanged.disconnect(self._on_vscroll_changed)
        except Exception:
            pass
        super().closeEvent(event)

    def _toggle_fullscreen(self):
        win = self.window()
        # Redirect to MainWindow's implementation if available to ensure
        # Windows-specific fixes and exit bars are handled correctly.
        if hasattr(win, '_toggle_fullscreen') and win is not self:
            win._toggle_fullscreen()
        else:
            if win.isFullScreen():
                win.showNormal()
            else:
                win.showFullScreen()

    # ------------------------------------------------------------------ #
    # Navigation                                                           #
    # ------------------------------------------------------------------ #

    def _prev(self, is_back: bool = False):
        input_logger.debug(f" >> EXECUTE: _prev(is_back={is_back})")
        logger.debug(f"Reader _prev called. index={self._index}, total={self._total}")
        if self._index > 0:
            step = 2 if self._effective_layout() == PageLayout.DOUBLE else 1
            self._go_to(self._index - step, is_back=is_back)
        else:
            logger.debug("Reader: at first page, triggering prev boundary check")
            asyncio.create_task(self._handle_boundary(-1))

    def _next(self):
        input_logger.debug(" >> EXECUTE: _next()")
        logger.debug(f"Reader _next called. index={self._index}, total={self._total}")
        if self._index < self._total - 1:
            step = 2 if self._effective_layout() == PageLayout.DOUBLE else 1
            self._go_to(self._index + step, is_back=False)
        else:
            logger.debug("Reader: at last page, triggering next boundary check")
            asyncio.create_task(self._handle_boundary(1))

    def _go_to(self, idx: int, is_back: bool = False):
        idx = max(0, min(idx, self._total - 1))
        self._index = idx
        self._bumper_key = None
        self.adjacent_popover.hide()
        
        # Reset overscroll/pull on page change
        self._reset_navigation_state()
        
        asyncio.create_task(self._show_page(is_back=is_back))

    def _on_slider_pressed(self):
        self._slider_dragging = True

    def _on_slider_released(self):
        self._slider_dragging = False
        self._go_to(self.thumb_slider.slider.value())

    def _on_slider_value_changed(self, value: int):
        # While dragging: update counter only, no page load to avoid lag
        if self._slider_dragging:
            self.counter_label.setText(f"{value + 1} / {self._total}")
        else:
            # Not dragging: This is a single-click jump or a programmatic change.
            # Trigger the page load immediately.
            self._go_to(value)

    # ------------------------------------------------------------------ #
    # Settings Menu                                                        #
    # ------------------------------------------------------------------ #

    def _update_settings_menu(self):
        if not hasattr(self, 'settings_menu'): return
        self.settings_menu.clear()
        
        # 1. Commands (Top Priority)
        is_fs = self.window().isFullScreen()
        fs_label = "Exit Full Screen (F11)" if is_fs else "Enter Full Screen (F11)"
        fs_icon = "minimize" if is_fs else "fullscreen"
        
        # Main menu items use standard icons (content_primary)
        fullscreen_action = QAction(fs_label, self)
        fullscreen_action.setIcon(ThemeManager.get_icon(fs_icon, "content_primary"))
        fullscreen_action.triggered.connect(self._toggle_fullscreen)
        self.settings_menu.addAction(fullscreen_action)

        exit_action = QAction("Exit Reader (Esc)", self)
        exit_action.setIcon(ThemeManager.get_icon("back", "content_primary"))
        exit_action.triggered.connect(self._do_exit)
        self.settings_menu.addAction(exit_action)

        help_action = QAction("Show Help (H)", self)
        help_action.setIcon(ThemeManager.get_icon("help", "content_primary"))
        help_action.triggered.connect(self._toggle_help)
        self.settings_menu.addAction(help_action)

        self.settings_menu.addSeparator()

        # 2. Page Quality
        current_q = self.config_manager.get_reader_scaling_mode() if self.config_manager else "smooth"
        q_icons = {"fast": "quality_fast", "smooth": "quality_smooth"}
        
        scaling_q_menu = self.settings_menu.addMenu("Page Quality")
        # Main menu category icons use standard content_primary color
        scaling_q_menu.setIcon(ThemeManager.get_icon(q_icons.get(current_q, "quality_smooth"), "content_primary"))
        
        scale_group = QActionGroup(self)
        for q_mode, label in [("fast", "Fast"), ("smooth", "Smooth")]:
            action = QAction(label, self)
            action.setCheckable(True)
            is_sel = current_q == q_mode
            action.setChecked(is_sel)
            icon_name = q_icons[q_mode]
            # Submenu child actions KEEP the pill style
            action.setIcon(ThemeManager.get_icon(icon_name, pill=True))
            action.triggered.connect(lambda _, m=q_mode: self._set_scaling_quality(m))
            scale_group.addAction(action)
            scaling_q_menu.addAction(action)
            
        # 3. Page Scaling (Fit Modes)
        fit_icons = {
            FitMode.FIT_PAGE: "fit_page", 
            FitMode.FIT_WIDTH: "fit_width", 
            FitMode.FIT_HEIGHT: "fit_height", 
            FitMode.ORIGINAL: "fit_original",
            FitMode.CUSTOM: "settings"
        }
        scaling_menu = self.settings_menu.addMenu("Page Scaling")
        scaling_menu.setIcon(ThemeManager.get_icon(fit_icons.get(self._fit_mode, "fit_page"), "content_primary"))
        
        fit_group = QActionGroup(self)
        for mode in _FIT_CYCLE:
            label = _FIT_LABELS[mode]
            action = QAction(label, self)
            action.setCheckable(True)
            is_sel = self._fit_mode == mode
            action.setChecked(is_sel)
            action.setIcon(ThemeManager.get_icon(fit_icons[mode], pill=True))
            action.triggered.connect(lambda _, m=mode: self._set_fit_mode(m))
            fit_group.addAction(action)
            scaling_menu.addAction(action)
            
        # 4. Display Mode (Layout)
        pref_layout_val = self.config_manager.get_reader_layout() if self.config_manager else "single"
        pref_layout = PageLayout(pref_layout_val)
        layout_icons = {
            PageLayout.SINGLE: "layout_single",
            PageLayout.DOUBLE: "layout_double",
            PageLayout.AUTO: "layout_auto"
        }
        layout_menu = self.settings_menu.addMenu("Display Mode")
        layout_menu.setIcon(ThemeManager.get_icon(layout_icons.get(pref_layout, "layout_single"), "content_primary"))
        
        layout_group = QActionGroup(self)
        for layout in [PageLayout.SINGLE, PageLayout.DOUBLE, PageLayout.AUTO]:
            label = _LAYOUT_LABELS[layout]
            action = QAction(label, self)
            action.setCheckable(True)
            is_sel = pref_layout == layout
            action.setChecked(is_sel)
            action.setIcon(ThemeManager.get_icon(layout_icons[layout], pill=True))
            action.triggered.connect(lambda _, l=layout: self._set_page_layout(l))
            layout_group.addAction(action)
            layout_menu.addAction(action)
            
        # 5. Reading Flow
        current_flow = "ltr"
        if self._page_layout == PageLayout.CONTINUOUS:
            current_flow = "continuous"
        elif self._rtl:
            current_flow = "rtl"
            
        flow_icons = {
            "ltr": "flow_ltr",
            "rtl": "flow_rtl",
            "continuous": "flow_continuous"
        }
        flow_menu = self.settings_menu.addMenu("Reading Flow")
        flow_menu.setIcon(ThemeManager.get_icon(flow_icons.get(current_flow, "flow_ltr"), "content_primary"))
        
        flow_group = QActionGroup(self)
        flow_options = [
            ("ltr", "Left to Right (LtR)"),
            ("rtl", "Right to Left (RtL)"),
            ("continuous", "Continuous Vertical")
        ]
        for f_mode, label in flow_options:
            action = QAction(label, self)
            action.setCheckable(True)
            is_sel = current_flow == f_mode
            action.setChecked(is_sel)
            action.setIcon(ThemeManager.get_icon(flow_icons[f_mode], pill=True))
            action.triggered.connect(lambda _, m=f_mode: self._set_reading_flow(m))
            flow_group.addAction(action)
            flow_menu.addAction(action)

        # 6. Background Color
        bg_menu = self.settings_menu.addMenu("Background Color")
        bg_icons = {
            BackgroundMode.BLACK: "fit_original",
            BackgroundMode.WHITE: "fit_page",
            BackgroundMode.CUSTOM: "settings",
            BackgroundMode.MEDIAN: "quality_smooth",
            BackgroundMode.VIBRANT: "quality_smooth",
            BackgroundMode.CONTRAST: "quality_smooth",
            BackgroundMode.SMOOTH: "quality_smooth",
            BackgroundMode.GRADIENT: "quality_smooth",
            BackgroundMode.CLEAN: "quality_smooth",
            BackgroundMode.VIBE: "quality_smooth",
            BackgroundMode.VIBE_GRADIENT: "quality_smooth",
            BackgroundMode.TEMPORAL_VIBE: "quality_smooth"
        }
        bg_menu.setIcon(ThemeManager.get_icon(bg_icons.get(self._bg_mode, "moon"), "content_primary"))
        
        bg_group = QActionGroup(self)
        for mode in BackgroundMode:
            label = _BG_LABELS[mode]
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(self._bg_mode == mode)
            action.setIcon(ThemeManager.get_icon(bg_icons[mode], pill=True))
            if mode == BackgroundMode.CUSTOM:
                action.triggered.connect(self._set_custom_bg_color)
            else:
                action.triggered.connect(lambda _, m=mode: self._set_bg_mode(m))
            bg_group.addAction(action)
            bg_menu.addAction(action)

        # 7. Trackpad
        trackpad_menu = self.settings_menu.addMenu("Trackpad Settings")
        trackpad_menu.setIcon(ThemeManager.get_icon("trackpad", "content_primary"))

        momentum_enabled = self.config_manager.get_reader_trackpad_momentum() if self.config_manager else False
        mom_action = QAction("Add Trackpad 2D Panning Momentum", self)
        mom_action.setCheckable(True)
        mom_action.setChecked(momentum_enabled)
        mom_action.triggered.connect(self._toggle_trackpad_momentum)
        trackpad_menu.addAction(mom_action)


        
        basic_emu_enabled = self.config_manager.get_reader_trackpad_basic_emulation() if self.config_manager else False
        basic_emu_action = QAction("Trackpad Uses Basic Emulation", self)
        basic_emu_action.setCheckable(True)
        basic_emu_action.setChecked(basic_emu_enabled)
        basic_emu_action.triggered.connect(self._toggle_trackpad_basic_emulation)
        trackpad_menu.addAction(basic_emu_action)

        trackpad_menu.addSeparator()
        wizard_action = QAction("Trackpad Setup Wizard...", self)
        wizard_action.triggered.connect(self._run_trackpad_wizard)
        trackpad_menu.addAction(wizard_action)

        self.settings_menu.addSeparator()

        # 8. Image Filters
        filter_menu = self.settings_menu.addMenu("Image Filters")
        filter_menu.setIcon(ThemeManager.get_icon("filter", "content_primary"))
        
        deyellow_action = QAction("De-Yellow (Auto Contrast)", self)
        deyellow_action.setCheckable(True)
        deyellow_action.setChecked(self._filter_deyellow)
        deyellow_action.triggered.connect(self._toggle_deyellow)
        filter_menu.addAction(deyellow_action)

        self.settings_menu.addSeparator()

        # 9. Interface
        autohide_action = QAction("Auto-Hide Controls", self)
        autohide_action.setCheckable(True)
        autohide_action.setChecked(self._auto_hide_controls)
        autohide_action.triggered.connect(self._toggle_auto_hide)
        self.settings_menu.addAction(autohide_action)

    # ------------------------------------------------------------------ #
    # Fit mode                                                             #
    # ------------------------------------------------------------------ #

    def _set_fit_mode(self, mode: FitMode):
        self._fit_mode = mode
        if self.config_manager and mode != FitMode.CUSTOM:
            self.config_manager.set_reader_fit_mode(mode.value)
        self._update_settings_menu()
        self._apply_fit()

    def _set_scaling_quality(self, mode: str):
        self.config_manager.set_reader_scaling_mode(mode)
        self._update_settings_menu()
        self._apply_fit()
        # Trigger an immediate refresh of the current page to apply high-quality scaling
        asyncio.create_task(self._show_page())

    def _toggle_trackpad_momentum(self, enabled: bool):
        if self.config_manager:
            self.config_manager.set_reader_trackpad_momentum(enabled)
        self._update_settings_menu()



    def _toggle_trackpad_basic_emulation(self, enabled: bool):
        if self.config_manager:
            self.config_manager.set_reader_trackpad_basic_emulation(enabled)
        self._update_settings_menu()

    def _run_trackpad_wizard(self):
        try:
            from .components.trackpad_wizard import TrackpadWizardDialog
            dialog = TrackpadWizardDialog(self.config_manager, self.window())
            dialog.exec()
            self._update_settings_menu()
        except Exception as e:
            input_logger.error(f"Failed to run trackpad wizard: {e}")

    def _toggle_deyellow(self, checked):
        self._filter_deyellow = checked
        if self._page_layout == PageLayout.CONTINUOUS:
            self.clear_display()
            self._load_continuous_layout(center_idx=self._index)
        else:
            asyncio.create_task(self._show_page())

    async def _apply_image_filters_async(self, cache_path: Path) -> Optional[bytes]:
        if not self._filter_deyellow:
            return None
            
        def _process():
            try:
                from PIL import Image, ImageOps
                import io
                img = Image.open(str(cache_path))
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGB")
                img = ImageOps.autocontrast(img, cutoff=1)
                
                if img.mode == "RGBA":
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[3])
                    img = background
                    
                out = io.BytesIO()
                img.save(out, format="JPEG", quality=90)
                return out.getvalue()
            except Exception as e:
                logger.error(f"Filter error on {cache_path}: {e}")
                return None
                
        import asyncio
        return await asyncio.to_thread(_process)

    # ------------------------------------------------------------------ #

    def _get_min_scale(self) -> float:
        """Calculate the scale factor that would fit the page to the window."""
        vp = self.view.viewport()
        if self._effective_layout() == PageLayout.CONTINUOUS:
            if self._continuous_strip_width <= 0: 
                return TrackpadConstants.MIN_SCALE_FALLBACK
            # In continuous mode, we allow zooming out to show multiple pages worth of height.
            target_h = self._continuous_strip_width * TrackpadConstants.DEFAULT_ASPECT_RATIO * TrackpadConstants.CONTINUOUS_VIEW_PAGES
            scale_h = vp.height() / target_h
            # Also ensure it doesn't overflow horizontally
            scale_w = vp.width() / self._continuous_strip_width
            return min(scale_h, scale_w)
        else:
            if self.pixmap_item.base_width <= 0: 
                return TrackpadConstants.MIN_SCALE_FALLBACK
            scale_w = vp.width() / self.pixmap_item.base_width
            scale_h = vp.height() / self.pixmap_item.base_height
            return min(scale_w, scale_h)

    def _zoom(self, factor: float):
        # We need something to zoom
        if self._effective_layout() == PageLayout.CONTINUOUS:
            if not self._continuous_items: return
        else:
            if self.pixmap_item.pixmap().isNull(): return
            
        self._is_transforming = True
        try:
            self._bump_activity(ensure_overlays=False) # Show zoom level label
            
            # 1. Get current and min scale
            current_scale = self.view.transform().m11()
            min_scale = self._get_min_scale()
            
            # 2. Calculate target scale and clamp to floor
            target_scale = current_scale * factor
            
            if target_scale < min_scale:
                if current_scale <= min_scale:
                    # Already at or below floor, snap to Fit Page if not already there
                    if self._fit_mode != FitMode.FIT_PAGE:
                        self._set_fit_mode(FitMode.FIT_PAGE)
                    return
                # Apply exact remainder to reach floor
                factor = min_scale / current_scale

            # 3. Enter Custom mode if zooming in from Fit Page
            if self._fit_mode != FitMode.CUSTOM and factor > 1.0:
                self._set_fit_mode(FitMode.CUSTOM)

            # 4. Apply scale and update
            if abs(factor - 1.0) > TrackpadConstants.SCALE_EPSILON:
                self.view.scale(factor, factor)
                self._update_mipmap_levels()
        finally:
            self._is_transforming = False
            self._custom_scroll_y = float(self.view.verticalScrollBar().value())
            self._custom_scroll_x = float(self.view.horizontalScrollBar().value())
            if self._effective_layout() == PageLayout.CONTINUOUS:
                self._check_continuous_virtualization()

    def _cycle_zoom(self):
        if self.pixmap_item.pixmap().isNull():
            return

        self._is_transforming = True
        try:
            self._bump_activity(ensure_overlays=False) # Show zoom level label
            
            # Multipliers of Fit Page scale
            levels = TrackpadConstants.ZOOM_LEVELS
            self._zoom_cycle_idx = (self._zoom_cycle_idx + 1) % len(levels)
            target_multiplier = levels[self._zoom_cycle_idx]

            if self._zoom_cycle_idx == 0:
                self._set_fit_mode(FitMode.FIT_PAGE)
            else:
                # Capture center in continuous mode
                prev_center = None
                if self._effective_layout() == PageLayout.CONTINUOUS:
                    prev_center = self.view.mapToScene(self.view.viewport().rect().center())

                # Calculate base Fit Page scale
                pm_item = self.pixmap_item
                vp = self.view.viewport()
                base_scale_w = vp.width() / max(1, pm_item.base_width)
                base_scale_h = vp.height() / max(1, pm_item.base_height)
                base_scale = min(base_scale_w, base_scale_h)

                target_total_scale = base_scale * target_multiplier
                
                self._set_fit_mode(FitMode.CUSTOM)
                self.view.resetTransform()
                self.view.scale(target_total_scale, target_total_scale)

                # Restore center
                if prev_center:
                    self.view.centerOn(prev_center)

                self._update_mipmap_levels()
        finally:
            self._is_transforming = False
            self._custom_scroll_y = float(self.view.verticalScrollBar().value())
            self._custom_scroll_x = float(self.view.horizontalScrollBar().value())
            if self._effective_layout() == PageLayout.CONTINUOUS:
                self._check_continuous_virtualization()

    def _cycle_fit(self):
        try:
            i = _FIT_CYCLE.index(self._fit_mode)
            next_mode = _FIT_CYCLE[(i + 1) % len(_FIT_CYCLE)]
        except ValueError:
            # If current mode is CUSTOM or otherwise not in cycle, go to first mode
            next_mode = _FIT_CYCLE[0]
        self._set_fit_mode(next_mode)

    def _apply_fit(self):
        self._is_transforming = True
        # Programmatic fit should always center, not follow the mouse
        old_anchor = self.view.transformationAnchor()
        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        
        try:
            vp  = self.view.viewport()
            off = Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            on  = Qt.ScrollBarPolicy.ScrollBarAsNeeded

            # Apply scaling mode from comiccatcher.config
            mode = self.config_manager.get_reader_scaling_mode() if self.config_manager else "smooth"
            is_fast = (mode == "fast")
            logger.debug(f"Reader: Applying {mode} scaling (is_fast={is_fast})")
            
            t_mode = Qt.TransformationMode.FastTransformation if is_fast else Qt.TransformationMode.SmoothTransformation
            
            # Be very aggressive with render hints
            self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, not is_fast)
            self.view.setRenderHint(QPainter.RenderHint.Antialiasing, not is_fast)
            
            # Apply to main page
            if hasattr(self.pixmap_item, 'set_smooth'):
                self.pixmap_item.set_smooth(not is_fast)
            elif not self.pixmap_item.pixmap().isNull():
                self.pixmap_item.setTransformationMode(t_mode)
                
            # Apply to all continuous pages
            for it in self._continuous_items.values():
                if hasattr(it, 'set_smooth'):
                    it.set_smooth(not is_fast)
                else:
                    it.setTransformationMode(t_mode)
                
            self.view.viewport().update()

            if self._effective_layout() == PageLayout.CONTINUOUS:
                if not self._continuous_items:
                    return

                if self._fit_mode == FitMode.CUSTOM:
                    self._update_mipmap_levels()
                    return

                # Capture center before reset
                prev_center = self.view.mapToScene(self.view.viewport().rect().center())

                self.view.resetTransform()
                if self._continuous_strip_width > 0:
                    if self._fit_mode == FitMode.FIT_PAGE:
                        # In continuous mode, "Fit Page" acts as a zoomed-out mode.
                        # We target showing multiple page-heights (defined by constant)
                        target_h = self._continuous_strip_width * TrackpadConstants.DEFAULT_ASPECT_RATIO * TrackpadConstants.CONTINUOUS_VIEW_PAGES
                        scale_h = vp.height() / target_h
                        # Also ensure it doesn't overflow horizontally
                        scale_w = vp.width() / self._continuous_strip_width
                        scale = min(scale_h, scale_w)
                        self.view.scale(scale, scale)
                    elif self._fit_mode == FitMode.FIT_WIDTH:
                        scale = vp.width() / self._continuous_strip_width
                        self.view.scale(scale, scale)
                    elif self._fit_mode == FitMode.ORIGINAL:
                        pass # 1:1 scale

                # Restore center
                self.view.centerOn(prev_center)

                self._update_mipmap_levels()
                return

            if self.pixmap_item.pixmap().isNull():
                return
            pm_item  = self.pixmap_item

            if self._fit_mode == FitMode.FIT_PAGE:
                self.view.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

            elif self._fit_mode == FitMode.FIT_WIDTH:
                if pm_item.base_width > 0:
                    self.view.resetTransform()
                    self.view.scale(vp.width() / pm_item.base_width, vp.width() / pm_item.base_width)

            elif self._fit_mode == FitMode.FIT_HEIGHT:
                if pm_item.base_height > 0:
                    self.view.resetTransform()
                    self.view.scale(vp.height() / pm_item.base_height, vp.height() / pm_item.base_height)

            elif self._fit_mode == FitMode.ORIGINAL:
                self.view.resetTransform()

            elif self._fit_mode == FitMode.CUSTOM:
                pass

            self._update_mipmap_levels()
        finally:
            self.view.setTransformationAnchor(old_anchor)
            self._is_transforming = False
            self._custom_scroll_y = float(self.view.verticalScrollBar().value())
            self._custom_scroll_x = float(self.view.horizontalScrollBar().value())
            # Trigger one final sync virtualization after everything is stable
            if self._effective_layout() == PageLayout.CONTINUOUS:
                self._check_continuous_virtualization()

    def _update_mipmap_levels(self):
        try:
            view_scale = self.view.transform().m11()
            
            # Update zoom label (e.g. 125%)
            if hasattr(self, "zoom_label"):
                self.zoom_label.setText(f"{int(view_scale * 100)}%")

            if hasattr(self.pixmap_item, 'update_mipmap_level') and not self.pixmap_item.pixmap().isNull():
                self.pixmap_item.update_mipmap_level(view_scale)
            for it in self._continuous_items.values():
                if hasattr(it, 'update_mipmap_level') and not it.pixmap().isNull():
                    it.update_mipmap_level(view_scale)

            self._update_reader_cursor()
        except Exception as e:
            logger.error(f"Error updating mipmaps: {e}")

    # ------------------------------------------------------------------ #
    # Page layout                                                          #
    # ------------------------------------------------------------------ #

    def _effective_layout(self) -> PageLayout:
        """Resolve AUTO to SINGLE or DOUBLE based on current viewport shape."""
        if self._page_layout == PageLayout.AUTO:
            vp = self.view.viewport()
            return PageLayout.DOUBLE if vp.width() > vp.height() else PageLayout.SINGLE
        return self._page_layout

    def _clear_continuous_state(self):
        """Resets all state related to Continuous mode."""
        self._continuous_session_id += 1
        
        # Remove all items from scene EXCEPT the master pixmap_item and the container
        for item in self.scene.items():
            if item is self.pixmap_item or item is self.content_container:
                continue
            try:
                self.scene.removeItem(item)
            except RuntimeError:
                pass
                
        self._continuous_items.clear()
        self._continuous_y_offsets.clear()
        self._continuous_loading.clear()
        self._custom_scroll_velocity_y = 0.0
        self._custom_scroll_velocity_x = 0.0
        self._custom_scroll_y = 0.0
        self._custom_scroll_x = 0.0
        self._kinetic_timer.stop()

    def _sync_continuous_scene_rect(self):
        """Updates the sceneRect to exactly fit currently loaded items."""
        if not self._continuous_items:
            return
            
        all_ys = []
        for it in self._continuous_items.values():
            all_ys.append(it.pos().y())
            all_ys.append(it.pos().y() + (it.base_height * it._base_scale))
            
        self._continuous_min_y = min(all_ys)
        self._continuous_max_y = max(all_ys)
        
        self.scene.setSceneRect(0, self._continuous_min_y, self._continuous_strip_width, self._continuous_max_y - self._continuous_min_y)

    def _set_page_layout(self, layout: PageLayout):
        self._page_layout = layout
        # If we selected a standard layout, ensure we aren't in continuous flow anymore
        if self.config_manager and self.config_manager.get_reader_flow() == "continuous":
            self.config_manager.set_reader_flow("rtl" if self._rtl else "ltr")

        if self.config_manager:
            self.config_manager.set_reader_layout(layout.value)

        self._update_slider_direction()
        self._update_settings_menu()
        asyncio.create_task(self._show_page())
    def _cycle_layout(self):
        i = _LAYOUT_CYCLE.index(self._page_layout)
        next_layout = _LAYOUT_CYCLE[(i + 1) % len(_LAYOUT_CYCLE)]
        self._set_page_layout(next_layout)

    # ------------------------------------------------------------------ #
    # Thumbnail slider toggle                                              #
    # ------------------------------------------------------------------ #

    def _set_thumbnails_visible(self, visible: bool):
        self._thumb_visible = visible
        if self.config_manager:
            self.config_manager.set_reader_thumbs_visible(visible)
        self.thumb_slider.setVisible(self._thumb_visible)
        if not self._thumb_visible:
            self.thumb_slider.hide_popup()
        self._update_settings_menu()
        self._layout_overlays()

    def _toggle_thumb_slider(self):
        self._set_thumbnails_visible(not self._thumb_visible)

    # ------------------------------------------------------------------ #
    # Direction / Flow                                                     #
    # ------------------------------------------------------------------ #

    def _set_reading_flow(self, flow: str):
        if flow == "ltr":
            self._rtl = False
            if self._page_layout == PageLayout.CONTINUOUS:
                saved = self.config_manager.get_reader_layout() if self.config_manager else "single"
                # If the saved value is also 'continuous', fallback to 'single' to avoid getting stuck
                if saved == "continuous": saved = "single"
                self._page_layout = PageLayout(saved)
        elif flow == "rtl":
            self._rtl = True
            if self._page_layout == PageLayout.CONTINUOUS:
                saved = self.config_manager.get_reader_layout() if self.config_manager else "single"
                if saved == "continuous": saved = "single"
                self._page_layout = PageLayout(saved)
        elif flow == "continuous":
            self._page_layout = PageLayout.CONTINUOUS
            
        self._update_slider_direction()

        if self.config_manager:
            self.config_manager.set_reader_flow(flow)
            # Update the layout in config as well so it matches our restored state
            self.config_manager.set_reader_layout(self._page_layout.value)
            
        self._update_settings_menu()
        asyncio.create_task(self._show_page())

    def _set_bg_mode(self, mode: BackgroundMode):
        self._bg_mode = mode
        if self.config_manager:
            self.config_manager.set_reader_bg_mode(mode.value)
        
        self._update_background()
        self.reapply_theme() # Full reapply to handle text contrast

    def _update_slider_direction(self):
        """Update the scrub bar's visual and logical direction."""
        # Force LtR (Normal) direction for Continuous Vertical mode.
        is_rtl_visual = self._rtl and self._page_layout != PageLayout.CONTINUOUS
        
        self.thumb_slider.slider.setInvertedAppearance(is_rtl_visual)
        self.thumb_slider.slider.setProperty("rtl", is_rtl_visual)
        self.thumb_slider.slider.style().unpolish(self.thumb_slider.slider)
        self.thumb_slider.slider.style().polish(self.thumb_slider.slider)

    def _set_custom_bg_color(self):
        color = QColorDialog.getColor(self._custom_bg_color, self, "Select Background Color")
        if color.isValid():
            self._custom_bg_color = color
            self._bg_mode = BackgroundMode.CUSTOM
            if self.config_manager:
                self.config_manager.set_reader_bg_mode("custom")
                self.config_manager.set_reader_bg_color(color.name())
            
            self._update_background()
            self.reapply_theme()

    # ------------------------------------------------------------------ #
    # Page display (called by subclasses after data is ready)             #
    # ------------------------------------------------------------------ #

    def clear_display(self):
        """Immediately blank the canvas and labels (prevents prior-comic flash)."""
        self._is_closing = False
        self.pixmap_item.setPixmap(QPixmap())
        
        self._clear_continuous_state()
                
        self.title_label.setText("")
        self.counter_label.setText("0 / 0")
        self.thumb_slider.clear()
        
        self.thumb_slider.slider.blockSignals(True)
        self.thumb_slider.slider.setRange(0, 0)
        self.thumb_slider.slider.setValue(0)
        self.thumb_slider.slider.blockSignals(False)

    def _setup_reader(self, title: str, total: int, subtitle: str = None, start_index: int = 0):
        """Call once the page list / reading order is known."""
        self._total = total
        self._index = max(0, min(start_index, total - 1))
        
        s = UIConstants.scale
        display_text = f'<span style="font-size: {s(19)}px;">{title}</span>'
        if subtitle and subtitle.strip():
            display_text += f'<br/><i style="font-size: {s(15)}px; color: #bbb; font-weight: normal;">{subtitle.strip()}</i>'
            
        self.title_label.setText(display_text)
        
        self.thumb_slider.slider.blockSignals(True)
        self.thumb_slider.slider.setRange(0, max(0, total - 1))
        self.thumb_slider.slider.setValue(self._index)
        self.thumb_slider.slider.blockSignals(False)

        self.setFocus()

    async def _show_page(self, is_back: bool = False):
        idx = self._index
        if not (0 <= idx < self._total):
            return

        layout = self._effective_layout()
        
        # 1. Update UI Labels and Slider state for all modes
        double    = layout == PageLayout.DOUBLE
        idx2      = idx + 1 if double and idx + 1 < self._total else None
        page_desc = (f"{idx + 1}–{idx2 + 1}" if idx2 is not None else str(idx + 1))
        self.counter_label.setText(f"{page_desc} / {self._total}")

        self.thumb_slider.slider.blockSignals(True)
        self.thumb_slider.slider.setValue(idx)
        self.thumb_slider.slider.blockSignals(False)

        # 2. Handle Continuous Vertical Layout
        if layout == PageLayout.CONTINUOUS:
            self.pixmap_item.setVisible(False)
            
            # If jumping far away, clear scene
            if idx not in self._continuous_items:
                self._clear_continuous_state()
                asyncio.create_task(self._load_continuous_page_initial(idx))
            else:
                # Scroll to it
                item = self._continuous_items[idx]
                self.view.ensureVisible(item, 0, 0)

            self._on_page_changed(idx)
            return
        
        # 3. Handle Paginated Layouts (Single/Double)
        # Non-continuous mode: clean up continuous items if they exist
        if self._continuous_items:
            self._clear_continuous_state()
        
        self.pixmap_item.setVisible(True)

        if idx2 is not None:
            pm1, pm2 = await asyncio.gather(
                self._load_page_pixmap(idx),
                self._load_page_pixmap(idx2),
            )
            if self._is_closing: return
            
            # Check layout again after await - another mode might have taken over!
            if self._effective_layout() == PageLayout.CONTINUOUS:
                logger.debug("Reader _show_page: Discarding paginated spread as Continuous mode is now active.")
                return

            if idx != self._index:
                return
            if pm1 and pm2 and not pm1.isNull() and not pm2.isNull():
                pixmap = _compose_spread(pm1, pm2)
                self.thumb_slider.store_thumb(idx, pm1)
                self.thumb_slider.store_thumb(idx2, pm2)
            else:
                pixmap = pm1  # fallback to single if second page missing
                if pm1 and not pm1.isNull():
                    self.thumb_slider.store_thumb(idx, pm1)
        else:
            pixmap = await self._load_page_pixmap(idx)
            if self._is_closing: return
            
            # Check layout again after await
            if self._effective_layout() == PageLayout.CONTINUOUS:
                logger.debug("Reader _show_page: Discarding paginated page as Continuous mode is now active.")
                return

            if idx != self._index:
                return
            if pixmap and not pixmap.isNull():
                self.thumb_slider.store_thumb(idx, pixmap)

        if pixmap and not pixmap.isNull():
            self.pixmap_item.setPixmap(pixmap)
            self.scene.setSceneRect(self.pixmap_item.boundingRect())
            self._apply_fit()
            self._update_background(pixmap)
            
            # Reset scroll position to appropriate corner
            vbar = self.view.verticalScrollBar()
            hbar = self.view.horizontalScrollBar()
            
            if is_back:
                # Reset to END corner
                vbar.setValue(vbar.maximum())
                if self._rtl:
                    hbar.setValue(hbar.minimum())
                else:
                    hbar.setValue(hbar.maximum())
            else:
                # Reset to START corner
                vbar.setValue(vbar.minimum())
                if self._rtl:
                    hbar.setValue(hbar.maximum())
                else:
                    hbar.setValue(hbar.minimum())

        # Prefetch ahead and one behind for back-navigation
        ahead_start = (idx2 or idx) + 1
        for j in range(ahead_start, min(self._total, ahead_start + self.PREFETCH_AHEAD)):
            asyncio.create_task(self._do_prefetch(j))
        if idx > 0:
            asyncio.create_task(self._do_prefetch(idx - 1))

        self._on_page_changed(idx)

    async def _load_continuous_page_initial(self, start_idx: int):
        async with self._continuous_task_lock:
            # Clear everything again inside the lock to ensure consistency
            self._clear_continuous_state()
            session_id = self._continuous_session_id
            
            cont_logger.debug(f"Continuous INITIAL (Session {session_id}): Requesting index {start_idx}")
            pm = await self._load_page_pixmap(start_idx)
            if self._is_closing: return
            
            # Check if session changed while we were awaiting
            if session_id != self._continuous_session_id:
                cont_logger.debug(f"Continuous INITIAL (Session {session_id}): Discarding stale session load.")
                return

            if not pm or pm.isNull():
                cont_logger.warning(f"Continuous INITIAL: Failed to load index {start_idx}")
                return
            self.thumb_slider.store_thumb(start_idx, pm)

            self._continuous_strip_width = pm.width() or 1000.0
            cont_logger.debug(f"Continuous INITIAL: Base strip width set to {self._continuous_strip_width}")
            
            item = MipmapPixmapItem(pm)
            item.set_base_scale(1.0)
            item.setParentItem(self.content_container)
            self._continuous_items[start_idx] = item
            
            item.setPos(0, 0)
            self._continuous_y_offsets[start_idx] = 0.0
            self._continuous_min_y = 0.0
            self._continuous_max_y = pm.height()
            
            self.scene.setSceneRect(0, 0, self._continuous_strip_width, self._continuous_max_y)
            self._apply_fit()
            self.view.verticalScrollBar().setValue(0)
            self._update_background(pm)
            
            cont_logger.debug(f"Continuous INITIAL: Setup complete. sceneRect=(0, {self._continuous_min_y}, {self._continuous_strip_width}, {self._continuous_max_y})")

        # Prefetch adjacent (outside the main session lock)
        if start_idx + 1 < self._total:
            asyncio.create_task(self._load_continuous_page_append(start_idx + 1, session_id))
        if start_idx - 1 >= 0:
            asyncio.create_task(self._load_continuous_page_prepend(start_idx - 1, session_id))

    async def _load_continuous_page_append(self, idx: int, session_id: int):
        if session_id != self._continuous_session_id: return
        if idx >= self._total or idx in self._continuous_items: return
        try:
            cont_logger.debug(f"Continuous APPEND (Session {session_id}): Fetching index {idx}")
            pm = await self._load_page_pixmap(idx)
            if self._is_closing: return
            
            if session_id != self._continuous_session_id: return
            if idx in self._continuous_items: return

            if not pm or pm.isNull():
                cont_logger.warning(f"Continuous APPEND: Failed to load index {idx}")
                return
            self.thumb_slider.store_thumb(idx, pm)
            
            item = MipmapPixmapItem(pm)
            scale = self._continuous_strip_width / pm.width() if pm.width() else 1.0
            item.set_base_scale(scale)
            
            # Position relative to immediate neighbor to ensure NO GAPS
            if idx - 1 in self._continuous_items:
                prev = self._continuous_items[idx - 1]
                target_y = prev.pos().y() + (prev.base_height * prev._base_scale) - 1.0
            elif idx + 1 in self._continuous_items:
                nxt = self._continuous_items[idx + 1]
                target_y = nxt.pos().y() - (pm.height() * scale) + 1.0
            else:
                target_y = self._continuous_max_y - 1.0

            item.setParentItem(self.content_container)
            item.setPos(0, target_y)
            self._continuous_items[idx] = item
            self._continuous_y_offsets[idx] = target_y
            
            # Ensure it starts with the correct mipmap level for the current zoom
            item.update_mipmap_level(self.view.transform().m11())
            
            # Re-sync overall scene boundaries from all loaded items to prevent drift
            self._sync_continuous_scene_rect()
            
            cont_logger.debug(f"Continuous APPEND: Added {idx} at Y={target_y:.1f}, SceneRect={self.scene.sceneRect()}")
        finally:
            self._continuous_loading.discard(idx)

    async def _load_continuous_page_prepend(self, idx: int, session_id: int):
        if session_id != self._continuous_session_id: return
        if idx < 0 or idx in self._continuous_items: return
        try:
            cont_logger.debug(f"Continuous PREPEND (Session {session_id}): Fetching index {idx}")
            pm = await self._load_page_pixmap(idx)
            if self._is_closing: return
            
            if session_id != self._continuous_session_id: return
            if idx in self._continuous_items: return

            if not pm or pm.isNull():
                cont_logger.warning(f"Continuous PREPEND: Failed to load index {idx}")
                return
            self.thumb_slider.store_thumb(idx, pm)
            
            item = MipmapPixmapItem(pm)
            scale = self._continuous_strip_width / pm.width() if pm.width() else 1.0
            item.set_base_scale(scale)
            
            new_h = (pm.height() * scale) - 1.0
            
            # Position relative to immediate neighbor
            if idx + 1 in self._continuous_items:
                nxt = self._continuous_items[idx + 1]
                target_y = nxt.pos().y() - new_h
            elif idx - 1 in self._continuous_items:
                prev = self._continuous_items[idx - 1]
                target_y = prev.pos().y() + (prev.base_height * prev._base_scale) - 1.0
            else:
                target_y = self._continuous_min_y - new_h

            item.setParentItem(self.content_container)
            item.setPos(0, target_y)
            self._continuous_items[idx] = item
            self._continuous_y_offsets[idx] = target_y
            
            # Ensure it starts with the correct mipmap level for the current zoom
            item.update_mipmap_level(self.view.transform().m11())
            
            # Re-sync overall boundaries
            self._sync_continuous_scene_rect()
            
            cont_logger.debug(f"Continuous PREPEND: Added {idx} at Y={target_y:.1f}, SceneRect={self.scene.sceneRect()}")
        finally:
            self._continuous_loading.discard(idx)

    def _on_vscroll_changed(self, value):
        if self._is_transforming:
            return
            
        # Sync logical position if not dragging (e.g. keyboard scroll)
        if self._last_drag_y is None and not self._kinetic_timer.isActive():
            self._custom_scroll_y = float(value)
            
        self._check_continuous_virtualization()
            
    def _on_hscroll_changed(self, value):
        if self._is_transforming:
            return
            
        # Sync logical position if not dragging (e.g. keyboard/wheel scroll)
        if self._last_drag_x is None and not self._kinetic_timer.isActive():
            self._custom_scroll_x = float(value)

    def _check_continuous_virtualization(self):
        if self._is_closing or self._page_layout != PageLayout.CONTINUOUS or not self._continuous_items:
            return
            
        vp = self.view.viewport()
        vbar = self.view.verticalScrollBar()
        if vbar.minimum() == vbar.maximum() and self._total > 1:
            return

        scene_top = self.view.mapToScene(0, 0).y()
        scene_bottom = self.view.mapToScene(0, vp.height()).y()
        scene_center = self.view.mapToScene(0, vp.height() // 2).y()
        
        visible_idx = self._index
        min_visible = float('inf')
        max_visible = float('-inf')
        
        # Track physical loaded bounds
        loaded_min_y = float('inf')
        loaded_max_y = float('-inf')

        for idx, item in self._continuous_items.items():
            try:
                # Use scenePos() to account for visual overscroll translation
                item_y = item.scenePos().y()
                item_h = item.base_height * item._base_scale
                
                # Base loaded bounds ignore the overscroll offset for logic consistency
                base_y = item.pos().y()
                loaded_min_y = min(loaded_min_y, base_y)
                loaded_max_y = max(loaded_max_y, base_y + item_h)

                if item_y <= scene_center < item_y + item_h:
                    visible_idx = idx
                if item_y < scene_bottom and item_y + item_h > scene_top:
                    min_visible = min(min_visible, idx)
                    max_visible = max(max_visible, idx)
            except RuntimeError:
                continue
                
        if min_visible == float('inf'):
            min_visible = max_visible = visible_idx

        if visible_idx != self._index:
            cont_logger.debug(f"Continuous Scroll: Viewport center crossed into index {visible_idx}")
            self._index = visible_idx
            try:
                self.counter_label.setText(f"{visible_idx + 1} / {self._total}")
                self.thumb_slider.slider.blockSignals(True)
                self.thumb_slider.slider.setValue(visible_idx)
                self.thumb_slider.slider.blockSignals(False)
                self._on_page_changed(visible_idx)
                self._update_background()
            except RuntimeError:
                pass
            
        try:
            # Physical Virtualization: distance to the actual edges of loaded content
            dist_to_top_edge = scene_top - loaded_min_y
            dist_to_bottom_edge = loaded_max_y - scene_bottom
            
            # 1. UNLOAD pages physically far away (more than 3 viewports distance)
            unload_threshold = vp.height() * 3.0
            keep_range = range(min_visible - 4, max_visible + 5)
            
            keys_to_remove = []
            for k, item in self._continuous_items.items():
                if k in keep_range: continue
                
                item_y = item.pos().y()
                item_h = item.base_height * item._base_scale
                if item_y + item_h < scene_top - unload_threshold or item_y > scene_bottom + unload_threshold:
                    keys_to_remove.append(k)

            for k in keys_to_remove:
                cont_logger.debug(f"Continuous Virtualization: Unloading offscreen index {k}")
                item = self._continuous_items.pop(k)
                self.scene.removeItem(item)
            
            if keys_to_remove:
                self._sync_continuous_scene_rect()
                
            # 2. LOAD more if we are within 1.5 viewports of a loaded edge
            load_threshold = vp.height() * 1.5
            
            max_loaded_idx = max(self._continuous_items.keys(), default=visible_idx)
            if max_loaded_idx < self._total - 1 and dist_to_bottom_edge < load_threshold:
                next_idx = max_loaded_idx + 1
                if next_idx not in self._continuous_loading:
                    self._continuous_loading.add(next_idx)
                    cont_logger.debug(f"Continuous Virtualization: dist_to_bottom={dist_to_bottom_edge:.1f}, loading APPEND {next_idx}")
                    asyncio.create_task(self._load_continuous_page_append(next_idx, self._continuous_session_id))
                
            min_loaded_idx = min(self._continuous_items.keys(), default=visible_idx)
            if min_loaded_idx > 0 and dist_to_top_edge < load_threshold:
                prev_idx = min_loaded_idx - 1
                if prev_idx not in self._continuous_loading:
                    self._continuous_loading.add(prev_idx)
                    cont_logger.debug(f"Continuous Virtualization: dist_to_top={dist_to_top_edge:.1f}, loading PREPEND {prev_idx}")
                    asyncio.create_task(self._load_continuous_page_prepend(prev_idx, self._continuous_session_id))
        except (RuntimeError, ValueError):
            pass
        pass
