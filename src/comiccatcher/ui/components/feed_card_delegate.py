from PyQt6.QtWidgets import QStyle, QStyleOptionViewItem
from PyQt6.QtCore import Qt, QRect, QSize
from PyQt6.QtGui import QPainter, QColor, QPen
from comiccatcher.ui.theme_manager import ThemeManager, UIConstants
from comiccatcher.models.feed_page import FeedItem, ItemType
from comiccatcher.ui.components.feed_browser_model import CompositeItemType
from comiccatcher.ui.components.base_card_delegate import BaseCardDelegate, CardConfig

# Debug outline colors for delegate-painted pseudo-items
_DBG_COLORS = {
    CompositeItemType.HEADER:    QColor(255,   0, 255, 220),  # magenta
    CompositeItemType.RIBBON:    QColor(255, 200,   0, 220),  # yellow
    CompositeItemType.GRID_ITEM: QColor(160,  32, 240, 220),  # purple
}

class FeedCardDelegate(BaseCardDelegate):
    def __init__(self, parent, image_manager, show_labels=True):
        super().__init__(parent, show_labels=show_labels, reserve_progress_space=False)
        self.image_manager = image_manager
        
        # Sizing constants
        s = UIConstants.scale
        self.header_height = UIConstants.TOGGLE_BUTTON_SIZE + UIConstants.SECTION_HEADER_MARGIN_TOP
        self.ribbon_height = UIConstants.CARD_HEIGHT + s(30) # Space for ribbon widget

    def sizeHint(self, option: QStyleOptionViewItem, index):
        s = UIConstants.scale
        ctype = index.data(Qt.ItemDataRole.UserRole + 3) # CompositeTypeRole
        
        # 1. Handle Full-Width rows (Headers/Ribbons)
        if ctype in (CompositeItemType.HEADER, CompositeItemType.RIBBON):
            # Fallback width if parent is not a view
            vp_width = 1000 
            if hasattr(self.parent(), 'viewport'):
                vp_width = self.parent().viewport().width()
            
            if ctype == CompositeItemType.HEADER:
                h = self.header_height
            else:
                # Ribbon height must match BaseCardRibbon's internal calculation exactly
                card_h = UIConstants.get_card_height(self.show_labels, reserve_progress_space=False)
                # Total height = Card + Gutter + Scrollbar
                h = card_h + UIConstants.RIBBON_SCROLLBAR_GUTTER + UIConstants.SCROLLBAR_SIZE
                    
            return QSize(vp_width - s(20), h)
            
        # 2. Handle standard grid items via BaseCardDelegate
        return super().sizeHint(option, index)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        ctype = index.data(Qt.ItemDataRole.UserRole + 3)
        item = index.data(Qt.ItemDataRole.UserRole + 1)
        
        # If there is a widget set for this index, don't paint anything
        if hasattr(self.parent(), 'indexWidget') and self.parent().indexWidget(index):
            return

        if not item: return

        if ctype == CompositeItemType.HEADER:
            # Fallback painting for top-level headers in virtual list
            title = getattr(item, 'title', 'Section')
            self._draw_header(painter, option, index, title)
            return

        if ctype == CompositeItemType.GRID_ITEM:
            theme = ThemeManager.get_current_theme_colors()
            
            pixmap = None
            if item.cover_url:
                pixmap = self.image_manager.get_image_sync(item.cover_url)
                
            config = CardConfig(
                primary_text=item.title,
                cover_pixmap=pixmap,
                is_folder=(item.type == ItemType.FOLDER),
                image_manager=self.image_manager,
                reserve_progress_space=self.reserve_progress_space
            )
            self.paint_card(painter, option, theme, config)

        # Debug outlines for delegate-painted pseudo-items
        if UIConstants.DEBUG_OUTLINES and ctype in _DBG_COLORS:
            painter.save()
            color = _DBG_COLORS[ctype]
            painter.setPen(QPen(color, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(option.rect.adjusted(1, 1, -1, -1))
            font = painter.font()
            font.setPixelSize(9)
            painter.setFont(font)
            painter.setPen(color)
            painter.drawText(option.rect.adjusted(3, 2, 0, 0),
                             Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                             ctype.name if ctype else "?")
            painter.restore()

    def _draw_header(self, painter: QPainter, option: QStyleOptionViewItem, index, title: str):
        """Standard dashboard-style header painting (Fallback)."""
        painter.save()
        theme = ThemeManager.get_current_theme_colors()
        s = UIConstants.scale
        
        # Draw Chevron
        is_collapsed = index.data(Qt.ItemDataRole.UserRole + 2) # IsCollapsedRole
        icon_name = "chevron_right" if is_collapsed else "chevron_down"
        icon = ThemeManager.get_icon(icon_name, "accent")
        
        rect = option.rect
        s = UIConstants.scale
        icon_size = s(16)
        icon_rect = QRect(rect.left() + UIConstants.LAYOUT_MARGIN_DEFAULT, rect.top() + (rect.height() - icon_size) // 2, icon_size, icon_size)
        icon.paint(painter, icon_rect)
        
        # Draw Title
        painter.setPen(QColor(theme['accent']))
        font = painter.font()
        font.setPixelSize(UIConstants.FONT_SIZE_SECTION_HEADER)
        font.setBold(True)
        painter.setFont(font)
        
        text_rect = rect.adjusted(s(35), 0, -s(10), 0)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)
        painter.restore()
