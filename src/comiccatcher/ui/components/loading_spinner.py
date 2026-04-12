from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QPainter, QPen, QColor

class LoadingSpinner(QWidget):
    """
    A modular, reusable circular indeterminate progress indicator.
    Scales perfectly and pulls colors from the current theme.
    """
    def __init__(self, parent=None, size=24, color=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._angle = 0
        self._color = color
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self.hide() # Hidden by default

    def _rotate(self):
        self._angle = (self._angle - 10) % 360
        self.update()

    def set_color(self, color: QColor):
        self._color = color
        self.update()

    def paintEvent(self, event):
        if not self.isVisible():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        pen = QPen()
        # Fallback to a generic blue if theme color isn't provided
        color = self._color or QColor("#3b82f6")
        pen.setColor(color)
        pen.setWidth(3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        
        # Draw a 270-degree arc that "spins"
        margin = 3
        rect = QRectF(margin, margin, self.width() - margin*2, self.height() - margin*2)
        painter.drawArc(rect, self._angle * 16, 270 * 16)

    def start(self):
        """Starts the animation and shows the widget."""
        try:
            if not self._timer.isActive():
                self._timer.start(30) # ~33 fps
            self.show()
        except RuntimeError:
            pass # Object deleted

    def stop(self):
        """Stops the animation and hides the widget."""
        try:
            self._timer.stop()
            self.hide()
        except RuntimeError:
            pass # Object deleted
