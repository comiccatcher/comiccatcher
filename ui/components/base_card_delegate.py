from PyQt6.QtWidgets import QStyledItemDelegate, QStyle, QStyleOptionViewItem
from PyQt6.QtCore import Qt, QRect, QSize, QRectF, QByteArray
from PyQt6.QtGui import QPainter, QColor, QPixmap, QFont, QPen
from PyQt6.QtSvg import QSvgRenderer
from ui.theme_manager import UIConstants, ThemeManager, ICON_DIR

class BaseCardDelegate(QStyledItemDelegate):
    """
    Base class for card-based delegates (Library and Browser).
    Provides shared drawing primitives for visual consistency.
    """
    
    def __init__(self, parent=None, show_labels=True):
        super().__init__(parent)
        self.show_labels = show_labels
        self.card_width = UIConstants.CARD_WIDTH
        self.card_height = UIConstants.CARD_HEIGHT
        self.cover_height = UIConstants.CARD_COVER_HEIGHT
        self.label_height = UIConstants.CARD_LABEL_HEIGHT
        self.spacing = UIConstants.CARD_SPACING

    def sizeHint(self, option, index):
        if not self.show_labels:
            # Shrink height if labels are hidden, but keep room for progress bar.
            # cover_height (180) + prog_bar (10) + margin (10)
            return QSize(UIConstants.CARD_WIDTH, UIConstants.CARD_COVER_HEIGHT + UIConstants.PROGRESS_BAR_TOTAL_HEIGHT + UIConstants.CARD_SPACING)
        return QSize(UIConstants.CARD_WIDTH, UIConstants.CARD_HEIGHT)

    def draw_card_background(self, painter: QPainter, rect: QRect, option: QStyleOptionViewItem, theme: dict):
        """Draws the standard rounded card background and border."""
        p = UIConstants.CARD_PADDING
        s = UIConstants.scale
        
        # Center the card in the provided rect if it's wider than our standard
        # This prevents stretching in justified layouts.
        target_w = UIConstants.CARD_WIDTH
        
        # We only cap if the rect is significantly wider (headers handle their own drawing)
        # In IconMode, rect.width() might be expanded by the layout engine.
        if rect.width() > target_w + s(20): 
            # If it's a card, center it. If it's a header (managed by subclass), 
            # the subclass usually overrides or we handle it here.
            # BaseCardDelegate is used for Cards.
            offset_x = (rect.width() - target_w) // 2
            draw_rect = QRect(rect.left() + offset_x, rect.top(), target_w, rect.height())
        else:
            draw_rect = rect
            
        content_rect = draw_rect.adjusted(p, p, -p, -p)
        
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setBrush(QColor(theme['accent_dim']))
            painter.setPen(QPen(QColor(theme['accent']), UIConstants.CARD_BORDER_WIDTH_SELECTED))
        else:
            painter.setBrush(QColor(theme['card_bg']))
            painter.setPen(QPen(QColor(theme['card_border']), UIConstants.CARD_BORDER_WIDTH))
            
        painter.drawRoundedRect(content_rect, UIConstants.CARD_ROUNDING, UIConstants.CARD_ROUNDING)
        return content_rect

    def draw_cover_pixmap(self, painter: QPainter, rect: QRect, pixmap: QPixmap, opacity: float = 1.0):
        """Scales and draws a cover pixmap centered in the target rect."""
        if not pixmap or pixmap.isNull():
            return

        pw, ph = pixmap.width(), pixmap.height()
        if pw <= 0 or ph <= 0:
            return
            
        scale = min(rect.width() / pw, rect.height() / ph)
        # Avoid over-scaling small icons
        if pw < 64: scale = min(scale, 2.0)
        
        draw_w, draw_h = int(pw * scale), int(ph * scale)
        paint_rect = QRect(
            rect.left() + (rect.width() - draw_w) // 2,
            rect.top() + (rect.height() - draw_h) // 2,
            draw_w,
            draw_h
        )
        
        if opacity < 1.0:
            painter.setOpacity(opacity)
            painter.drawPixmap(paint_rect, pixmap)
            painter.setOpacity(1.0)
        else:
            painter.drawPixmap(paint_rect, pixmap)
            
        return paint_rect

    def draw_folder_stack(self, painter: QPainter, rect: QRect, theme: dict, image_manager=None, label: str = None, icon_name: str = "folder", badge_icon_name: str = None):
        """Draws the SVG folder stack icon, with optional server logo badge and internal label."""
        # 1. Inner Background
        painter.setBrush(QColor(theme['bg_sidebar']))
        painter.setPen(QColor(theme['border']))
        painter.drawRoundedRect(rect, UIConstants.CARD_ROUNDING, UIConstants.CARD_ROUNDING)
        
        # 2. SVG Icon
        s = UIConstants.scale
        margin = UIConstants.FOLDER_ICON_MARGIN
        if label and not self.show_labels:
            # Shrink icon slightly more to make room for 2 rows of text
            margin += s(15)
            
        folder_size = min(rect.width(), rect.height()) - margin
        color = theme.get("text_dim", "#a0a0a0")
        svg_path = ICON_DIR / f"{icon_name}.svg"
        
        x = rect.left() + (rect.width() - folder_size) // 2
        y = rect.top() + (rect.height() - folder_size) // 2
        
        # Shift icon up slightly if we are showing an internal label
        if label and not self.show_labels:
            y -= s(12)
        
        if svg_path.exists():
            svg_bytes = svg_path.read_bytes()
            svg_bytes = svg_bytes.replace(b'stroke="white"', f'stroke="{color}"'.encode())
            svg_bytes = svg_bytes.replace(b'fill="white"', f'fill="{color}"'.encode())
            
            renderer = QSvgRenderer(QByteArray(svg_bytes))
            folder_rect = QRectF(x, y, folder_size, folder_size)
            
            painter.setOpacity(0.8)
            renderer.render(painter, folder_rect)
            painter.setOpacity(1.0)

        # 3. Server Logo Badge or Custom Badge
        badge_size = UIConstants.FOLDER_BADGE_SIZE
        badge_x = x + (folder_size - badge_size) / 2
        badge_y = y + (folder_size - badge_size) / 2 + UIConstants.FOLDER_BADGE_OFFSET_Y

        if badge_icon_name:
            badge_svg_path = ICON_DIR / f"{badge_icon_name}.svg"
            if badge_svg_path.exists():
                svg_bytes = badge_svg_path.read_bytes()
                svg_bytes = svg_bytes.replace(b'stroke="white"', f'stroke="{color}"'.encode())
                svg_bytes = svg_bytes.replace(b'fill="white"', f'fill="{color}"'.encode())
                
                renderer = QSvgRenderer(QByteArray(svg_bytes))
                badge_rect = QRectF(badge_x, badge_y, badge_size, badge_size)
                
                painter.setOpacity(0.6)
                renderer.render(painter, badge_rect)
                painter.setOpacity(1.0)
        elif image_manager and getattr(image_manager, 'api_client', None):
            profile = getattr(image_manager.api_client, 'profile', None)
            cached_icon = getattr(profile, '_cached_icon', None) if profile else None
            if cached_icon and not cached_icon.isNull():
                painter.drawPixmap(int(badge_x), int(badge_y), int(badge_size), int(badge_size), cached_icon)

        # 4. Internal Label (only used when global labels are off)
        if label and not self.show_labels:
            painter.save()
            font = painter.font()
            font.setPointSize(UIConstants.FONT_SIZE_CARD_LABEL - 1)
            font.setBold(False)
            painter.setFont(font)
            
            # Draw semi-transparent background strip at bottom
            s = UIConstants.scale
            margin = s(4)
            metrics = painter.fontMetrics()
            line_h = metrics.lineSpacing()
            strip_h = (line_h * 2) + s(4) # 2 rows + small padding
            strip_rect = QRect(rect.left() + margin, rect.bottom() - strip_h - margin, rect.width() - (margin * 2), strip_h)
            
            # Subtle gradient or solid dim background
            bg_color = QColor(theme['bg_main'])
            bg_color.setAlpha(180)
            painter.setBrush(bg_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(strip_rect, s(4), s(4))
            
            # Draw text (Middle-elided, 2 rows max)
            painter.setPen(QColor(theme['text_main']))
            # Use a conservative heuristic (1.85x) to account for word-wrap overhead
            # and ensure we don't trigger a 3rd line.
            elided = metrics.elidedText(label, Qt.TextElideMode.ElideMiddle, int(strip_rect.width() * 1.85))
            painter.drawText(strip_rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, elided)
            painter.restore()

    def draw_label(self, painter: QPainter, rect: QRect, text: str, theme: dict, secondary_text: str = None):
        """Draws the elided bold primary label, and optional dimmer secondary text below."""
        if not text or not self.show_labels:
            return
            
        # 1. Primary Label
        painter.setPen(QColor(theme['text_main']))
        font = painter.font()
        font.setPointSize(UIConstants.FONT_SIZE_CARD_LABEL)
        font.setBold(False)
        painter.setFont(font)
        
        metrics = painter.fontMetrics()
        
        if secondary_text:
            # If we have secondary text, primary only gets one line
            elided_primary = metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, rect.width())
            painter.drawText(rect, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter, elided_primary)
            
            # Draw secondary below primary
            painter.setPen(QColor(theme.get('text_dim', '#a0a0a0')))
            font.setBold(False)
            font.setPointSize(UIConstants.FONT_SIZE_CARD_LABEL - 1)
            painter.setFont(font)
            
            elided_secondary = metrics.elidedText(secondary_text, Qt.TextElideMode.ElideMiddle, rect.width())
            s = UIConstants.scale
            secondary_rect = rect.adjusted(0, metrics.height() + s(2), 0, 0)
            painter.drawText(secondary_rect, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter, elided_secondary)
        else:
            # No secondary text: primary label can use full space (2 rows max)
            # Use elidedText with a width that represents 2 lines
            # and ensure we don't spill to a 3rd line by using a fixed height for drawing
            line_height = metrics.lineSpacing()
            max_height = line_height * 2
            
            # Draw into a rect limited to 2 lines height
            label_rect = QRect(rect.left(), rect.top(), rect.width(), max_height)
            
            # Use elidedText with a width that represents ~2 lines of text
            # ElideMiddle is requested.
            elided_text = metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, int(rect.width() * 1.9))
            
            # Draw with word wrap but strictly within 2-line height
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap, elided_text)

    def draw_progress_bar(self, painter: QPainter, rect: QRect, progress: float, color: QColor):
        """Draws a subtle progress bar in the dedicated progress area."""
        if progress <= 0 or progress >= 1.0:
            return
            
        bar_h = UIConstants.PROGRESS_BAR_HEIGHT
        m_h = UIConstants.PROGRESS_BAR_MARGIN_H
        
        # Center bar vertically in the provided rect
        y = rect.top() + (rect.height() - bar_h) // 2
        bar_rect = QRect(rect.left() + m_h, y, rect.width() - (m_h * 2), bar_h)
        
        painter.fillRect(bar_rect, QColor(0, 0, 0, 100))
        painter.fillRect(QRect(bar_rect.left(), bar_rect.top(), int(bar_rect.width() * progress), bar_h), color)
