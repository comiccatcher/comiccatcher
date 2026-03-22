from PyQt6.QtWidgets import QStyledItemDelegate, QStyle, QStyleOptionViewItem, QFrame
from PyQt6.QtCore import Qt, QRect, QSize, QPoint
from PyQt6.QtGui import QPainter, QColor, QPixmap, QFont, QPen
from ui.theme_manager import UIConstants, ThemeManager
from api.image_manager import ImageManager
from models.feed_page import FeedItem, ItemType
from ui.components.base_card_delegate import BaseCardDelegate

class FeedCardDelegate(BaseCardDelegate):
    """
    Renders FeedItems in a grid or ribbon.
    Handles 'Standard Cell' logic (Mockup 3).
    """
    
    def __init__(self, parent=None, image_manager: ImageManager = None, show_labels=True):
        super().__init__(parent, show_labels=show_labels)
        self.image_manager = image_manager

    def sizeHint(self, option, index):
        item: FeedItem = index.data(Qt.ItemDataRole.UserRole + 1)
        if item and item.type == ItemType.HEADER:
            s = UIConstants.scale
            return QSize(self.card_width * 3, s(40)) # Full width header
        return super().sizeHint(option, index)

    def reapply_theme(self):
        """No-op as paint() fetches theme on every call, but here for consistency."""
        pass

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        item: FeedItem = index.data(Qt.ItemDataRole.UserRole + 1)
        if not item:
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        theme = ThemeManager.get_current_theme_colors()

        rect = option.rect

        # 1. Handle HEADERS
        if item.type == ItemType.HEADER:
            self._draw_header(painter, option, rect, item.title)
            painter.restore()
            return

        # 2. Handle EMPTY (Skeletons)
        if item.type == ItemType.EMPTY:
            self._draw_skeleton(painter, rect, theme)
            painter.restore()
            return

        # 3. Draw standard card background
        content_rect = self.draw_card_background(painter, rect, option, theme)

        # 4. Cover / Folder Art Area
        cover_area_rect = QRect(content_rect.left(), content_rect.top(), content_rect.width(), self.cover_height)
        
        if item.type == ItemType.FOLDER:
            self.draw_folder_stack(painter, cover_area_rect, theme, image_manager=self.image_manager, label=item.title)
        else:
            # Load and draw cover image
            pixmap = None
            if item.cover_url and self.image_manager:
                cache_path = self.image_manager._get_cache_path(item.cover_url)
                if cache_path.exists():
                    pixmap = QPixmap(str(cache_path))
            
            if pixmap and not pixmap.isNull():
                self.draw_cover_pixmap(painter, cover_area_rect, pixmap)
            else:
                # Placeholder
                painter.setBrush(QColor(theme['text_dim']))
                painter.setOpacity(0.2)
                s = UIConstants.scale
                painter.drawRoundedRect(cover_area_rect.adjusted(s(10), s(10), -s(10), -s(10)), s(3), s(3))
                painter.setOpacity(1.0)
                
        # 4. Progress bar (BELOW the cover)
        s = UIConstants.scale
        prog_bar_y = cover_area_rect.bottom() + s(2)
        progress_rect = QRect(content_rect.left(), prog_bar_y, content_rect.width(), UIConstants.PROGRESS_BAR_TOTAL_HEIGHT)
        
        # Feed items currently don't expose progress easily, but we prepare the area for consistency
        # If we add progress to FeedItem later, it will draw here.

        # 5. Label Text
        if self.show_labels:
            # Label starts after progress bar area to match Library View
            text_y = progress_rect.bottom() + s(2)
            text_rect = QRect(content_rect.left() + s(5), text_y, content_rect.width() - s(10), self.label_height)
            self.draw_label(painter, text_rect, item.title, theme)

        painter.restore()

    def _draw_header(self, painter: QPainter, option: QStyleOptionViewItem, rect: QRect, title: str):
        painter.save()
        theme = ThemeManager.get_current_theme_colors()
        painter.setPen(QColor(theme['accent']))
        font = painter.font()
        s = UIConstants.scale
        font.setPointSize(UIConstants.FONT_SIZE_SECTION_HEADER)
        font.setBold(True)
        painter.setFont(font)
        # Add slight left margin
        text_rect = rect.adjusted(s(10), 0, -s(10), 0)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)
        painter.restore()

    def _draw_skeleton(self, painter: QPainter, rect: QRect, theme: dict):
        """Draws a theme-aware loading skeleton."""
        import time
        pulse = (int(time.time() * 2) % 2) * 10
        base_color = QColor(theme['text_dim'])
        color = QColor(base_color.red(), base_color.green(), base_color.blue(), 30 + pulse)
        
        p = UIConstants.CARD_PADDING
        content_rect = rect.adjusted(p, p, -p, -p)
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        
        # Draw skeleton card bg
        painter.setBrush(QColor(theme['card_bg']))
        painter.drawRoundedRect(content_rect, UIConstants.CARD_ROUNDING, UIConstants.CARD_ROUNDING)
        
        painter.setBrush(color)
        cover_rect = QRect(content_rect.left(), content_rect.top(), content_rect.width(), self.cover_height)
        painter.drawRoundedRect(cover_rect, UIConstants.CARD_ROUNDING, UIConstants.CARD_ROUNDING)
        
        if self.show_labels:
            sp = UIConstants.SKELETON_PADDING
            sr = UIConstants.SKELETON_ROUNDING
            s = UIConstants.scale
            text_rect = QRect(content_rect.left() + sp, cover_rect.bottom() + sp, content_rect.width() - (sp * 2), s(15))
            painter.drawRoundedRect(text_rect, sr, sr)
