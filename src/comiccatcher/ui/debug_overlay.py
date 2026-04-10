"""
Debug overlay — draws colored outlines around all visible widgets.
Toggle with Ctrl+Shift+D in the main window.

Colors by widget type:
  Red      — generic QWidget
  Blue     — QListView / QAbstractItemView
  Green    — SectionHeader / CollapsibleSection
  Orange   — BaseCardRibbon
  Cyan     — QScrollArea
"""
import logging
from PyQt6.QtWidgets import QWidget, QListView, QAbstractItemView, QScrollArea
from PyQt6.QtCore import Qt, QTimer, QRect
from PyQt6.QtGui import QPainter, QPen, QColor

_log = logging.getLogger("ui.debug_overlay")


# (r, g, b) per widget category
_COLORS = {
    "listview":   QColor(60,  120, 255, 200),   # blue
    "ribbon":     QColor(255, 140,   0, 200),   # orange
    "header":     QColor(50,  200,  50, 200),   # green
    "scroll":     QColor(0,   200, 200, 200),   # cyan
    "widget":     QColor(220,  50,  50, 160),   # red (generic)
}


def _categorize(w: QWidget):
    # Lazy imports to avoid circular dependencies
    try:
        from comiccatcher.ui.components.base_ribbon import BaseCardRibbon
        if isinstance(w, BaseCardRibbon):
            return "ribbon"
    except ImportError:
        pass
    try:
        from comiccatcher.ui.components.section_header import SectionHeader
        if isinstance(w, SectionHeader):
            return "header"
    except ImportError:
        pass
    try:
        from comiccatcher.ui.components.collapsible_section import CollapsibleSection
        if isinstance(w, CollapsibleSection):
            return "header"
    except ImportError:
        pass
    if isinstance(w, QListView):
        return "listview"
    if isinstance(w, QScrollArea):
        return "scroll"
    return "widget"


class DebugOverlay(QWidget):
    """
    Transparent mouse-through overlay installed as a child of the main window.
    Paints colored outlines over every visible descendant widget.
    Refreshes on a 150ms timer so it stays in sync as the UI changes.
    """

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        self._entries: list[tuple[QRect, QColor, str]] = []

        self._timer = QTimer(self)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()

        self._raise_and_resize()
        # Dump coords once on activation (after Qt processes pending events)
        QTimer.singleShot(300, self._log_coords)

    # ------------------------------------------------------------------
    def dump_to_log(self):
        """Public entry point for coordinate dumps."""
        self._log_coords()

    def _raise_and_resize(self):
        p = self.parent()
        if p:
            self.setGeometry(0, 0, p.width(), p.height())
            self.raise_()

    def _refresh(self):
        self._raise_and_resize()
        entries: list[tuple[QRect, QColor, str]] = []
        root = self.parent()
        if root:
            self._walk(root, entries)
        self._entries = entries
        self.update()

    def _walk(self, widget: QWidget, out: list):
        if widget is self:
            return
        if not widget.isVisible():
            return
        if not isinstance(widget, QWidget):
            return

        # Map widget's top-left corner from global into our coordinate space
        global_tl = widget.mapToGlobal(widget.rect().topLeft())
        local_tl  = self.mapFromGlobal(global_tl)
        rect = QRect(local_tl, widget.size())

        cat   = _categorize(widget)
        color = _COLORS[cat]
        label = type(widget).__name__
        out.append((rect, color, label))

        for child in widget.children():
            if isinstance(child, QWidget):
                self._walk(child, out)

    # ------------------------------------------------------------------
    def _log_coords(self):
        """Dump widget coordinates to the log for alignment inspection."""
        self._refresh()  # ensure fresh data
        _log.info("=== DEBUG OVERLAY: widget coordinate dump ===")
        for rect, color, label in self._entries:
            _log.info(f"  {label:40s}  x={rect.x():5d}  y={rect.y():5d}  w={rect.width():5d}  h={rect.height():5d}")
        _log.info("=== END DEBUG OVERLAY dump ===")

    def paintEvent(self, event):
        if not self._entries:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        from comiccatcher.ui.theme_manager import UIConstants
        font = painter.font()
        font.setPixelSize(UIConstants.scale(9))
        painter.setFont(font)

        for rect, color, label in self._entries:
            # Outline
            pen = QPen(color, 1)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect.adjusted(0, 0, -1, -1))

            # Tiny label in top-left corner with coordinates
            painter.setPen(color)
            painter.drawText(rect.adjusted(2, 1, 0, 0),
                             Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                             f"{label} ({rect.x()},{rect.y()})")

        painter.end()
