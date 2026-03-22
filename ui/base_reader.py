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

from PyQt6.QtCore import Qt, QEvent, QPoint, QTimer, QSize
from PyQt6.QtGui import QKeyEvent, QPainter, QPixmap, QAction, QActionGroup, QColor
from PyQt6.QtWidgets import (
    QFrame, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView,
    QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget, QMenu,
    QGraphicsDropShadowEffect, QScrollArea
)

from logger import get_logger
from api.image_manager import ImageManager
from ui.theme_manager import ThemeManager, UIConstants, THEMES
from ui.components.mini_detail_popover import MiniDetailPopover

logger = get_logger("ui.base_reader")


# ---------------------------------------------------------------------------
# Fit mode
# ---------------------------------------------------------------------------

class FitMode(enum.Enum):
    FIT_PAGE   = "fit_page"
    FIT_WIDTH  = "fit_width"
    FIT_HEIGHT = "fit_height"
    ORIGINAL   = "original"


_FIT_LABELS = {
    FitMode.FIT_PAGE:   "Fit to Window",
    FitMode.FIT_WIDTH:  "Full Width",
    FitMode.FIT_HEIGHT: "Full Height",
    FitMode.ORIGINAL:   "Original Size",
}
_FIT_CYCLE = [FitMode.FIT_PAGE, FitMode.FIT_WIDTH, FitMode.FIT_HEIGHT, FitMode.ORIGINAL]


# ---------------------------------------------------------------------------
# Page layout
# ---------------------------------------------------------------------------

class PageLayout(enum.Enum):
    SINGLE = "single"
    DOUBLE = "double"
    AUTO   = "auto"


_LAYOUT_LABELS = {
    PageLayout.SINGLE: "Single Page",
    PageLayout.DOUBLE: "Two-Page Spread",
    PageLayout.AUTO:   "Automatic Layout",
}
_LAYOUT_CYCLE = [PageLayout.SINGLE, PageLayout.DOUBLE, PageLayout.AUTO]


