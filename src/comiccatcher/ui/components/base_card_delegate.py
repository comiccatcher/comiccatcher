# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

from dataclasses import dataclass
from typing import Optional
from PyQt6.QtWidgets import QStyledItemDelegate, QStyle, QStyleOptionViewItem, QToolTip
from PyQt6.QtCore import Qt, QRect, QSize, QRectF, QByteArray, QEvent, QPoint, QModelIndex
from PyQt6.QtGui import QPainter, QColor, QPixmap, QPen
from PyQt6.QtSvg import QSvgRenderer
from comiccatcher.ui.theme_manager import UIConstants, ThemeManager, ICON_DIR

@dataclass
class CardConfig:
    primary_text: str
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
    card_size: str = "medium"
class BaseCardDelegate(QStyledItemDelegate):
    """
    Base class for card-based delegates (Library and Browser).
    Provides shared drawing primitives for visual consistency.
    """
    
    def __init__(self, parent, show_labels=True, reserve_progress_space=True, card_size="medium"):
        super().__init__(parent)
        self._show_labels = show_labels
        self.reserve_progress_space = reserve_progress_space
        self._card_size = card_size
        self._skeleton_cache = {} # Keyed by (size, theme_name, is_selected) -> QPixmap
        self._label_cache = {}    # Keyed by (primary, secondary, size, theme_name, is_selected) -> QPixmap
        self._update_metrics()

    def reapply_theme(self):
        """Invalidate the painting cache when theme changes."""
        self._skeleton_cache.clear()
        self._label_cache.clear()

    @property
    def card_size(self):
        return self._card_size

    @card_size.setter
    def card_size(self, size: str):
        if self._card_size == size: return
        self._card_size = size
        self._update_metrics()

    @property
    def show_labels(self):
        return self._show_labels

    @show_labels.setter
    def show_labels(self, enabled: bool):
        if self._show_labels == enabled: return
        self._show_labels = enabled
        self._update_metrics()

    def _update_metrics(self):
        """Recalculate all internal sizing tokens based on current state."""
        self.card_width = UIConstants.get_card_width(self._card_size)
        self.card_height = UIConstants.get_card_height(self._show_labels, self.reserve_progress_space, self._card_size)
        self.cover_height = UIConstants.get_card_cover_height(self._card_size)
        self.label_height = UIConstants.CARD_LABEL_HEIGHT
        self.spacing = UIConstants.CARD_SPACING

    def sizeHint(self, option, index):
        return QSize(self.card_width, self.card_height)

    def helpEvent(self, event, view, option, index):
        """Show the primary title as a tooltip on hover."""
        if event.type() == QEvent.Type.ToolTip:
            tooltip = index.data(Qt.ItemDataRole.ToolTipRole)
            if not tooltip:
                tooltip = index.data(Qt.ItemDataRole.DisplayRole)
            
            if tooltip and tooltip != "Loading...":
                QToolTip.showText(event.globalPos(), tooltip, view)
                return True
        return super().helpEvent(event, view, option, index)

    def paint_card(self, painter: QPainter, option: QStyleOptionViewItem, index, theme: dict, config: CardConfig):
        """
        Centralized orchestration method for painting a standardized card.
        Handles the layout and order of all possible card elements.
        """
        # Ensure metrics match the requested card size for this specific paint call
        old_size = self._card_size
        self.card_size = config.card_size

        try:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            rect = option.rect
            
            # 1. Background
            content_rect = self.draw_card_background(painter, rect, option, theme)
            
            # Selection Badge: Visible even when keyboard cursor is active
            view = option.widget or self.parent()
            is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
            
            is_keyboard_focused = self._is_keyboard_focused(index=index)
            
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
                    badge_icon_name=config.badge_icon_name,
                    pixmap=config.cover_pixmap
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

                self.draw_label(painter, text_rect, config.primary_text, theme, config.secondary_text, forced_text_color=forced_color)
            else:
                # Internal label as a backup when covers are missing
                # (Folders handle their own internal label inside draw_folder_stack)
                if not config.is_folder and (not config.cover_pixmap or config.cover_pixmap.isNull()):
                    self.draw_internal_label(painter, cover_area_rect, config.primary_text, theme)

            if is_selected:
                self.draw_selection_badge(painter, content_rect, theme)
            if is_keyboard_focused:
                self.draw_keyboard_focus_ring(painter, content_rect, theme)
                    
            painter.restore()
        finally:
            # Restore original global size
            self.card_size = old_size

    def _draw_skeleton(self, painter: QPainter, rect: QRect, theme: dict):
        """Draws an empty placeholder box for missing covers."""
        painter.save()
        painter.setBrush(QColor(theme['card_border']))
        painter.setPen(Qt.PenStyle.NoPen)
        s = UIConstants.scale
        painter.drawRoundedRect(rect, s(4), s(4))
        painter.restore()

    def draw_card_background(self, painter: QPainter, rect: QRect, option: QStyleOptionViewItem, theme: dict):
        """Draws the standard rounded card background and border, using a pixmap cache."""
        p = UIConstants.CARD_PADDING
        s = UIConstants.scale
        theme_name = ThemeManager._current_theme
        
        target_w = UIConstants.get_card_width(self.card_size)
        target_h = self.card_height # Full delegate cell height
        
        # 1. Check/Build Pixmap Cache for the "Shell"
        cache_key = (self.card_size, theme_name)
        if cache_key not in self._skeleton_cache:
            from PyQt6.QtGui import QPixmap
            # Create a transparent pixmap exactly the size of a standard card
            # Using the full cell height so we only have to draw it once.
            pm = QPixmap(target_w, target_h)
            pm.fill(Qt.GlobalColor.transparent)
            pm_painter = QPainter(pm)
            pm_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            # Draw the background inside the standard card rect
            card_rect = QRect(0, 0, target_w, target_h)
            content_rect = card_rect.adjusted(p, p + UIConstants.CARD_MARGIN_TOP, -p, -p)
            
            pm_painter.setBrush(QColor(theme['card_bg']))
            pm_painter.setPen(QPen(QColor(theme['card_border']), UIConstants.CARD_BORDER_WIDTH))
                
            pm_painter.drawRoundedRect(content_rect, UIConstants.CARD_ROUNDING, UIConstants.CARD_ROUNDING)
            pm_painter.end()
            self._skeleton_cache[cache_key] = pm

        # 2. Paint the cached pixmap
        # Center the card in the provided rect if it's wider than our standard
        if rect.width() > target_w + UIConstants.LAYOUT_MARGIN_LARGE: 
            offset_x = (rect.width() - target_w) // 2
            painter.drawPixmap(rect.left() + offset_x, rect.top(), self._skeleton_cache[cache_key])
        else:
            painter.drawPixmap(rect.left(), rect.top(), self._skeleton_cache[cache_key])
            
        # Return the content_rect relative to the painter's current coordinate system
        # (Needed by the rest of the paint_card pipeline)
        if rect.width() > target_w + UIConstants.LAYOUT_MARGIN_LARGE: 
            offset_x = (rect.width() - target_w) // 2
            return QRect(rect.left() + offset_x + p, rect.top() + p + UIConstants.CARD_MARGIN_TOP, target_w - (p*2), target_h - (p*2) - UIConstants.CARD_MARGIN_TOP)
        else:
            return QRect(rect.left() + p, rect.top() + p + UIConstants.CARD_MARGIN_TOP, target_w - (p*2), target_h - (p*2) - UIConstants.CARD_MARGIN_TOP)

    def _is_keyboard_focused(self, index) -> bool:
        parent = self.parent()
        if not parent or not getattr(parent, "property", None):
            return False
        if not parent.property("keyboard_cursor_active"):
            return False
        if index is None or not index.isValid():
            return False
        
        # Use our custom persistent cursor property instead of currentIndex()
        current = parent.property("keyboard_cursor_index")
        return bool(current and isinstance(current, QModelIndex) and current == index)

    def draw_keyboard_focus_ring(self, painter: QPainter, content_rect: QRect, theme: dict):
        painter.save()
        # Thicker border for keyboard focus
        pen = QPen(QColor(theme["accent"]), UIConstants.CARD_BORDER_WIDTH_SELECTED + 2)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(pen)
        ring_rect = content_rect.adjusted(-1, -1, 1, 1)
        painter.drawRoundedRect(ring_rect, UIConstants.CARD_ROUNDING, UIConstants.CARD_ROUNDING)
        painter.restore()

    def draw_selection_badge(self, painter: QPainter, content_rect: QRect, theme: dict):
        painter.save()
        s = UIConstants.scale
        badge_size = s(20)
        badge_rect = QRect(
            content_rect.right() - badge_size - s(6),
            content_rect.top() + s(6),
            badge_size,
            badge_size,
        )
        
        # Use theme keys for everything
        on_accent = QColor(theme.get("text_on_accent", "#ffffff"))
        accent = QColor(theme["accent"])
        
        # Draw an outline around the badge to pop it off the blue focus ring if they overlap
        painter.setPen(QPen(on_accent, s(2)))
        painter.setBrush(accent)
        painter.drawEllipse(badge_rect)
        
        # Draw the checkmark
        painter.setPen(QPen(on_accent, max(1, s(2))))
        p1 = QPoint(int(badge_rect.left() + badge_size * 0.28), int(badge_rect.top() + badge_size * 0.55))
        p2 = QPoint(int(badge_rect.left() + badge_size * 0.46), int(badge_rect.top() + badge_size * 0.72))
        p3 = QPoint(int(badge_rect.left() + badge_size * 0.76), int(badge_rect.top() + badge_size * 0.34))
        painter.drawLine(p1, p2)
        painter.drawLine(p2, p3)
        painter.restore()

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

    def draw_folder_stack(self, painter: QPainter, rect: QRect, theme: dict, image_manager=None, label: str = None, icon_name: str = "folder", badge_icon_name: str = None, pixmap: QPixmap = None):
        """Draws the SVG folder stack icon or a custom thumbnail, with appropriate type indicators."""
        # 1. Inner Background
        painter.setBrush(QColor(theme['bg_sidebar']))
        painter.setPen(QColor(theme['border']))
        painter.drawRoundedRect(rect, UIConstants.CARD_ROUNDING, UIConstants.CARD_ROUNDING)

        # 2. Main Visual
        if pixmap and not pixmap.isNull():
            # CASE A: Rich Thumbnail available
            self.draw_cover_pixmap(painter, rect, pixmap)

            # Draw small folder type indicator in top-left
            s = UIConstants.scale
            badge_size = s(28)
            padding = s(4)
            badge_rect = QRect(rect.left() + padding, rect.top() + padding, badge_size, badge_size)

            bg_color = QColor(theme['bg_main'])
            bg_color.setAlpha(180)
            painter.setBrush(bg_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(badge_rect)
            
            icon = ThemeManager.get_icon("folder", "text_main")
            icon_padding = s(6)
            icon.paint(painter, badge_rect.adjusted(icon_padding, icon_padding, -icon_padding, -icon_padding))

            # Skip large icon and server badge logic
        else:
            # CASE B: No thumbnail (Standard Folder)
            s = UIConstants.scale
            margin = UIConstants.FOLDER_ICON_MARGIN
            if label and not self.show_labels:
                margin += s(15)

            folder_size = min(rect.width(), rect.height()) - margin
            color = theme.get("text_dim", theme.get("text_main", "#888888"))
            svg_path = ICON_DIR / f"{icon_name}.svg"            

            x = rect.left() + (rect.width() - folder_size) // 2
            y = rect.top() + (rect.height() - folder_size) // 2

            if label and not self.show_labels:
                y -= s(12)

            if svg_path.exists():
                from PyQt6.QtCore import QByteArray
                from PyQt6.QtSvg import QSvgRenderer
                svg_bytes = svg_path.read_bytes()
                svg_bytes = svg_bytes.replace(b'stroke="white"', f'stroke="{color}"'.encode())
                svg_bytes = svg_bytes.replace(b'fill="white"', f'fill="{color}"'.encode())

                renderer = QSvgRenderer(QByteArray(svg_bytes))
                f_rect = QRectF(x, y, folder_size, folder_size)

                painter.setOpacity(0.8)
                renderer.render(painter, f_rect)
                painter.setOpacity(1.0)

            # 3. Server Logo Badge (Only for Standard Folders)
            badge_size = UIConstants.FOLDER_BADGE_SIZE
            badge_x = rect.left() + (rect.width() - badge_size) / 2
            badge_y = rect.top() + (rect.height() - badge_size) / 2 + UIConstants.FOLDER_BADGE_OFFSET_Y

            if badge_icon_name:
                badge_svg_path = ICON_DIR / f"{badge_icon_name}.svg"
                if badge_svg_path.exists():
                    from PyQt6.QtCore import QByteArray
                    from PyQt6.QtSvg import QSvgRenderer
                    svg_bytes = badge_svg_path.read_bytes()
                    color = theme.get("text_dim", theme.get("text_main", "#888888"))
                    svg_bytes = svg_bytes.replace(b'stroke="white"', f'stroke="{color}"'.encode())
                    svg_bytes = svg_bytes.replace(b'fill="white"', f'fill="{color}"'.encode())

                    renderer = QSvgRenderer(QByteArray(svg_bytes))
                    b_rect = QRectF(badge_x, badge_y, badge_size, badge_size)

                    painter.setOpacity(0.6)
                    renderer.render(painter, b_rect)
                    painter.setOpacity(1.0)
            elif image_manager and getattr(image_manager, 'api_client', None):
                profile = getattr(image_manager.api_client, 'profile', None)
                cached_icon = getattr(profile, '_cached_icon', None) if profile else None

                if cached_icon and not cached_icon.isNull():
                    pw, ph = cached_icon.width(), cached_icon.height()
                    scale = min(badge_size / pw, badge_size / ph)
                    dw, dh = int(pw * scale), int(ph * scale)
                    dx = int(badge_x + (badge_size - dw) / 2)
                    dy = int(badge_y + (badge_size - dh) / 2)
                    painter.drawPixmap(dx, dy, dw, dh, cached_icon)
                else:
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
        """Draws the elided bold primary label, using a high-performance pixmap cache."""
        if not text or not self._show_labels:
            return

        theme_name = ThemeManager._current_theme
        is_selected = forced_text_color is not None # Usually selected when forced
        
        # 1. Check Cache
        cache_key = (text, secondary_text, self._card_size, theme_name, is_selected)
        if cache_key not in self._label_cache:
            from PyQt6.QtGui import QPixmap
            # Render labels into a transparent pixmap
            pm = QPixmap(rect.width(), rect.height())
            pm.fill(Qt.GlobalColor.transparent)
            pm_painter = QPainter(pm)
            pm_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            local_rect = QRect(0, 0, rect.width(), rect.height())
            
            # Primary Label Setup
            pm_painter.setPen(forced_text_color if forced_text_color else QColor(theme['text_main']))
            font = pm_painter.font()
            font.setPixelSize(UIConstants.FONT_SIZE_CARD_LABEL)
            font.setBold(False)
            pm_painter.setFont(font)
            metrics = pm_painter.fontMetrics()
            
            if secondary_text:
                # One line primary + one line secondary
                elided_primary = metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, rect.width())
                pm_painter.drawText(local_rect, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter, elided_primary)
                
                if forced_text_color:
                    sec_color = QColor(forced_text_color)
                    sec_color.setAlpha(180)
                    pm_painter.setPen(sec_color)
                else:
                    pm_painter.setPen(QColor(theme.get('text_dim', '#a0a0a0')))
                
                font.setBold(False)
                font.setPixelSize(UIConstants.FONT_SIZE_CARD_LABEL - 1)
                pm_painter.setFont(font)
                elided_secondary = metrics.elidedText(secondary_text, Qt.TextElideMode.ElideMiddle, rect.width())
                s = UIConstants.scale
                secondary_rect = local_rect.adjusted(0, metrics.height() + s(2), 0, 0)
                pm_painter.drawText(secondary_rect, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter, elided_secondary)
            else:
                # Two line primary
                line_height = metrics.lineSpacing()
                label_rect = QRect(0, 0, rect.width(), line_height * 2)
                elided_text = metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, int(rect.width() * 1.65))
                pm_painter.setClipRect(label_rect)
                pm_painter.drawText(label_rect, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap, elided_text)
                
            pm_painter.end()
            
            # Limit cache size to prevent memory creep (e.g. 500 items)
            if len(self._label_cache) > 500:
                self._label_cache.clear()
            self._label_cache[cache_key] = pm

        # 2. Paint the cached pixmap
        painter.drawPixmap(rect.left(), rect.top(), self._label_cache[cache_key])

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
