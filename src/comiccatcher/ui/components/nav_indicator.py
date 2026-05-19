from PyQt6.QtWidgets import QWidget, QLabel, QHBoxLayout
from PyQt6.QtCore import Qt, QPoint, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QPainter, QColor, QIcon, QBrush, QPen

from comiccatcher.ui.theme_manager import ThemeManager, UIConstants

class NavIndicator(QWidget):
    """
    A floating overlay that shows a navigation arrow when pulling past the edge.
    Used for 'pull-to-turn' page navigation.
    """
    def __init__(self, parent=None, direction="left"):
        super().__init__(parent)
        self.direction = direction # "left" (prev) or "right" (next)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._pull_distance = 0.0
        self._threshold = UIConstants.scale(150)
        self._is_active = False
        
        # UI Metrics
        self._size = UIConstants.scale(48)
        self._margin = UIConstants.scale(20)
        
        self.setFixedSize(self._size + self._margin * 2, self._size * 2)
        self.hide()

    @pyqtProperty(float)
    def pull_distance(self):
        return self._pull_distance

    @pull_distance.setter
    def pull_distance(self, val):
        self._pull_distance = abs(val)
        self._is_active = self._pull_distance >= self._threshold
        self.update_position()
        self.update()
        if self._pull_distance > 0.1:
            self.show()
        else:
            self.hide()

    def update_position(self):
        if not self.parent(): return
        parent_rect = self.parent().rect()
        
        # Calculate how much of the indicator is visible
        # We start hidden off-screen and slide in as pull increases.
        # Max slide-in is full size + margin.
        visible_amt = min(self._pull_distance / self._threshold, 1.0) * (self._size + self._margin)
        
        y = (parent_rect.height() - self.height()) // 2
        
        if self.direction == "left":
            x = int(visible_amt - self.width())
        else:
            x = int(parent_rect.width() - visible_amt)
            
        self.move(x, y)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        theme = ThemeManager.get_current_theme_colors()
        accent = QColor(theme.get('accent', '#007AFF'))
        bg = QColor(theme.get('surface_highest', '#333333'))
        
        # Use active color if threshold reached
        color = accent if self._is_active else bg
        opacity = min(self._pull_distance / self._threshold, 1.0)
        color.setAlphaF(opacity * 0.9)
        
        # Draw background circle/pill
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        
        rect = self.rect()
        if self.direction == "left":
            # Draw half-circle on the right side of our widget
            circle_rect = rect.adjusted(rect.width() - self._size, (rect.height() - self._size) // 2, 0, -(rect.height() - self._size) // 2)
            painter.drawEllipse(circle_rect)
            
            # Draw arrow
            icon_name = "chevron_left"
        else:
            # Draw half-circle on the left side
            circle_rect = rect.adjusted(0, (rect.height() - self._size) // 2, -(rect.width() - self._size), -(rect.height() - self._size) // 2)
            painter.drawEllipse(circle_rect)
            
            icon_name = "chevron_right"
            
        # Draw Icon
        icon = ThemeManager.get_icon(icon_name, "text_primary" if self._is_active else "text_secondary")
        icon_size = UIConstants.scale(24)
        icon_rect = circle_rect.adjusted(
            (circle_rect.width() - icon_size) // 2,
            (circle_rect.height() - icon_size) // 2,
            -(circle_rect.width() - icon_size) // 2,
            -(circle_rect.height() - icon_size) // 2
        )
        painter.drawPixmap(icon_rect, icon.pixmap(icon_size, icon_size))
