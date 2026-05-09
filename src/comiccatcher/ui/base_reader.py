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
import time
from typing import Optional, Callable, Any

from PyQt6.QtCore import Qt, QEvent, QPoint, QTimer, QSize, QRectF, QPropertyAnimation, pyqtProperty
from PyQt6.QtGui import QKeyEvent, QPainter, QPixmap, QAction, QActionGroup, QColor, QCloseEvent, QNativeGestureEvent, QLinearGradient, QBrush
from PyQt6.QtWidgets import (
    QFrame, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView,
    QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget, QMenu,
    QGraphicsDropShadowEffect, QApplication, QScroller, QScrollerProperties,
    QColorDialog
)

import sys
import os
from comiccatcher.logger import get_logger
from comiccatcher.api.image_manager import ImageManager
from comiccatcher.ui.theme_manager import ThemeManager, UIConstants, THEMES
from comiccatcher.ui.components.mini_detail_popover import MiniDetailPopover
from comiccatcher.ui.components.popover_mixin import BubbleMixin
from comiccatcher.ui.win_utils import apply_windows_popover_fix

logger = get_logger("ui.base_reader")
input_logger = get_logger("input")
cont_logger = get_logger("cont")

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


# Background mode
# ---------------------------------------------------------------------------

class BackgroundMode(enum.Enum):
    BLACK   = "black"
    WHITE   = "white"
    CUSTOM  = "custom"
    MEAN    = "mean"
    MEDIAN  = "median"
    MODE    = "mode"
    MODE_MEAN = "mode_mean"
    VIBRANT   = "vibrant"
    CONTRAST  = "contrast"
    SMOOTH    = "smooth"
    GRADIENT  = "gradient"
    CLEAN     = "clean"


