from dataclasses import dataclass
from typing import Optional
from PyQt6.QtWidgets import QStyledItemDelegate, QStyle, QStyleOptionViewItem
from PyQt6.QtCore import Qt, QRect, QSize, QRectF, QByteArray
from PyQt6.QtGui import QPainter, QColor, QPixmap, QFont, QPen
from PyQt6.QtSvg import QSvgRenderer
from comiccatcher.ui.theme_manager import UIConstants, ThemeManager, ICON_DIR

@dataclass
class CardConfig:
    """Configuration for painting a standardized card."""
    primary_text: str = ""
    secondary_text: Optional[str] = None
    cover_pixmap: Optional[QPixmap] = None
    is_folder: bool = False
    folder_icon_name: str = "folder"
    badge_icon_name: Optional[str] = None
    fallback_icon_name: str = "book"
    progress_pct: float = 0.0
    progress_color: Optional[QColor] = None
    image_manager: Optional[object] = None # Used for server logo fallback in folders
    dim_cover: bool = False # Used to indicate a "read" state
    reserve_progress_space: bool = True # Whether to keep space for a progress bar

class BaseCardDelegate(QStyledItemDelegate):
    """
    Base class for card-based delegates (Library and Browser).
    Provides shared drawing primitives for visual consistency.
    """
    
    def __init__(self, parent, show_labels=True, reserve_progress_space=True):
        super().__init__(parent)
        self.show_labels = show_labels
        self.reserve_progress_space = reserve_progress_space

        self.card_width = UIConstants.CARD_WIDTH
        self.card_height = UIConstants.CARD_HEIGHT
        self.cover_height = UIConstants.CARD_COVER_HEIGHT
        self.label_height = UIConstants.CARD_LABEL_HEIGHT
        self.spacing = UIConstants.CARD_SPACING

    def sizeHint(self, option, index):
        return QSize(UIConstants.CARD_WIDTH, UIConstants.get_card_height(self.show_labels, self.reserve_progress_space))

    def paint_card(self, painter: QPainter, option: QStyleOptionViewItem, theme: dict, config: CardConfig):
        """
        Centralized orchestration method for painting a standardized card.
        Handles the layout and order of all possible card elements.
        """
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = option.rect
        
        # 1. Background
        content_rect = self.draw_card_background(painter, rect, option, theme)
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        
        # 2. Cover Area Calculation
        # The cover always starts at CARD_PADDING from the top of the rounded box (content_rect)
        cover_area_rect = QRect(content_rect.left(), content_rect.top() + UIConstants.CARD_PADDING, 
                                content_rect.width(), self.cover_height)
            
        # 3. Draw Main Visual (Folder, Cover, or Fallback)
        if config.is_folder:
            self.draw_folder_stack(
                painter, 
                cover_area_rect, 
                theme, 
                image_manager=config.image_manager, 
                label=config.primary_text,
                icon_name=config.folder_icon_name,
                badge_icon_name=config.badge_icon_name
            )
        elif config.cover_pixmap and not config.cover_pixmap.isNull():
            opacity = 0.5 if config.dim_cover else 1.0
            self.draw_cover_pixmap(painter, cover_area_rect, config.cover_pixmap, opacity)
        else:
            # Standard fallback (e.g. book icon)
            # We only show the icon if it's NOT a folder and we don't have a pixmap.
            # However, if we are in the middle of an async load, we prefer a neutral skeleton.
            self._draw_skeleton(painter, cover_area_rect, theme)
            
            # Only draw icon if it's the final state (e.g. no image_manager or failed load)
            # For now, we'll check if a pixmap is specifically NULL vs MISSING.
            # A more robust way is to just use a very subtle icon.
            s = UIConstants.scale
            icon = ThemeManager.get_icon(config.fallback_icon_name, "text_dim")
            icon_size = s(40)
            icon_rect = QRect(cover_area_rect.left() + (cover_area_rect.width() - icon_size) // 2,
                             cover_area_rect.top() + (cover_area_rect.height() - icon_size) // 2,
                             icon_size, icon_size)
            painter.setOpacity(0.3)
            icon.paint(painter, icon_rect)
            painter.setOpacity(1.0)

        # 4. Progress bar (BELOW the cover area)
        # Determine where labels start based on progress space reservation
        if config.reserve_progress_space:
            # Match get_card_height logic exactly: CoverBottom + Gap (2px)
            prog_bar_y = cover_area_rect.bottom() + UIConstants.PROGRESS_BAR_GAP
            progress_rect = QRect(content_rect.left(), prog_bar_y, content_rect.width(), UIConstants.PROGRESS_BAR_TOTAL_HEIGHT)
            if not config.is_folder and 0 < config.progress_pct < 0.99:
                color = config.progress_color or option.palette.highlight().color()
                self.draw_progress_bar(painter, progress_rect, config.progress_pct, color)
            label_y = progress_rect.bottom() + UIConstants.CARD_PADDING
        else:
            # No progress space: Labels start after cover + padding
            label_y = cover_area_rect.bottom() + UIConstants.CARD_PADDING

        # 5. External Labels
        if self.show_labels:
            text_rect = QRect(content_rect.left() + UIConstants.CARD_PADDING, 
                              label_y, 
                              content_rect.width() - (UIConstants.CARD_PADDING * 2), 
                              UIConstants.CARD_LABEL_HEIGHT)
            
            forced_color = None
            if is_selected:
                forced_color = QColor(theme.get('text_selected', theme['white']))
                
            self.draw_label(painter, text_rect, config.primary_text, theme, config.secondary_text, forced_text_color=forced_color)
        else:
            # Internal label as a backup when covers are missing
            # (Folders handle their own internal label inside draw_folder_stack)
            if not config.is_folder and (not config.cover_pixmap or config.cover_pixmap.isNull()):
                self.draw_internal_label(painter, cover_area_rect, config.primary_text, theme)
                
        painter.restore()

    def _draw_skeleton(self, painter: QPainter, rect: QRect, theme: dict):
        """Draws an empty placeholder box for missing covers."""
        painter.save()
        painter.setBrush(QColor(theme['card_border']))
        painter.setPen(Qt.PenStyle.NoPen)
        s = UIConstants.scale
        painter.drawRoundedRect(rect, s(4), s(4))
        painter.restore()

    def draw_card_background(self, painter: QPainter, rect: QRect, option: QStyleOptionViewItem, theme: dict):
        """Draws the standard rounded card background and border."""
        p = UIConstants.CARD_PADDING
        s = UIConstants.scale
        
        # Center the card in the provided rect if it's wider than our standard
        # This prevents stretching in justified layouts.
        target_w = UIConstants.CARD_WIDTH
        
        # We only cap if the rect is significantly wider
        if rect.width() > target_w + UIConstants.LAYOUT_MARGIN_LARGE: 
            offset_x = (rect.width() - target_w) // 2
            draw_rect = QRect(rect.left() + offset_x, rect.top(), target_w, rect.height())
        else:
            draw_rect = rect
            
        content_rect = draw_rect.adjusted(p, p + UIConstants.CARD_MARGIN_TOP, -p, -p)
        
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setBrush(QColor(theme['bg_item_selected']))
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
                # Center and scale keeping aspect ratio
                pw, ph = cached_icon.width(), cached_icon.height()
                scale = min(badge_size / pw, badge_size / ph)
                dw, dh = int(pw * scale), int(ph * scale)
                dx = int(badge_x + (badge_size - dw) / 2)
                dy = int(badge_y + (badge_size - dh) / 2)
                painter.drawPixmap(dx, dy, dw, dh, cached_icon)
            else:
                # Fallback to generic feeds icon if no server logo
                default_icon = ThemeManager.get_icon("feeds", "text_dim")
                default_icon.paint(painter, int(badge_x), int(badge_y), int(badge_size), int(badge_size))

        # 4. Internal Label (only used when global labels are off)
        if label and not self.show_labels:
            self.draw_internal_label(painter, rect, label, theme)

    def draw_internal_label(self, painter: QPainter, rect: QRect, text: str, theme: dict):
        """Draws a semi-transparent label strip inside the card area."""
        painter.save()
        font = painter.font()
        font.setPixelSize(UIConstants.FONT_SIZE_CARD_LABEL)
        font.setBold(False)
        painter.setFont(font)
        
        # Draw semi-transparent background strip at bottom
        s = UIConstants.scale
        margin = s(4)
        metrics = painter.fontMetrics()
        line_h = metrics.lineSpacing()
        strip_h = (line_h * 2) + s(4) # 2 rows + small padding
        strip_rect = QRect(rect.left() + margin, rect.bottom() - strip_h - margin, rect.width() - (margin * 2), strip_h)
        
        # Subtle dim background
        bg_color = QColor(theme['bg_main'])
        bg_color.setAlpha(180)
        painter.setBrush(bg_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(strip_rect, s(4), s(4))
        
        # Draw text (Middle-elided, 2 rows max)
        painter.setPen(QColor(theme['text_main']))
        elided = metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, int(strip_rect.width() * UIConstants.ELIDED_TEXT_WIDTH_FACTOR))
        painter.drawText(strip_rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, elided)
        painter.restore()

    def draw_label(self, painter: QPainter, rect: QRect, text: str, theme: dict, secondary_text: str = None, forced_text_color: QColor = None):
        """Draws the elided bold primary label, and optional dimmer secondary text below."""
        if not text or not self.show_labels:
            return
            
        # 1. Primary Label
        painter.setPen(forced_text_color if forced_text_color else QColor(theme['text_main']))
        font = painter.font()
        font.setPixelSize(UIConstants.FONT_SIZE_CARD_LABEL)
        font.setBold(False)
        painter.setFont(font)
        
        metrics = painter.fontMetrics()
        
        if secondary_text:
            # If we have secondary text, primary only gets one line
            elided_primary = metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, rect.width())
            painter.drawText(rect, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter, elided_primary)
            
            # Draw secondary below primary
            if forced_text_color:
                # Dim the forced color for secondary
                sec_color = QColor(forced_text_color)
                sec_color.setAlpha(180)
                painter.setPen(sec_color)
            else:
                painter.setPen(QColor(theme.get('text_dim', '#a0a0a0')))
            
            font.setBold(False)
            font.setPixelSize(UIConstants.FONT_SIZE_CARD_LABEL - 1)
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
            
            # Use elidedText with a width that represents ~2 lines of text.
            # We use a conservative factor to ensure it fits.
            elided_text = metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, int(rect.width() * 1.65))
            
            # Use explicit clipping to GUARANTEE no spillover
            painter.save()
            painter.setClipRect(label_rect)
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap, elided_text)
            painter.restore()

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