def _compose_spread(pm1: QPixmap, pm2: QPixmap) -> QPixmap:
    """Composite two pages side-by-side, centred vertically, on a black canvas."""
    total_w = pm1.width() + pm2.width()
    max_h   = max(pm1.height(), pm2.height())
    result  = QPixmap(total_w, max_h)
    result.fill(Qt.GlobalColor.black)
    painter = QPainter(result)
    painter.drawPixmap(0,           (max_h - pm1.height()) // 2, pm1)
    painter.drawPixmap(pm1.width(), (max_h - pm2.height()) // 2, pm2)
    painter.end()
    return result


# ---------------------------------------------------------------------------
# Adjacent Book Popover
# ---------------------------------------------------------------------------

class AdjacentBookPopover(QFrame):
    """
    A popover that appears when reaching the start/end of a book,
    suggesting the next or previous book in the current context.
    Pinned to "light" theme by default.
    """
    def __init__(self, parent=None, on_clicked: Callable[[], None] = None, theme_name="light"):
        super().__init__(parent)
        self.on_clicked = on_clicked
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        s = UIConstants.scale
        self.setFixedWidth(s(300))
        self.setFixedHeight(s(400))
        
        theme = THEMES.get(theme_name, THEMES["light"])
        
        # Main container
        self.container = QFrame(self)
        self.container.setObjectName("adjacent_container")
        self.container.setCursor(Qt.CursorShape.PointingHandCursor)
        self.container.setStyleSheet(f"""
            QFrame#adjacent_container {{
                background-color: {theme['bg_header']};
                border: {max(1, s(2))}px solid {theme['accent']};
                border-radius: {s(15)}px;
            }}
            QLabel {{ color: {theme['text_main']}; background: transparent; }}
            QLabel#header_label {{ font-weight: bold; font-size: {s(14)}px; color: {theme['accent']}; }}
            QLabel#title_label {{ font-weight: bold; font-size: {s(15)}px; color: {theme['text_main']}; }}
        """)
        
        # Shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(s(20))
        shadow.setColor(QColor(0, 0, 0, 100))
        self.container.setGraphicsEffect(shadow)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(s(10), s(10), s(10), s(10))
        layout.addWidget(self.container)
        
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
        self.cover_label.setStyleSheet(f"border: {max(1, s(1))}px solid {theme['border']}; border-radius: {s(4)}px;")
        self.inner_layout.addWidget(self.cover_label, 0, Qt.AlignmentFlag.AlignCenter)
        
        # Title
        self.title_label = QLabel("")
        self.title_label.setObjectName("title_label")
        self.title_label.setWordWrap(True)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.inner_layout.addWidget(self.title_label)
        
    def populate(self, direction: int, title: str, cover: QPixmap):
        self.direction = direction
        if direction > 0:
            self.hdr_label.setText("Next Comic 👉")
        else:
            self.hdr_label.setText("👈 Previous Comic")
            
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
        
        # Proper direction key triggers transition
        if key == Qt.Key.Key_Right and self.direction > 0:
            if self.on_clicked:
                self.on_clicked()
        elif key == Qt.Key.Key_Left and self.direction < 0:
            if self.on_clicked:
                self.on_clicked()
        
        # ANY key (proper or otherwise) closes the popover
        self.hide()
        # If it was NOT the proper key, we don't want to pass it through 
        # to the reader (preventing accidental page turns or exits)
        event.accept()

    def show_at(self, pos: QPoint):
        self.move(pos)
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
            if t in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress):
                self._show_at(event.position().x())
            elif t in (QEvent.Type.Leave, QEvent.Type.MouseButtonRelease):
                self._popup.setVisible(False)
        return super().eventFilter(source, event)

    def _page_at(self, x: float) -> int:
        mx = self.slider.maximum()
        if mx <= 0:
            return 0
        ratio = max(0.0, min(1.0, x / max(1, self.slider.width())))
        return round(ratio * mx)

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

    def __init__(
        self, 
        on_exit, 
        image_manager: ImageManager = None, 
        on_title_clicked: Callable[[], None] = None,
        on_get_adjacent: Callable[[int], Any] = None,
        on_transition: Callable[[Any], None] = None
    ):
        super().__init__()
        self.on_exit = on_exit
        self.on_title_clicked = on_title_clicked
        self.on_get_adjacent = on_get_adjacent
        self.on_transition = on_transition

        self._index   = 0
        self._total   = 0
        self._fit_mode    = FitMode.FIT_PAGE
        self._page_layout = PageLayout.SINGLE
        self._rtl         = False
        self._overlays_visible = True
        self._overlays_locked  = False
        self._slider_dragging  = False
        self._thumb_visible    = True

        self.setStyleSheet("background-color: black; color: white;")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Meta Popover
        self.meta_popover = MiniDetailPopover(self)
        
        # Adjacent Popover
        self.adjacent_popover = AdjacentBookPopover(self, on_clicked=self._on_adjacent_clicked)
        self._current_adjacent_ref = None


        # --- Graphics view (fills the whole widget) ---
        self.scene = QGraphicsScene()
        self.view  = QGraphicsView(self.scene)
        self.view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.view.setStyleSheet("border: none; background-color: black;")
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setMouseTracking(True)
        self.view.viewport().setMouseTracking(True)
        self.view.viewport().setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.view)

        # --- Header overlay ---
        self.header = QFrame(self)
        s = UIConstants.scale
        self.header.setFixedHeight(s(60))
        self.header.setStyleSheet(
            "background-color: rgba(0,0,0,160); border: none;"
        )
        hdr = QHBoxLayout(self.header)
        hdr.setContentsMargins(s(10), s(5), s(10), s(5))
        hdr.setSpacing(s(15))

        self.btn_back = QPushButton()
        self.btn_back.setIcon(ThemeManager.get_icon("back", "white"))
        s = UIConstants.scale
        self.btn_back.setFixedSize(s(36), s(36))
        self.btn_back.setIconSize(QSize(s(20), s(20)))
        self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back.setToolTip("Exit Reader")
        self.btn_back.clicked.connect(self._do_exit)

        self.title_label = QLabel("")
        self.title_label.setStyleSheet("color: white; font-weight: bold;")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setTextFormat(Qt.TextFormat.RichText)
        self.title_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.title_label.mousePressEvent = lambda e: self._on_title_pressed(e)

        self.btn_settings = QPushButton()
        self.btn_settings.setIcon(ThemeManager.get_icon("settings", "white"))
        s = UIConstants.scale
        self.btn_settings.setFixedSize(s(36), s(36))
        self.btn_settings.setIconSize(QSize(s(22), s(22)))
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.setToolTip("Reader Settings")
        self.settings_menu = QMenu(self)
        self.btn_settings.setMenu(self.settings_menu)
        self._update_settings_menu()

        self.btn_fullscreen = QPushButton()
        self.btn_fullscreen.setIcon(ThemeManager.get_icon("fullscreen", "white"))
        self.btn_fullscreen.setFixedSize(s(36), s(36))
        self.btn_fullscreen.setIconSize(QSize(s(20), s(20)))
        self.btn_fullscreen.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fullscreen.setToolTip("Toggle fullscreen  [F11]")
        self.btn_fullscreen.clicked.connect(self._toggle_fullscreen)

        hdr.addWidget(self.btn_back)
        hdr.addWidget(self.title_label, 1)
        hdr.addWidget(self.btn_settings)
        hdr.addWidget(self.btn_fullscreen)

        self.counter_label = QLabel("0 / 0")
        s = UIConstants.scale
        self.counter_label.setStyleSheet(f"color: #aaa; font-size: {s(16)}px; font-weight: bold;")
        self.counter_label.setFixedWidth(s(95))
        self.counter_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
        )

        # --- Footer overlay ---
        self.footer = QFrame(self)
        self.footer.setStyleSheet(
            "background-color: rgba(0,0,0,160); border: none;"
        )
        ftr = QVBoxLayout(self.footer)
        s = UIConstants.scale
        ftr.setContentsMargins(s(10), s(6), s(10), s(8))
        ftr.setSpacing(s(5))

        slider_row = QHBoxLayout()
        slider_row.setSpacing(s(10))
        
        self.thumb_slider = ThumbnailSlider(self)
        self.thumb_slider.slider.sliderPressed.connect(self._on_slider_pressed)
        self.thumb_slider.slider.sliderReleased.connect(self._on_slider_released)
        self.thumb_slider.slider.valueChanged.connect(self._on_slider_value_changed)
        
        slider_row.addWidget(self.counter_label)
        slider_row.addWidget(self.thumb_slider)
        ftr.addLayout(slider_row)

        _btn_css = (
            "QPushButton { background:#333; color:white; border-radius:4px;"
            " padding:4px; }"
            "QPushButton:hover { background:#555; }"
            "QPushButton:disabled { color:#555; }"
        )

        for b in (self.btn_back, self.btn_fullscreen, self.btn_settings):
            b.setStyleSheet(_btn_css)

        # --- Timers ---
        self._overlay_timer = QTimer(self)
        self._overlay_timer.setSingleShot(True)
        self._overlay_timer.setInterval(self.OVERLAY_HIDE_MS)
        self._overlay_timer.timeout.connect(self._hide_overlays)

        self._cursor_timer = QTimer(self)
        self._cursor_timer.setSingleShot(True)
        self._cursor_timer.setInterval(self.CURSOR_HIDE_MS)
        self._cursor_timer.timeout.connect(lambda: self.setCursor(Qt.CursorShape.BlankCursor))

        self.view.viewport().installEventFilter(self)
        self.view.installEventFilter(self)

        self._bump_activity()

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
            if direction > 0:
                # Next: Right side
                x = self.width() - self.adjacent_popover.width() - s(40)
            else:
                # Prev: Left side
                x = s(40)
                
            y = (self.height() - self.adjacent_popover.height()) // 2
            self.adjacent_popover.show_at(self.mapToGlobal(QPoint(x, y)))
            
        except Exception as e:
            logger.error(f"Error getting adjacent book: {e}")

    # ------------------------------------------------------------------ #
    # Activity / overlay visibility                                        #
    # ------------------------------------------------------------------ #

    def _bump_cursor(self):
        if self.cursor().shape() == Qt.CursorShape.BlankCursor:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self._cursor_timer.start()

    def _bump_activity(self):
        self._bump_cursor()
        if not self._overlays_visible:
            self._show_overlays()
        
        if not self._overlays_locked:
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

    def _toggle_overlays_locked(self):
        self._overlays_locked = not self._overlays_locked
        self._update_settings_menu()
        if self._overlays_locked:
            self._bump_activity() # Ensure they are shown
        else:
            self._overlay_timer.start() # Schedule hide

    def _hide_overlays(self):
        if self._slider_dragging:
            # Don't hide while dragging, restart timer if not locked
            if not self._overlays_locked:
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

        if t == QEvent.Type.MouseMove:
            self._bump_cursor() # Just show cursor, don't show overlays

        if t == QEvent.Type.Resize and source is vp:
            self._apply_fit()

        if t == QEvent.Type.MouseButtonPress and source is vp:
            self._handle_click(event)
            return True # Consume click

        if t == QEvent.Type.KeyPress:
            self.keyPressEvent(event)
            return True # Consume key

        if t == QEvent.Type.Wheel and source is vp:
            # Pass through to view's scrollbar in scrollable fit modes
            if self._fit_mode in (FitMode.FIT_WIDTH, FitMode.FIT_HEIGHT, FitMode.ORIGINAL):
                return False
            if event.angleDelta().y() < 0:
                self._next()
            else:
                self._prev()
            return True

        return super().eventFilter(source, event)

    def _handle_click(self, event):
        self._bump_cursor() # Restore cursor on any click
        w = self.view.viewport().width()
        x = event.position().x()
        
        is_left = x < w / 3
        is_right = x > w * 2 / 3
        
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
                self._bump_activity()

    def keyPressEvent(self, event: QKeyEvent):
        self._bump_cursor()
        key = event.key()

        # Flip horizontal arrow keys for RtL
        if self._rtl:
            if   key == Qt.Key.Key_Right: key = Qt.Key.Key_Left
            elif key == Qt.Key.Key_Left:  key = Qt.Key.Key_Right

        if key in (Qt.Key.Key_Right, Qt.Key.Key_PageDown):
            self._next()
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_PageUp):
            self._prev()
        elif key == Qt.Key.Key_Space:
            # Space toggles overlays
            if self._overlays_visible:
                self._hide_overlays()
                self._overlay_timer.stop()
            else:
                self._bump_activity() # This will show overlays
        elif key == Qt.Key.Key_F11:
            self._toggle_fullscreen()
        elif key == Qt.Key.Key_Escape:
            if self.window().isFullScreen():
                self._toggle_fullscreen()
            else:
                self._do_exit()
        elif key == Qt.Key.Key_F:
            self._cycle_fit()
        elif key == Qt.Key.Key_R:
            self._toggle_dir()
        elif key == Qt.Key.Key_L:
            self._cycle_layout()
        elif key == Qt.Key.Key_Home:
            self._go_to(0)
        elif key == Qt.Key.Key_End:
            self._go_to(self._total - 1)
        super().keyPressEvent(event)

    # ------------------------------------------------------------------ #
    # Fullscreen / exit                                                    #
    # ------------------------------------------------------------------ #

    def _do_exit(self):
        if self.window().isFullScreen():
            self.window().showNormal()
        self.on_exit()

    def _toggle_fullscreen(self):
        win = self.window()
        if win.isFullScreen():
            win.showNormal()
            self.btn_fullscreen.setIcon(ThemeManager.get_icon("fullscreen", "white"))
            self.btn_fullscreen.setToolTip("Exit fullscreen  [F11]")
        else:
            win.showFullScreen()
            self.btn_fullscreen.setIcon(ThemeManager.get_icon("minimize", "white"))
            self.btn_fullscreen.setToolTip("Exit fullscreen  [F11]")

    # ------------------------------------------------------------------ #
    # Navigation                                                           #
    # ------------------------------------------------------------------ #

    def _prev(self):
        logger.debug(f"Reader _prev called. index={self._index}, total={self._total}")
        if self._index > 0:
            step = 2 if self._effective_layout() == PageLayout.DOUBLE else 1
            self._go_to(self._index - step)
        else:
            logger.debug("Reader: at first page, triggering prev boundary check")
            asyncio.create_task(self._handle_boundary(-1))

    def _next(self):
        logger.debug(f"Reader _next called. index={self._index}, total={self._total}")
        if self._index < self._total - 1:
            step = 2 if self._effective_layout() == PageLayout.DOUBLE else 1
            self._go_to(self._index + step)
        else:
            logger.debug("Reader: at last page, triggering next boundary check")
            asyncio.create_task(self._handle_boundary(1))

    def _go_to(self, idx: int):
        idx = max(0, min(idx, self._total - 1))
        self._index = idx
        self.adjacent_popover.hide()
        asyncio.create_task(self._show_page())

    def _on_slider_pressed(self):
        self._slider_dragging = True

    def _on_slider_released(self):
        self._slider_dragging = False
        self._go_to(self.thumb_slider.slider.value())

    def _on_slider_value_changed(self, value: int):
        # While dragging: update counter only, no page load
        if self._slider_dragging:
            self.counter_label.setText(f"{value + 1} / {self._total}")

    # ------------------------------------------------------------------ #
    # Settings Menu                                                        #
    # ------------------------------------------------------------------ #

    def _update_settings_menu(self):
        if not hasattr(self, 'settings_menu'): return
        self.settings_menu.clear()
        
        # 1. Scaling
        header_scaling = self.settings_menu.addAction("IMAGE SCALING")
        header_scaling.setEnabled(False)
        
        fit_group = QActionGroup(self)
        for mode in _FIT_CYCLE:
            label = _FIT_LABELS[mode]
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(self._fit_mode == mode)
            action.triggered.connect(lambda _, m=mode: self._set_fit_mode(m))
            fit_group.addAction(action)
            self.settings_menu.addAction(action)
            
        self.settings_menu.addSeparator()
        
        # 2. Page Layout
        header_view = self.settings_menu.addAction("DISPLAY MODE")
        header_view.setEnabled(False)
        
        layout_group = QActionGroup(self)
        for layout in _LAYOUT_CYCLE:
            label = _LAYOUT_LABELS[layout]
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(self._page_layout == layout)
            action.triggered.connect(lambda _, l=layout: self._set_page_layout(l))
            layout_group.addAction(action)
            self.settings_menu.addAction(action)
            
        self.settings_menu.addSeparator()
        
        # 3. Reading Direction
        header_dir = self.settings_menu.addAction("READING ORDER")
        header_dir.setEnabled(False)
        
        dir_group = QActionGroup(self)
        
        ltr_action = QAction("Left to Right (LtR)", self)
        ltr_action.setCheckable(True)
        ltr_action.setChecked(not self._rtl)
        ltr_action.triggered.connect(lambda: self._set_reading_direction(False))
        dir_group.addAction(ltr_action)
        self.settings_menu.addAction(ltr_action)
        
        rtl_action = QAction("Right to Left (RtL)", self)
        rtl_action.setCheckable(True)
        rtl_action.setChecked(self._rtl)
        rtl_action.triggered.connect(lambda: self._set_reading_direction(True))
        dir_group.addAction(rtl_action)
        self.settings_menu.addAction(rtl_action)
        
        self.settings_menu.addSeparator()
        
        # 4. Interface / Previews
        header_ui = self.settings_menu.addAction("INTERFACE")
        header_ui.setEnabled(False)
        
        thumb_action = QAction("Show Navigation Previews", self)
        thumb_action.setCheckable(True)
        thumb_action.setChecked(self._thumb_visible)
        thumb_action.triggered.connect(lambda: self._set_thumbnails_visible(not self._thumb_visible))
        self.settings_menu.addAction(thumb_action)
        
        lock_action = QAction("Keep Controls Visible", self)
        lock_action.setCheckable(True)
        lock_action.setChecked(self._overlays_locked)
        lock_action.triggered.connect(self._toggle_overlays_locked)
        self.settings_menu.addAction(lock_action)

    # ------------------------------------------------------------------ #
    # Fit mode                                                             #
    # ------------------------------------------------------------------ #

    def _set_fit_mode(self, mode: FitMode):
        self._fit_mode = mode
        self._update_settings_menu()
        self._apply_fit()

    def _cycle_fit(self):
        i = _FIT_CYCLE.index(self._fit_mode)
        next_mode = _FIT_CYCLE[(i + 1) % len(_FIT_CYCLE)]
        self._set_fit_mode(next_mode)

    def _apply_fit(self):
        if self.pixmap_item.pixmap().isNull():
            return
        pm  = self.pixmap_item.pixmap()
        vp  = self.view.viewport()
        off = Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        on  = Qt.ScrollBarPolicy.ScrollBarAsNeeded

        if self._fit_mode == FitMode.FIT_PAGE:
            self.view.setHorizontalScrollBarPolicy(off)
            self.view.setVerticalScrollBarPolicy(off)
            self.view.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

        elif self._fit_mode == FitMode.FIT_WIDTH:
            self.view.setHorizontalScrollBarPolicy(off)
            self.view.setVerticalScrollBarPolicy(on)
            if pm.width() > 0:
                self.view.resetTransform()
                self.view.scale(vp.width() / pm.width(), vp.width() / pm.width())

        elif self._fit_mode == FitMode.FIT_HEIGHT:
            self.view.setHorizontalScrollBarPolicy(on)
            self.view.setVerticalScrollBarPolicy(off)
            if pm.height() > 0:
                self.view.resetTransform()
                self.view.scale(vp.height() / pm.height(), vp.height() / pm.height())

        elif self._fit_mode == FitMode.ORIGINAL:
            self.view.setHorizontalScrollBarPolicy(on)
            self.view.setVerticalScrollBarPolicy(on)
            self.view.resetTransform()

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
        self.thumb_slider.setVisible(self._thumb_visible)
        if not self._thumb_visible:
            self.thumb_slider.hide_popup()
        self._update_settings_menu()
        self._layout_overlays()

    def _toggle_thumb_slider(self):
        self._set_thumbnails_visible(not self._thumb_visible)

    # ------------------------------------------------------------------ #
    # Direction                                                            #
    # ------------------------------------------------------------------ #

    def _set_reading_direction(self, rtl: bool):
        self._rtl = rtl
        self._update_settings_menu()

    def _toggle_dir(self):
        self._set_reading_direction(not self._rtl)

    # ------------------------------------------------------------------ #
    # Page display (called by subclasses after data is ready)             #
    # ------------------------------------------------------------------ #

    def clear_display(self):
        """Immediately blank the canvas and labels (prevents prior-comic flash)."""
        self.pixmap_item.setPixmap(QPixmap())
        self.title_label.setText("")
        self.counter_label.setText("0 / 0")
        self.thumb_slider.slider.setRange(0, 0)
        self.thumb_slider.slider.setValue(0)

    def _setup_reader(self, title: str, total: int, subtitle: str = None):
        """Call once the page list / reading order is known."""
        self._total = total
        self._index = 0
        
        s = UIConstants.scale
        display_text = f'<span style="font-size: {s(19)}px;">{title}</span>'
        if subtitle and subtitle.strip():
            display_text += f'<br/><i style="font-size: {s(15)}px; color: #bbb; font-weight: normal;">{subtitle.strip()}</i>'
            
        self.title_label.setText(display_text)
        self.thumb_slider.slider.setRange(0, max(0, total - 1))
        self.thumb_slider.slider.setValue(0)
        self.setFocus()

    async def _show_page(self):
        idx = self._index
        if not (0 <= idx < self._total):
            return

        layout    = self._effective_layout()
        double    = layout == PageLayout.DOUBLE
        idx2      = idx + 1 if double and idx + 1 < self._total else None
        page_desc = (f"{idx + 1}–{idx2 + 1}" if idx2 is not None else str(idx + 1))
        self.counter_label.setText(f"{page_desc} / {self._total}")

        self.thumb_slider.slider.blockSignals(True)
        self.thumb_slider.slider.setValue(idx)
        self.thumb_slider.slider.blockSignals(False)

        if idx2 is not None:
            pm1, pm2 = await asyncio.gather(
                self._load_page_pixmap(idx),
                self._load_page_pixmap(idx2),
            )
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
            if idx != self._index:
                return
            if pixmap and not pixmap.isNull():
                self.thumb_slider.store_thumb(idx, pixmap)

        if pixmap and not pixmap.isNull():
            self.pixmap_item.setPixmap(pixmap)
            self.scene.setSceneRect(self.pixmap_item.boundingRect())
            self._apply_fit()

        # Prefetch ahead and one behind for back-navigation
        ahead_start = (idx2 or idx) + 1
        for j in range(ahead_start, min(self._total, ahead_start + self.PREFETCH_AHEAD)):
            asyncio.create_task(self._do_prefetch(j))
        if idx > 0:
            asyncio.create_task(self._do_prefetch(idx - 1))

        self._on_page_changed(idx)