_BG_LABELS = {
    BackgroundMode.BLACK: "Black",
    BackgroundMode.WHITE: "White",
    BackgroundMode.CUSTOM: "Custom Color...",
    BackgroundMode.MEAN: "Sampling: Mean (Exp)",
    BackgroundMode.MEDIAN: "Sampling: Median (Exp)",
    BackgroundMode.MODE: "Sampling: Mode (Exp)",
    BackgroundMode.MODE_MEAN: "Sampling: Mode Mean (Exp)",
    BackgroundMode.VIBRANT: "Sampling: Most Vibrant (Exp)",
    BackgroundMode.CONTRAST: "Sampling: Contrast Frame (Exp)",
    BackgroundMode.SMOOTH: "Sampling: Temporal Mean (Exp)",
    BackgroundMode.GRADIENT: "Sampling: 4-Way Gradient (Exp)",
    BackgroundMode.CLEAN: "Sampling: Clean Margin (Exp)",
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

        def scale_images():
            if qimage.isNull(): return None
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
                # Apply if needed
                if self.scene() and self.scene().views():
                    view = self.scene().views()[0]
                    self.update_mipmap_level(view.transform().m11())
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

        # Determine appropriate target mipmap level considering our base scale
        effective_scale = view_scale * self._base_scale
        target_level = 1.0
        if effective_scale <= 0.25 and 0.25 in self._mipmaps:
            target_level = 0.25
        elif effective_scale <= 0.50 and 0.50 in self._mipmaps:
            target_level = 0.50

        if target_level != self._current_level:
            self._current_level = target_level
            pm = self._mipmaps[target_level]
            super().setPixmap(pm)
            # Adjust internal scale to match the physical size of 1.0, preserving our base scale
            self.setScale((1.0 / target_level) * self._base_scale)


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
    
    # Touchpad Scroll Settings
    TOUCHPAD_SCROLL_THRESHOLD = 120   # Units required to trigger a "notch" (120 = 1 mouse wheel click)
    TOUCHPAD_VELOCITY_THRESHOLD = 75  # Units/sec. Drop below this to unlock the next notch.
    SWIPE_COOLDOWN_MS = 250          # Fallback lock duration if velocity isn't detected.
    
    # Zoom Settings
    ZOOM_STEP_IN = 1.05
    ZOOM_STEP_OUT = 0.95
    
    # Smart Panning Settings
    SMART_PAN_STEP_H_PCT = 0.15
    SMART_PAN_STEP_V_PCT = 0.4
    
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
        self._scroll_accumulator = 0 # Accumulates high-precision deltas (touchpad)
        self._horizontal_swipe_accumulator = 0
        self._last_wheel_event_time = 0
        self._swipe_locked = False
        self._ignore_next_release = False # Suppress click handling after a double-click
        
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._on_click_timer_timeout)
        self._pending_click_pos = None

        self._swipe_lock_timer = QTimer(self)
        self._swipe_lock_timer.setSingleShot(True)
        self._swipe_lock_timer.setInterval(self.SWIPE_COOLDOWN_MS)
        self._swipe_lock_timer.timeout.connect(self._unlock_swipe)

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
        self._mouse_press_pos = None
        self._zoom_cycle_idx = 0

        # Kinetic scrolling (momentum)
        QScroller.grabGesture(self.view.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        scroller = QScroller.scroller(self.view.viewport())
        props = scroller.scrollerProperties()
        # Ensure it feels responsive and "flickable"
        props.setScrollMetric(QScrollerProperties.ScrollMetric.DragVelocitySmoothingFactor, 0.5)
        props.setScrollMetric(QScrollerProperties.ScrollMetric.MinimumVelocity, 0.0)
        props.setScrollMetric(QScrollerProperties.ScrollMetric.MaximumVelocity, 0.8)
        props.setScrollMetric(QScrollerProperties.ScrollMetric.DecelerationFactor, 0.15)
        # Bouncing at edges can be annoying for comics, disable overshoot by default
        props.setScrollMetric(QScrollerProperties.ScrollMetric.HorizontalOvershootPolicy, QScrollerProperties.OvershootPolicy.OvershootAlwaysOff)
        props.setScrollMetric(QScrollerProperties.ScrollMetric.VerticalOvershootPolicy, QScrollerProperties.OvershootPolicy.OvershootAlwaysOff)
        scroller.setScrollerProperties(props)
        scroller.stateChanged.connect(self._on_scroller_state_changed)

        self.pixmap_item = MipmapPixmapItem()
        self.scene.addItem(self.pixmap_item)

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

        self.view.viewport().installEventFilter(self)
        self.view.installEventFilter(self)
        self.header.installEventFilter(self)
        self.footer.installEventFilter(self)
        for b in (self.btn_back, self.btn_settings):
            b.installEventFilter(self)
        self.installEventFilter(self)
        
        self.view.verticalScrollBar().valueChanged.connect(self._on_vscroll_changed)

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
        color = self._current_bg_color
        is_gradient = self._bg_mode == BackgroundMode.GRADIENT and hasattr(self, '_current_bg_gradient')
        
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
            BackgroundMode.MEAN, BackgroundMode.MEDIAN, BackgroundMode.MODE,
            BackgroundMode.MODE_MEAN, BackgroundMode.VIBRANT, BackgroundMode.CONTRAST,
            BackgroundMode.SMOOTH, BackgroundMode.GRADIENT, BackgroundMode.CLEAN
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
                new_color = self._get_edge_color(target)
            else:
                new_color = QColor(Qt.GlobalColor.black)
        
        if self._bg_mode == BackgroundMode.SMOOTH:
            self._bg_anim.stop()
            self._bg_anim.setStartValue(old_color)
            self._bg_anim.setEndValue(new_color)
            self._bg_anim.start()
        else:
            self.bg_color = new_color # Uses setter for immediate apply

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
            
        if self._bg_mode == BackgroundMode.MEAN:
            r = sum(p.red() for p in pixels) // len(pixels)
            g = sum(p.green() for p in pixels) // len(pixels)
            b = sum(p.blue() for p in pixels) // len(pixels)
            return QColor(r, g, b)
            
        elif self._bg_mode == BackgroundMode.MEDIAN:
            rs = sorted(p.red() for p in pixels)
            gs = sorted(p.green() for p in pixels)
            bs = sorted(p.blue() for p in pixels)
            mid = len(pixels) // 2
            return QColor(rs[mid], gs[mid], bs[mid])
            
        elif self._bg_mode == BackgroundMode.MODE:
            from collections import Counter
            counts = Counter((p.red(), p.green(), p.blue()) for p in pixels)
            most_common = counts.most_common(1)[0][0]
            return QColor(*most_common)
            
        elif self._bg_mode == BackgroundMode.MODE_MEAN:
            # Bin colors to group similar shades, then take the mean of the largest bin
            from collections import defaultdict
            bins = defaultdict(list)
            STEP = 24 # 256 / 24 = ~10 bins per channel
            
            for p in pixels:
                # Simple quantization binning
                bin_key = (p.red() // STEP, p.green() // STEP, p.blue() // STEP)
                bins[bin_key].append(p)
            
            # Find the bin with the most pixels
            target_bin = max(bins.values(), key=len)
            
            r = sum(p.red() for p in target_bin) // len(target_bin)
            g = sum(p.green() for p in target_bin) // len(target_bin)
            b = sum(p.blue() for p in target_bin) // len(target_bin)
            return QColor(r, g, b)

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

    def _on_scroller_state_changed(self, state):
        if state == QScroller.State.Dragging:
            self.view.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            self._bump_activity(ensure_overlays=False) # Keep cursor visible while dragging
        elif state == QScroller.State.Scrolling:
            self.view.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            self._bump_activity(ensure_overlays=False) # Keep cursor visible while coasting
        elif state == QScroller.State.Inactive:
            self._update_reader_cursor()

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
            g_type = event.gestureType()
            val = event.value()
            input_logger.debug(f"GESTURE: type={g_type.name} val={val:.4f} locked={self._swipe_locked}")

            # Engage the navigation lock for ALL gestures. 
            # A pinch-zoom often starts as a small Pan or Rotate.
            self._horizontal_swipe_accumulator = 0
            self._scroll_accumulator = 0
            self._swipe_locked = True
            self._swipe_lock_timer.start()

            if g_type == Qt.NativeGestureType.ZoomNativeGesture:

                # value() is the scale factor (e.g. 1.05 for zooming in 5%)
                # Some Linux drivers send it as a delta (0.05), so we add 1.0
                # but most modern ones (libinput) send it as 1.0 + delta.
                # Heuristic: if it's very small, it's a delta.
                val = event.value()
                if abs(val) < 0.5:
                    self._zoom(1.0 + val)
                else:
                    self._zoom(val)
                return True

        if t == QEvent.Type.MouseMove:
            self._bump_cursor() # Just show cursor, don't show overlays

        if t == QEvent.Type.Resize and source is vp:
            if self._fit_mode != FitMode.CUSTOM:
                self._apply_fit()

        if t == QEvent.Type.MouseButtonPress and source is vp:
            if event.button() == Qt.MouseButton.LeftButton:
                self._mouse_press_pos = event.position()
            else:
                self._mouse_press_pos = None
            return False # Let QGraphicsView start drag

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
                return True

            # Ignore release if QScroller is actively handling a gesture
            scroller = QScroller.scroller(vp)
            if scroller.state() in (QScroller.State.Dragging, QScroller.State.Scrolling):
                self._mouse_press_pos = None
                return True

            if self._mouse_press_pos and event.button() == Qt.MouseButton.LeftButton:
                diff = event.position() - self._mouse_press_pos
                if diff.manhattanLength() < 5:
                    self._handle_click(event)
            self._mouse_press_pos = None
            return False

        if t == QEvent.Type.KeyPress:
            self.keyPressEvent(event)
            return True # Consume key

        if t == QEvent.Type.Wheel and source is vp:
            # Detect and handle touchpad phases and velocity
            now = time.time()
            phase = event.phase()
            dx = event.angleDelta().x()
            dy = event.angleDelta().y()
            px = event.pixelDelta()
            
            # Inclusive Touchpad Detection:
            # On Windows, pixelDelta is often null. We check for horizontal data (dx) 
            # or Phase data, which standard mouse wheels do not provide.
            is_tp = not px.isNull() or phase != Qt.ScrollPhase.NoScrollPhase or dx != 0

            input_logger.debug(
                f"WHEEL: phase={phase.name} dx={dx} dy={dy} pixel={px.x()},{px.y()} "
                f"is_tp={is_tp} locked={self._swipe_locked}"
            )

            # Calculate Velocity (units per second) for notched scrolling
            # Use max(abs(dx), abs(dy)) for 2D awareness
            dt = now - self._last_wheel_event_time
            velocity = max(abs(dx), abs(dy)) / dt if dt > 0 else 0
            self._last_wheel_event_time = now
            
            # 1. Ignore Momentum (Inertia) for discrete page turns
            if phase == Qt.ScrollPhase.ScrollMomentum:
                # Always block if not in continuous mode
                if self._page_layout != PageLayout.CONTINUOUS:
                    input_logger.debug(" >> BLOCKED (Momentum in Discrete Mode)")
                    return True
                # In continuous mode, block only at boundaries
                vbar = self.view.verticalScrollBar()
                if vbar.value() >= vbar.maximum() or vbar.value() <= vbar.minimum():
                    input_logger.debug(" >> BLOCKED (Momentum at Boundary)")
                    return True
            
            # 2. Reset accumulators when a fresh physical gesture begins
            if phase == Qt.ScrollPhase.ScrollBegin:
                input_logger.debug(" >> RESET (Gesture Begin)")
                self._scroll_accumulator = 0
                self._horizontal_swipe_accumulator = 0
                self._swipe_locked = False

            # 3. Ctrl+Wheel for zooming (Always High Priority)
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                input_logger.debug(f" >> ZOOM: dy={dy}")
                # Suppress swipes while zooming to avoid accidental page turns
                self._horizontal_swipe_accumulator = 0
                self._swipe_locked = True
                self._swipe_lock_timer.start()

                if dy > 0:
                    self._zoom(self.ZOOM_STEP_IN)
                elif dy < 0:
                    self._zoom(self.ZOOM_STEP_OUT)
                return True

            # 4. Handle Unlock (Notch mechanism)
            # If we are locked, we only unlock if the movement slows down significantly 
            # or the gesture officially ends.
            if self._swipe_locked:
                if velocity < self.TOUCHPAD_VELOCITY_THRESHOLD or phase == Qt.ScrollPhase.ScrollEnd:
                    input_logger.debug(f" >> UNLOCKED: vel={velocity:.1f}")
                    self._swipe_locked = False
                else:
                    return True # Still moving too fast from the first notch

            if is_tp:
                # 1. Handle Horizontal Swipes (Page Turns)
                # Ignore horizontal swipes in Continuous mode as lateral paging is 
                # logically inconsistent with the vertical strip interaction model.
                if dx != 0 and self._page_layout != PageLayout.CONTINUOUS:
                    # Hardened: Ignore tiny horizontal jitter (less than 40 units)
                    # to prevent accidental page turns during zooming or slow scrolls.
                    if abs(dx) < 40:
                        self._horizontal_swipe_accumulator = 0
                        return True
                        
                    self._horizontal_swipe_accumulator += dx
                    if abs(self._horizontal_swipe_accumulator) >= self.TOUCHPAD_SCROLL_THRESHOLD:
                        is_swipe_right = self._horizontal_swipe_accumulator > 0
                        input_logger.debug(f" >> SWIPE: direction={'RIGHT' if is_swipe_right else 'LEFT'} acc={self._horizontal_swipe_accumulator}")
                        self._horizontal_swipe_accumulator = 0
                        self._swipe_locked = True
                        self._swipe_lock_timer.start()
                        
                        # In LtR: Right-swipe is Prev, Left-swipe is Next
                        # In RtL: Right-swipe is Next, Left-swipe is Prev
                        if not self._rtl:
                            if is_swipe_right: self._prev()
                            else: self._next()
                        else:
                            if is_swipe_right: self._next()
                            else: self._prev()
                        return True
                else:
                    self._horizontal_swipe_accumulator = 0

                # 2. Handle Vertical Scrolling
                self._scroll_accumulator += dy
                
                # Continuous Vertical mode needs smooth scrolling passthrough 
                # unless we've hit a boundary where we transition books.
                if self._page_layout == PageLayout.CONTINUOUS:
                    vbar = self.view.verticalScrollBar()
                    at_boundary = (dy < 0 and vbar.value() >= vbar.maximum()) or \
                                  (dy > 0 and vbar.value() <= vbar.minimum())
                    
                    if at_boundary:
                        # Use threshold to slow down book transitions
                        if abs(self._scroll_accumulator) >= self.TOUCHPAD_SCROLL_THRESHOLD:
                            input_logger.debug(f" >> BOUNDARY TRANSITION: acc={self._scroll_accumulator}")
                            self._scroll_accumulator = 0
                            self._swipe_locked = True
                            self._swipe_lock_timer.start()
                            # Book transition counts as 120 units
                            step_dy = 120 if dy > 0 else -120
                            return self._smart_scroll(step_dy)
                        else:
                            return True # Swallow events until threshold met
                    else:
                        self._scroll_accumulator = 0 # Moving smoothly, clear threshold
                        # Pass through original 'dy' at full strength for smooth panning
                        return self._smart_scroll(dy)

                # Discrete page modes: accumulate until threshold reached
                if abs(self._scroll_accumulator) >= self.TOUCHPAD_SCROLL_THRESHOLD:
                    input_logger.debug(f" >> PAGE TURN: dy={dy} acc={self._scroll_accumulator}")
                    self._scroll_accumulator = 0
                    self._swipe_locked = True
                    self._swipe_lock_timer.start()
                    # A notch is reached: trigger one smart scroll step
                    step_dy = 120 if dy > 0 else -120
                    return self._smart_scroll(step_dy)
                else:
                    return True # Swallow intermediate high-res events
            else:
                # 3. Handle Standard Mouse Wheel (Discrete clicks)
                # Hardened: Ignore tiny values (like -1 or -8) often sent by 
                # touchpads emulating mouse wheels, which cause runaway paging.
                if abs(dy) < 60:
                    input_logger.debug(f" >> FILTERED (Noise): dy={dy}")
                    return True
                    
                input_logger.debug(f" >> MOUSE WHEEL: dy={dy}")
                self._scroll_accumulator = 0 # Discrete mouse wheel reset
                self._horizontal_swipe_accumulator = 0
                return self._smart_scroll(dy)

        return super().eventFilter(source, event)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            self._update_settings_menu()
        super().changeEvent(event)

    def _smart_scroll(self, dy: int) -> bool:
        """Shared logic for mouse wheel and Space/Shift+Space 'smart' navigation."""
        if dy == 0: return False
        
        vbar = self.view.verticalScrollBar()
        hbar = self.view.horizontalScrollBar()
        vp_h = self.view.viewport().height()
        vp_w = self.view.viewport().width()

        # 1. Typewriter flow (Fit Width/Height, Not Continuous)
        if self._fit_mode in (FitMode.FIT_WIDTH, FitMode.FIT_HEIGHT, FitMode.ORIGINAL, FitMode.CUSTOM) and self._page_layout != PageLayout.CONTINUOUS:
            scroll_amount_h = int(vp_w * self.SMART_PAN_STEP_H_PCT)
            v_jump = int(vp_h * self.SMART_PAN_STEP_V_PCT) # Overlap percentage
            
            if dy < 0: # Scroll "Down" / Forward
                # 1a. Try Horizontal panning first (if it has range)
                if hbar.maximum() > 0:
                    if not self._rtl: # LtR
                        if hbar.value() < hbar.maximum():
                            hbar.setValue(hbar.value() + scroll_amount_h)
                            return True
                    else: # RtL
                        if hbar.value() > hbar.minimum():
                            hbar.setValue(hbar.value() - scroll_amount_h)
                            return True

                # 1b. Try Vertical panning next
                if vbar.maximum() > 0:
                    if vbar.value() < vbar.maximum():
                        vbar.setValue(min(vbar.maximum(), vbar.value() + v_jump))
                        # Reset horizontal to start of line
                        hbar.setValue(hbar.maximum() if self._rtl else hbar.minimum())
                        return True
                
                # 1c. If at bottom-right (or bottom-left for RtL), Next Page
                self._next()
                return True

            elif dy > 0: # Scroll "Up" / Backward
                # 1a. Try Horizontal panning first (if it has range)
                if hbar.maximum() > 0:
                    if not self._rtl: # LtR
                        if hbar.value() > hbar.minimum():
                            hbar.setValue(hbar.value() - scroll_amount_h)
                            return True
                    else: # RtL
                        if hbar.value() < hbar.maximum():
                            hbar.setValue(hbar.value() + scroll_amount_h)
                            return True

                # 1b. Try Vertical panning next
                if vbar.maximum() > 0:
                    if vbar.value() > vbar.minimum():
                        vbar.setValue(max(vbar.minimum(), vbar.value() - v_jump))
                        # Reset horizontal to end of line
                        hbar.setValue(hbar.minimum() if self._rtl else hbar.maximum())
                        return True
                
                # 1c. If at top-left (or top-right for RtL), Prev Page
                self._prev()
                return True
            
            return False

        # 2. Continuous Mode: pass through for native scrolling, but handle boundaries
        if self._page_layout == PageLayout.CONTINUOUS:
            if dy < 0 and vbar.value() >= vbar.maximum():
                self._next()
                return True
            elif dy > 0 and vbar.value() <= vbar.minimum():
                self._prev()
                return True
            return False

        # 3. Default (Fit Page): Simple next/prev page
        if dy < 0:
            self._next()
        else:
            self._prev()
        return True

    def _on_click_timer_timeout(self):
        if self._pending_click_pos:
            pos = self._pending_click_pos
            self._pending_click_pos = None
            self._execute_click(pos)

    def _unlock_swipe(self):
        self._swipe_locked = False

    def _handle_click(self, event):
        self._bump_cursor() # Restore cursor on any click
        w = self.view.viewport().width()
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

    def _prev(self):
        input_logger.debug(" >> EXECUTE: _prev()")
        logger.debug(f"Reader _prev called. index={self._index}, total={self._total}")
        if self._index > 0:
            step = 2 if self._effective_layout() == PageLayout.DOUBLE else 1
            self._go_to(self._index - step, is_back=True)
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
            BackgroundMode.MEAN: "quality_smooth",
            BackgroundMode.MEDIAN: "quality_smooth",
            BackgroundMode.MODE: "quality_smooth",
            BackgroundMode.MODE_MEAN: "quality_smooth",
            BackgroundMode.VIBRANT: "quality_smooth",
            BackgroundMode.CONTRAST: "quality_smooth",
            BackgroundMode.SMOOTH: "quality_smooth",
            BackgroundMode.GRADIENT: "quality_smooth",
            BackgroundMode.CLEAN: "quality_smooth"
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

        self.settings_menu.addSeparator()
        
        # 6. Interface
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

    def _zoom(self, factor: float):
        # We need something to zoom
        if self._page_layout == PageLayout.CONTINUOUS:
            if not self._continuous_items: return
        else:
            if self.pixmap_item.pixmap().isNull(): return
            
        self._bump_activity(ensure_overlays=False) # Show zoom level label
        
        if self._fit_mode != FitMode.CUSTOM:
            self._fit_mode = FitMode.CUSTOM
            self._update_settings_menu()
            if self._page_layout == PageLayout.CONTINUOUS:
                self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
                self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            else:
                self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
                self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.view.scale(factor, factor)
        
        # Calculate minimum scale
        vp = self.view.viewport()

        # Use first available page as a reference for min_scale
        if self._page_layout == PageLayout.CONTINUOUS:
            min_scale_w = vp.width() / max(1, self._continuous_strip_width)
            # Allow zooming out to see ~2.5 pages
            target_h = self._continuous_strip_width * 1.5 * 2.5
            min_scale_h = vp.height() / max(1, target_h)
            min_scale = min(min_scale_w, min_scale_h)
        else:
            sample_item = self.pixmap_item
            min_scale_w = vp.width() / max(1, sample_item.base_width)
            min_scale_h = vp.height() / max(1, sample_item.base_height)
            min_scale = min(min_scale_w, min_scale_h)

        # Current scale
        current_scale = self.view.transform().m11()

        if self._page_layout == PageLayout.CONTINUOUS:
            cont_logger.debug(f"Continuous Zoom: factor={factor:.2f}, current_scale={current_scale:.3f}, min_scale={min_scale:.3f}")

        if current_scale < min_scale:
            self._set_fit_mode(FitMode.FIT_PAGE)
        else:
            self._update_mipmap_levels()

    def _cycle_zoom(self):
        if self.pixmap_item.pixmap().isNull():
            return

        self._bump_activity(ensure_overlays=False) # Show zoom level label
        
        # 4 Levels (Multipliers of Fit Page scale)
        levels = [1.0, 1.5, 2.5, 4.0]
        self._zoom_cycle_idx = (self._zoom_cycle_idx + 1) % len(levels)
        target_multiplier = levels[self._zoom_cycle_idx]

        if self._zoom_cycle_idx == 0:
            self._set_fit_mode(FitMode.FIT_PAGE)
        else:
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
            if self._page_layout == PageLayout.CONTINUOUS:
                self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
                self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            else:
                self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
                self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self._update_mipmap_levels()

    def _cycle_fit(self):
        try:
            i = _FIT_CYCLE.index(self._fit_mode)
            next_mode = _FIT_CYCLE[(i + 1) % len(_FIT_CYCLE)]
        except ValueError:
            # If current mode is CUSTOM or otherwise not in cycle, go to first mode
            next_mode = _FIT_CYCLE[0]
        self._set_fit_mode(next_mode)

    def _apply_fit(self):
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
            if not self.pixmap_item.pixmap().isNull():
                self.pixmap_item.setTransformationMode(t_mode)
                
            # Apply to all continuous pages
            for it in self._continuous_items.values():
                it.setTransformationMode(t_mode)
                
            self.view.viewport().update()

            if self._page_layout == PageLayout.CONTINUOUS:
                self.view.setHorizontalScrollBarPolicy(off)
                self.view.setVerticalScrollBarPolicy(off)
                self.view.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

                if not self._continuous_items:
                    return

                if self._fit_mode == FitMode.CUSTOM:
                    self._update_mipmap_levels()
                    return

                self.view.resetTransform()
                if self._continuous_strip_width > 0:
                    if self._fit_mode == FitMode.FIT_PAGE:
                        # In continuous mode, "Fit Page" acts as a zoomed-out mode.
                        # We target showing approximately 1.0 page's worth of height.
                        # Assuming an average aspect ratio of 1.5 (height/width)
                        target_h = self._continuous_strip_width * 1.5 * 1.0
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

                self._update_mipmap_levels()
                return

            if self.pixmap_item.pixmap().isNull():
                return
            pm_item  = self.pixmap_item

            if self._fit_mode == FitMode.FIT_PAGE:
                self.view.setHorizontalScrollBarPolicy(off)
                self.view.setVerticalScrollBarPolicy(off)
                self.view.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

            elif self._fit_mode == FitMode.FIT_WIDTH:
                self.view.setHorizontalScrollBarPolicy(off)
                self.view.setVerticalScrollBarPolicy(on)
                if pm_item.base_width > 0:
                    self.view.resetTransform()
                    self.view.scale(vp.width() / pm_item.base_width, vp.width() / pm_item.base_width)

            elif self._fit_mode == FitMode.FIT_HEIGHT:
                self.view.setHorizontalScrollBarPolicy(on)
                self.view.setVerticalScrollBarPolicy(off)
                if pm_item.base_height > 0:
                    self.view.resetTransform()
                    self.view.scale(vp.height() / pm_item.base_height, vp.height() / pm_item.base_height)

            elif self._fit_mode == FitMode.ORIGINAL:
                self.view.setHorizontalScrollBarPolicy(on)
                self.view.setVerticalScrollBarPolicy(on)
                self.view.resetTransform()

            elif self._fit_mode == FitMode.CUSTOM:
                self.view.setHorizontalScrollBarPolicy(on)
                self.view.setVerticalScrollBarPolicy(on)

            self._update_mipmap_levels()
        finally:
            self.view.setTransformationAnchor(old_anchor)

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
        
        # Clear continuous items if any exist
        if hasattr(self, '_continuous_items') and self._continuous_items:
            for item in self._continuous_items.values():
                try:
                    self.scene.removeItem(item)
                except Exception:
                    pass
            self._continuous_items.clear()
            if hasattr(self, '_continuous_y_offsets'):
                self._continuous_y_offsets.clear()
            if hasattr(self, '_continuous_loading'):
                self._continuous_loading.clear()
                
        self.title_label.setText("")
        self.counter_label.setText("0 / 0")
        self.thumb_slider.clear()
        self.thumb_slider.slider.setRange(0, 0)
        self.thumb_slider.slider.setValue(0)

    def _setup_reader(self, title: str, total: int, subtitle: str = None, start_index: int = 0):
        """Call once the page list / reading order is known."""
        self._total = total
        self._index = max(0, min(start_index, total - 1))
        
        s = UIConstants.scale
        display_text = f'<span style="font-size: {s(19)}px;">{title}</span>'
        if subtitle and subtitle.strip():
            display_text += f'<br/><i style="font-size: {s(15)}px; color: #bbb; font-weight: normal;">{subtitle.strip()}</i>'
            
        self.title_label.setText(display_text)
        self.thumb_slider.slider.setRange(0, max(0, total - 1))
        self.thumb_slider.slider.setValue(self._index)
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
                for item in self._continuous_items.values():
                    self.scene.removeItem(item)
                self._continuous_items.clear()
                self._continuous_y_offsets.clear()
                asyncio.create_task(self._load_continuous_page_initial(idx))
            else:
                # Scroll to it
                item = self._continuous_items[idx]
                self.view.ensureVisible(item, 0, 0)

            return
        
        # 3. Handle Paginated Layouts (Single/Double)
        # Non-continuous mode: clean up continuous items if they exist
        if self._continuous_items:
            for item in self._continuous_items.values():
                self.scene.removeItem(item)
            self._continuous_items.clear()
        
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
            self._continuous_session_id += 1
            session_id = self._continuous_session_id
            
            # Clear everything again inside the lock to ensure consistency
            for item in self._continuous_items.values():
                try: self.scene.removeItem(item)
                except: pass
            self._continuous_items.clear()
            self._continuous_y_offsets.clear()
            self._continuous_loading.clear()
            
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
            self.scene.addItem(item)
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

            item.setPos(0, target_y)
            self.scene.addItem(item)
            self._continuous_items[idx] = item
            self._continuous_y_offsets[idx] = target_y
            
            # Re-sync overall scene boundaries from all loaded items to prevent drift
            all_ys = []
            for it in self._continuous_items.values():
                all_ys.append(it.pos().y())
                all_ys.append(it.pos().y() + (it.base_height * it._base_scale))
            
            self._continuous_min_y = min(all_ys)
            self._continuous_max_y = max(all_ys)
            self.scene.setSceneRect(0, self._continuous_min_y, self._continuous_strip_width, self._continuous_max_y - self._continuous_min_y)
            
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

            item.setPos(0, target_y)
            self.scene.addItem(item)
            self._continuous_items[idx] = item
            self._continuous_y_offsets[idx] = target_y
            
            # Re-sync overall boundaries
            all_ys = []
            for it in self._continuous_items.values():
                all_ys.append(it.pos().y())
                all_ys.append(it.pos().y() + (it.base_height * it._base_scale))
            
            self._continuous_min_y = min(all_ys)
            self._continuous_max_y = max(all_ys)
            self.scene.setSceneRect(0, self._continuous_min_y, self._continuous_strip_width, self._continuous_max_y - self._continuous_min_y)
            
            cont_logger.debug(f"Continuous PREPEND: Added {idx} at Y={target_y:.1f}, SceneRect={self.scene.sceneRect()}")
        finally:
            self._continuous_loading.discard(idx)

    def _on_vscroll_changed(self, value):
        if self._is_closing or self._page_layout != PageLayout.CONTINUOUS or not self._continuous_items:
            return
            
        vp = self.view.viewport()
        vbar = self.view.verticalScrollBar()
        if vbar.maximum() <= 0 and self._total > 1:
            return

        scene_top = self.view.mapToScene(0, 0).y()
        scene_bottom = self.view.mapToScene(0, vp.height()).y()
        scene_center = self.view.mapToScene(0, vp.height() // 2).y()
        
        visible_idx = self._index
        min_visible = float('inf')
        max_visible = float('-inf')
        
        # Track items in viewport AND physical loaded bounds
        loaded_min_y = float('inf')
        loaded_max_y = float('-inf')

        for idx, item in self._continuous_items.items():
            try:
                item_y = item.pos().y()
                item_h = item.base_height * item._base_scale
                
                loaded_min_y = min(loaded_min_y, item_y)
                loaded_max_y = max(loaded_max_y, item_y + item_h)

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
            
            # 1. UNLOAD pages physically far away (more than 4 viewports distance)
            unload_threshold = vp.height() * 4.0
            keep_range = range(min_visible - 6, max_visible + 7)
            
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
        except RuntimeError:
            pass
            
        try:
            # Physical Virtualization: check pixel distance to loaded edges
            dist_to_top = scene_top - self._continuous_min_y
            dist_to_bottom = self._continuous_max_y - scene_bottom
            
            # Unload pages far away (more than 3 viewports away)
            keep_range = range(min_visible - 4, max_visible + 5)
            keys_to_remove = [k for k in self._continuous_items.keys() if k not in keep_range]
            # Safety: don't unload if we are physically near that page
            keys_to_remove = [k for k in keys_to_remove if (k < min_visible and dist_to_top > 2000) or (k > max_visible and dist_to_bottom > 2000)]
            
            for k in keys_to_remove:
                cont_logger.debug(f"Continuous Virtualization: Unloading offscreen index {k}")
                item = self._continuous_items.pop(k)
                self.scene.removeItem(item)
                
            # Load more if we are within 1.5 viewports of a boundary
            load_threshold = vp.height() * 1.5
            
            max_loaded = max(self._continuous_items.keys(), default=visible_idx)
            if max_loaded < self._total - 1 and (dist_to_bottom < load_threshold):
                next_idx = max_loaded + 1
                if next_idx not in self._continuous_loading:
                    self._continuous_loading.add(next_idx)
                    cont_logger.debug(f"Continuous Virtualization: dist_to_bottom={dist_to_bottom:.1f}, loading APPEND {next_idx}")
                    asyncio.create_task(self._load_continuous_page_append(next_idx, self._continuous_session_id))
                
            min_loaded = min(self._continuous_items.keys(), default=visible_idx)
            if min_loaded > 0 and (dist_to_top < load_threshold):
                prev_idx = min_loaded - 1
                if prev_idx not in self._continuous_loading:
                    self._continuous_loading.add(prev_idx)
                    cont_logger.debug(f"Continuous Virtualization: dist_to_top={dist_to_top:.1f}, loading PREPEND {prev_idx}")
                    asyncio.create_task(self._load_continuous_page_prepend(prev_idx, self._continuous_session_id))
        except RuntimeError:
            pass
