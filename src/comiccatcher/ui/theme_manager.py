import os
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QColor, QPalette, QIcon

ICON_DIR = Path(__file__).parent.parent / "resources" / "icons"

THEMES = {
    "light": {
        "bg_main": "#f5f6f8",
        "bg_sidebar": "#e8ecf0",
        "bg_header": "#ffffff",
        "bg_item_hover": "#dde3ea",
        "bg_item_selected": "#c8ddf8",
        "text_main": "#1a1d21",
        "text_dim": "#5a6270",
        "text_selected": "#004bb0",
        "text_on_accent": "#ffffff",
        "accent": "#004bb0",
        "accent_dim": "rgba(0, 75, 176, 40)",
        "border": "#c8cdd4",
        "card_bg": "#ffffff",
        "card_border": "#d1d5db",
        "white": "#ffffff",
        "danger": "#dc3545",
        "success": "#28a745",
        "bg_reader": "#ffffff",
        "text_reader": "#1a1d21"
    },
    "dark": {
        "bg_main": "#1e1e1e",
        "bg_sidebar": "#2d2d2d",
        "bg_header": "#252526",
        "bg_item_hover": "#3e3e42",
        "bg_item_selected": "#264f78",
        "text_main": "#e1e1e1",
        "text_dim": "#a0a0a0",
        "text_selected": "#ffffff",
        "text_on_accent": "#ffffff",
        "accent": "#007fd4",
        "accent_dim": "rgba(0, 127, 212, 40)",
        "border": "#333333",
        "card_bg": "#252526",
        "card_border": "#3f3f46",
        "white": "#ffffff",
        "danger": "#f44336",
        "success": "#4caf50",
        "bg_reader": "#2d2d2d",
        "text_reader": "#e1e1e1"
    },
    "oled": {
        "bg_main": "#000000",
        "bg_sidebar": "#000000",
        "bg_header": "#000000",
        "bg_item_hover": "#1a1a1a",
        "bg_item_selected": "#007fd4",
        "text_main": "#ffffff",
        "text_dim": "#bbbbbb",
        "text_selected": "#ffffff",
        "text_on_accent": "#ffffff",
        "accent": "#007fd4",
        "accent_dim": "rgba(0, 127, 212, 60)",
        "border": "#404040",
        "card_bg": "#000000",
        "card_border": "#333333",
        "white": "#ffffff",
        "danger": "#f44336",
        "success": "#4caf50",
        "bg_reader": "#000000",
        "text_reader": "#ffffff"
    },
    "blue": {
        "bg_main": "#0f172a",
        "bg_sidebar": "#1e293b",
        "bg_header": "#1e293b",
        "bg_item_hover": "#334155",
        "bg_item_selected": "#0ea5e9",
        "text_main": "#f1f5f9",
        "text_dim": "#94a3b8",
        "text_selected": "#ffffff",
        "text_on_accent": "#0f172a",
        "accent": "#0ea5e9",
        "accent_dim": "rgba(14, 165, 233, 40)",
        "border": "#334155",
        "card_bg": "#1e293b",
        "card_border": "#334155",
        "white": "#ffffff",
        "danger": "#ef4444",
        "success": "#10b981",
        "bg_reader": "#1e293b",
        "text_reader": "#f1f5f9"
    },
    "light_blue": {
        "bg_main": "#f0f7ff",
        "bg_sidebar": "#e1effe",
        "bg_header": "#ffffff",
        "bg_item_hover": "#d1e9ff",
        "bg_item_selected": "#bfdbfe",
        "text_main": "#1e3a8a",
        "text_dim": "#3b82f6",
        "text_selected": "#1e3a8a",
        "text_on_accent": "#ffffff",
        "accent": "#1d4ed8",
        "accent_dim": "rgba(29, 78, 216, 40)",
        "border": "#bfdbfe",
        "card_bg": "#ffffff",
        "card_border": "#bfdbfe",
        "white": "#ffffff",
        "danger": "#dc3545",
        "success": "#16a34a",
        "bg_reader": "#ffffff",
        "text_reader": "#1e3a8a"
    }
}

class UIConstants:
    """Centralized design tokens for consistent UI across all views."""
    _scale_factor = 1.0

    # --- 1. Base Design Tokens (Unscaled) ---
    # These are the "Source of Truth". Change them here to update the whole UI.
    _BASE_HEADER_HEIGHT = 50
    _BASE_STATUS_HEIGHT = 2
    
    _BASE_FONT_SIZE_SECTION_HEADER = 14
    _BASE_FONT_SIZE_DEFAULT = 13
    _BASE_FONT_SIZE_CARD_LABEL = 13
    _BASE_FONT_SIZE_STATUS = 11
    _BASE_FONT_SIZE_BOTTOM_BAR = 11
    _BASE_FONT_SIZE_DEBUG = 10
    _BASE_FONT_SIZE_DETAIL_TITLE = 24
    _BASE_FONT_SIZE_DETAIL_SUBTITLE = 18
    _BASE_FONT_SIZE_BADGE = 11
    _BASE_FONT_SIZE_PAGING = 14
    _BASE_FONT_SIZE_DETAIL_INFO = 14
    _BASE_FONT_SIZE_SEARCH_TITLE = 28
    _BASE_FONT_SIZE_SEARCH_INPUT = 16
    _BASE_FONT_SIZE_BREADCRUMB = 13
    _BASE_FONT_SIZE_SIDEBAR = 12
    _BASE_FONT_SIZE_FEED_LIST = 14
    _BASE_FONT_SIZE_FEED_NAME_LARGE = 18
    _BASE_FONT_SIZE_FEED_URL_LARGE = 14
    _BASE_FEED_ICON_SIZE_LARGE = 48
    _BASE_FONT_SIZE_FEED_NAME_SMALL = 16
    _BASE_FONT_SIZE_FEED_URL_SMALL = 12
    _BASE_FEED_ICON_SIZE_SMALL = 32
    
    _BASE_SIDEBAR_WIDTH = 85
    _BASE_NAV_ICON_SIZE = 32
    _BASE_DETAIL_META_WIDTH = 100
    
    _BASE_SEARCH_ITEM_HEIGHT = 40
    
    _BASE_READER_BTN_SIZE = 36
    _BASE_READER_ICON_SIZE = 20
    _BASE_READER_FONT_COUNTER = 16
    
    _BASE_CARD_WIDTH = 150
    _BASE_CARD_HEIGHT = 250
    _BASE_CARD_SPACING = 10
    _BASE_CARD_LABEL_HEIGHT = 55
    _BASE_CARD_COVER_HEIGHT = 180
    _BASE_CARD_PADDING = 5
    _BASE_CARD_MARGIN_TOP = 2
    _BASE_CARD_ROUNDING = 5
    _BASE_CARD_BORDER_WIDTH = 1
    _BASE_CARD_BORDER_WIDTH_SELECTED = 2
    
    _BASE_FOLDER_ICON_MARGIN = 10
    _BASE_FOLDER_BADGE_SIZE = 32
    _BASE_FOLDER_BADGE_OFFSET_Y = 4
    
    _BASE_PROGRESS_BAR_HEIGHT = 4
    _BASE_PROGRESS_BAR_TOTAL_HEIGHT = 10
    _BASE_PROGRESS_BAR_MARGIN_H = 10
    _BASE_PROGRESS_BAR_OFFSET_Y = 6
    _BASE_PROGRESS_BAR_GAP = 2
    
    _BASE_GRID_GUTTER = 10
    _BASE_RIBBON_LABEL_GAP = 25
    _BASE_RIBBON_SCROLLBAR_GUTTER = 8
    _BASE_LARGE_SECTION_THRESHOLD = 200
    _BASE_VIEWPORT_MARGIN = 20
    
    _BASE_SKELETON_PADDING = 10
    _BASE_SKELETON_ROUNDING = 3
    
    _BASE_SECTION_SPACING = 2
    _BASE_SECTION_MARGIN_BOTTOM = 0
    _BASE_SECTION_HEADER_SPACING = 5
    _BASE_SECTION_HEADER_MARGIN_TOP = 2
    _BASE_SECTION_HEADER_HEIGHT = 30
    _BASE_GRID_SPACING = 10
    _BASE_TOOLBAR_GAP = 12
    _BASE_TOGGLE_BUTTON_SIZE = 24
    _BASE_HEADER_BUTTON_SIZE = 32
    
    _BASE_ICON_SIZE_STANDARD = 18
    _BASE_ICON_SIZE_ACTION = 20
    _BASE_ICON_SIZE_SMALL = 16
    
    _BASE_LAYOUT_MARGIN_DEFAULT = 10
    _BASE_LAYOUT_MARGIN_LARGE = 20
    _BASE_DETAIL_MAX_WIDTH = 750
    
    _BASE_POPOVER_OFFSET = 10
    _BASE_POPOVER_ROUNDING = 8

    # --- 2. Live Attributes (Auto-initialized to base values) ---
    HEADER_HEIGHT = _BASE_HEADER_HEIGHT
    STATUS_HEIGHT = _BASE_STATUS_HEIGHT
    FONT_SIZE_SECTION_HEADER = _BASE_FONT_SIZE_SECTION_HEADER
    FONT_SIZE_DEFAULT = _BASE_FONT_SIZE_DEFAULT
    FONT_SIZE_CARD_LABEL = _BASE_FONT_SIZE_CARD_LABEL
    FONT_SIZE_STATUS = _BASE_FONT_SIZE_STATUS
    FONT_SIZE_BOTTOM_BAR = _BASE_FONT_SIZE_BOTTOM_BAR
    FONT_SIZE_DEBUG = _BASE_FONT_SIZE_DEBUG
    FONT_SIZE_DETAIL_TITLE = _BASE_FONT_SIZE_DETAIL_TITLE
    FONT_SIZE_DETAIL_SUBTITLE = _BASE_FONT_SIZE_DETAIL_SUBTITLE
    FONT_SIZE_BADGE = _BASE_FONT_SIZE_BADGE
    FONT_SIZE_PAGING = _BASE_FONT_SIZE_PAGING
    FONT_SIZE_DETAIL_INFO = _BASE_FONT_SIZE_DETAIL_INFO
    FONT_SIZE_SEARCH_TITLE = _BASE_FONT_SIZE_SEARCH_TITLE
    FONT_SIZE_SEARCH_INPUT = _BASE_FONT_SIZE_SEARCH_INPUT
    FONT_SIZE_BREADCRUMB = _BASE_FONT_SIZE_BREADCRUMB
    FONT_SIZE_SIDEBAR = _BASE_FONT_SIZE_SIDEBAR
    FONT_SIZE_FEED_LIST = _BASE_FONT_SIZE_FEED_LIST
    FONT_SIZE_FEED_NAME_LARGE = _BASE_FONT_SIZE_FEED_NAME_LARGE
    FONT_SIZE_FEED_URL_LARGE = _BASE_FONT_SIZE_FEED_URL_LARGE
    FEED_ICON_SIZE_LARGE = _BASE_FEED_ICON_SIZE_LARGE
    FONT_SIZE_FEED_NAME_SMALL = _BASE_FONT_SIZE_FEED_NAME_SMALL
    FONT_SIZE_FEED_URL_SMALL = _BASE_FONT_SIZE_FEED_URL_SMALL
    FEED_ICON_SIZE_SMALL = _BASE_FEED_ICON_SIZE_SMALL
    
    SIDEBAR_WIDTH = _BASE_SIDEBAR_WIDTH
    NAV_ICON_SIZE = _BASE_NAV_ICON_SIZE
    DETAIL_META_WIDTH = _BASE_DETAIL_META_WIDTH
    SEARCH_ITEM_HEIGHT = _BASE_SEARCH_ITEM_HEIGHT
    
    CARD_WIDTH = _BASE_CARD_WIDTH
    CARD_HEIGHT = _BASE_CARD_HEIGHT
    CARD_SPACING = _BASE_CARD_SPACING
    CARD_LABEL_HEIGHT = _BASE_CARD_LABEL_HEIGHT
    CARD_COVER_HEIGHT = _BASE_CARD_COVER_HEIGHT
    CARD_PADDING = _BASE_CARD_PADDING
    CARD_MARGIN_TOP = _BASE_CARD_MARGIN_TOP
    CARD_ROUNDING = _BASE_CARD_ROUNDING
    CARD_BORDER_WIDTH = _BASE_CARD_BORDER_WIDTH
    CARD_BORDER_WIDTH_SELECTED = _BASE_CARD_BORDER_WIDTH_SELECTED
    FOLDER_ICON_MARGIN = _BASE_FOLDER_ICON_MARGIN
    FOLDER_BADGE_SIZE = _BASE_FOLDER_BADGE_SIZE
    FOLDER_BADGE_OFFSET_Y = _BASE_FOLDER_BADGE_OFFSET_Y
    PROGRESS_BAR_HEIGHT = _BASE_PROGRESS_BAR_HEIGHT
    PROGRESS_BAR_TOTAL_HEIGHT = _BASE_PROGRESS_BAR_TOTAL_HEIGHT
    PROGRESS_BAR_MARGIN_H = _BASE_PROGRESS_BAR_MARGIN_H
    PROGRESS_BAR_OFFSET_Y = _BASE_PROGRESS_BAR_OFFSET_Y
    PROGRESS_BAR_GAP = _BASE_PROGRESS_BAR_GAP
    GRID_GUTTER = _BASE_GRID_GUTTER
    RIBBON_LABEL_GAP = _BASE_RIBBON_LABEL_GAP
    RIBBON_SCROLLBAR_GUTTER = _BASE_RIBBON_SCROLLBAR_GUTTER
    LARGE_SECTION_THRESHOLD = _BASE_LARGE_SECTION_THRESHOLD
    VIEWPORT_MARGIN = _BASE_VIEWPORT_MARGIN
    SKELETON_PADDING = _BASE_SKELETON_PADDING
    SKELETON_ROUNDING = _BASE_SKELETON_ROUNDING
    SECTION_SPACING = _BASE_SECTION_SPACING
    SECTION_MARGIN_BOTTOM = _BASE_SECTION_MARGIN_BOTTOM
    SECTION_HEADER_SPACING = _BASE_SECTION_HEADER_SPACING
    SECTION_HEADER_MARGIN_TOP = _BASE_SECTION_HEADER_MARGIN_TOP
    SECTION_HEADER_HEIGHT = _BASE_SECTION_HEADER_HEIGHT
    GRID_SPACING = _BASE_GRID_SPACING
    TOOLBAR_GAP = _BASE_TOOLBAR_GAP
    TOGGLE_BUTTON_SIZE = _BASE_TOGGLE_BUTTON_SIZE
    HEADER_BUTTON_SIZE = _BASE_HEADER_BUTTON_SIZE
    
    ICON_SIZE_STANDARD = _BASE_ICON_SIZE_STANDARD
    ICON_SIZE_ACTION = _BASE_ICON_SIZE_ACTION
    ICON_SIZE_SMALL = _BASE_ICON_SIZE_SMALL
    
    LAYOUT_MARGIN_DEFAULT = _BASE_LAYOUT_MARGIN_DEFAULT
    LAYOUT_MARGIN_LARGE = _BASE_LAYOUT_MARGIN_LARGE
    DETAIL_MAX_WIDTH = _BASE_DETAIL_MAX_WIDTH
    POPOVER_OFFSET = _BASE_POPOVER_OFFSET
    POPOVER_ROUNDING = _BASE_POPOVER_ROUNDING

    # Non-scaled logic constants
    ELIDED_TEXT_WIDTH_FACTOR = 1.7
    DEFAULT_PAGING_STRIDE = 50
    SPARSE_FETCH_BUFFER = 1
    MAX_CONCURRENT_FETCHES = 1
    SCROLL_DEBOUNCE_MS = 300
    STATUS_UPDATE_MS = 50
    RESIZE_DEBOUNCE_MS = 200
    DEBUG_OUTLINES = False

    @classmethod
    def get_card_height(cls, show_labels: bool, reserve_progress_space: bool = True) -> int:
        """Returns the total vertical height of a card based on visibility of labels and progress bar space."""
        p = cls.CARD_PADDING
        
        # 1. Shell Overhead: Top Margin + Top/Bottom Selection Insets
        # draw_card_background consumes MarginTop + 2*p
        height = cls.CARD_MARGIN_TOP + (p * 2)
        
        # 2. Internal Box Padding: Top and Bottom padding inside the rounded card
        height += (p * 2)
        
        # 3. Content: The Cover image
        height += cls.CARD_COVER_HEIGHT
        
        # 4. Optional: Progress Bar Area + Gap
        if reserve_progress_space:
            # We use PROGRESS_BAR_GAP (2px) and the total bar area (10px)
            height += cls.PROGRESS_BAR_GAP + cls.PROGRESS_BAR_TOTAL_HEIGHT
            
        # 5. Optional: Label Area + Gap
        if show_labels:
            # We use standard CARD_PADDING (5px) as the gap before labels
            height += p + cls.CARD_LABEL_HEIGHT
            
        return height

    @classmethod
    def scale(cls, val: int) -> int:
        return max(1, int(val * cls._scale_factor)) if val > 0 else 0

    @classmethod
    @property
    def BOTTOM_BAR_HEIGHT(cls) -> int:
        from PyQt6.QtGui import QFont, QFontMetrics
        font = QFont()
        font.setPixelSize(cls.FONT_SIZE_BOTTOM_BAR)
        metrics = QFontMetrics(font)
        # Line spacing + 8px total vertical padding (scaled)
        return metrics.lineSpacing() + cls.scale(8)

    @classmethod
    def set_scale(cls, factor: float):
        cls._scale_factor = max(0.5, min(3.0, factor))
        cls.init_scale()

    @classmethod
    def init_scale(cls, manual_factor: float = None):
        if manual_factor is not None:
            cls._scale_factor = manual_factor
        # Only fetch screen DPI if _scale_factor is still at default 1.0
        elif cls._scale_factor == 1.0:
            app = QApplication.instance()
            if app:
                screen = app.primaryScreen()
                if screen:
                    cls._scale_factor = screen.logicalDotsPerInch() / 96.0

        # Update all dynamic attributes from base values
        cls.HEADER_HEIGHT = cls.scale(cls._BASE_HEADER_HEIGHT)
        cls.STATUS_HEIGHT = cls.scale(cls._BASE_STATUS_HEIGHT)
        
        cls.FONT_SIZE_SECTION_HEADER = cls.scale(cls._BASE_FONT_SIZE_SECTION_HEADER)
        cls.FONT_SIZE_DEFAULT = cls.scale(cls._BASE_FONT_SIZE_DEFAULT)
        cls.FONT_SIZE_CARD_LABEL = cls.scale(cls._BASE_FONT_SIZE_CARD_LABEL)
        cls.FONT_SIZE_STATUS = cls.scale(cls._BASE_FONT_SIZE_STATUS)
        cls.FONT_SIZE_BOTTOM_BAR = cls.scale(cls._BASE_FONT_SIZE_BOTTOM_BAR)
        cls.FONT_SIZE_DEBUG = cls.scale(cls._BASE_FONT_SIZE_DEBUG)
        cls.FONT_SIZE_DETAIL_TITLE = cls.scale(cls._BASE_FONT_SIZE_DETAIL_TITLE)
        cls.FONT_SIZE_DETAIL_SUBTITLE = cls.scale(cls._BASE_FONT_SIZE_DETAIL_SUBTITLE)
        cls.FONT_SIZE_BADGE = cls.scale(cls._BASE_FONT_SIZE_BADGE)
        cls.FONT_SIZE_PAGING = cls.scale(cls._BASE_FONT_SIZE_PAGING)
        cls.FONT_SIZE_DETAIL_INFO = cls.scale(cls._BASE_FONT_SIZE_DETAIL_INFO)
        cls.FONT_SIZE_SEARCH_TITLE = cls.scale(cls._BASE_FONT_SIZE_SEARCH_TITLE)
        cls.FONT_SIZE_SEARCH_INPUT = cls.scale(cls._BASE_FONT_SIZE_SEARCH_INPUT)
        cls.FONT_SIZE_BREADCRUMB = cls.scale(cls._BASE_FONT_SIZE_BREADCRUMB)
        cls.FONT_SIZE_SIDEBAR = cls.scale(cls._BASE_FONT_SIZE_SIDEBAR)
        cls.FONT_SIZE_FEED_LIST = cls.scale(cls._BASE_FONT_SIZE_FEED_LIST)
        cls.FONT_SIZE_FEED_NAME_LARGE = cls.scale(cls._BASE_FONT_SIZE_FEED_NAME_LARGE)
        cls.FONT_SIZE_FEED_URL_LARGE = cls.scale(cls._BASE_FONT_SIZE_FEED_URL_LARGE)
        cls.FEED_ICON_SIZE_LARGE = cls.scale(cls._BASE_FEED_ICON_SIZE_LARGE)
        cls.FONT_SIZE_FEED_NAME_SMALL = cls.scale(cls._BASE_FONT_SIZE_FEED_NAME_SMALL)
        cls.FONT_SIZE_FEED_URL_SMALL = cls.scale(cls._BASE_FONT_SIZE_FEED_URL_SMALL)
        cls.FEED_ICON_SIZE_SMALL = cls.scale(cls._BASE_FEED_ICON_SIZE_SMALL)

        cls.SIDEBAR_WIDTH = cls.scale(cls._BASE_SIDEBAR_WIDTH)
        cls.NAV_ICON_SIZE = cls.scale(cls._BASE_NAV_ICON_SIZE)
        cls.DETAIL_META_WIDTH = cls.scale(cls._BASE_DETAIL_META_WIDTH)
        cls.SEARCH_ITEM_HEIGHT = cls.scale(cls._BASE_SEARCH_ITEM_HEIGHT)
        cls.READER_BTN_SIZE = cls.scale(cls._BASE_READER_BTN_SIZE)
        cls.READER_ICON_SIZE = cls.scale(cls._BASE_READER_ICON_SIZE)
        cls.READER_FONT_COUNTER = cls.scale(cls._BASE_READER_FONT_COUNTER)

        cls.ICON_SIZE_STANDARD = cls.scale(cls._BASE_ICON_SIZE_STANDARD)
        cls.ICON_SIZE_ACTION = cls.scale(cls._BASE_ICON_SIZE_ACTION)
        cls.ICON_SIZE_SMALL = cls.scale(cls._BASE_ICON_SIZE_SMALL)
        
        # 1. Start with fundamental card metrics
        cls.CARD_WIDTH = cls.scale(cls._BASE_CARD_WIDTH)
        cls.CARD_COVER_HEIGHT = cls.scale(cls._BASE_CARD_COVER_HEIGHT)
        cls.CARD_PADDING = cls.scale(cls._BASE_CARD_PADDING)
        cls.CARD_MARGIN_TOP = cls.scale(cls._BASE_CARD_MARGIN_TOP)
        cls.CARD_ROUNDING = cls.scale(cls._BASE_CARD_ROUNDING)
        cls.CARD_BORDER_WIDTH = max(1, cls.scale(cls._BASE_CARD_BORDER_WIDTH))
        cls.CARD_BORDER_WIDTH_SELECTED = max(1, cls.scale(cls._BASE_CARD_BORDER_WIDTH_SELECTED))
        
        cls.FOLDER_ICON_MARGIN = cls.scale(cls._BASE_FOLDER_ICON_MARGIN)
        cls.FOLDER_BADGE_SIZE = cls.scale(cls._BASE_FOLDER_BADGE_SIZE)
        cls.FOLDER_BADGE_OFFSET_Y = cls.scale(cls._BASE_FOLDER_BADGE_OFFSET_Y)

        # 2. Dynamically calculate label height based on font metrics (2 rows)
        app = QApplication.instance()
        if app:
            from PyQt6.QtGui import QFont, QFontMetrics
            font = QFont()
            font.setPixelSize(cls.FONT_SIZE_CARD_LABEL)
            metrics = QFontMetrics(font)
            # lineSpacing() * 2 gives us room for exactly two rows of text.
            # Add a small buffer for descenders/accents.
            cls.CARD_LABEL_HEIGHT = (metrics.lineSpacing() * 2) + cls.scale(4)
        else:
            # Fallback if no app instance
            cls.CARD_LABEL_HEIGHT = cls.scale(cls._BASE_CARD_LABEL_HEIGHT)

        cls.PROGRESS_BAR_HEIGHT = cls.scale(cls._BASE_PROGRESS_BAR_HEIGHT)
        cls.PROGRESS_BAR_TOTAL_HEIGHT = cls.scale(cls._BASE_PROGRESS_BAR_TOTAL_HEIGHT)
        cls.PROGRESS_BAR_MARGIN_H = cls.scale(cls._BASE_PROGRESS_BAR_MARGIN_H)
        cls.PROGRESS_BAR_OFFSET_Y = cls.scale(cls._BASE_PROGRESS_BAR_OFFSET_Y)
        cls.PROGRESS_BAR_GAP = cls.scale(cls._BASE_PROGRESS_BAR_GAP)
        
        # 3. Calculate "Perfect" Card Height
        # Total = Top Margin + Padding + Cover + Gap + Progress Bar Area + Padding + Label Area + Bottom Padding
        # This matches the logic in get_card_height(show_labels=True)
        cls.CARD_HEIGHT = (cls.CARD_MARGIN_TOP + 
                          cls.CARD_COVER_HEIGHT + 
                          cls.PROGRESS_BAR_TOTAL_HEIGHT + 
                          cls.CARD_LABEL_HEIGHT + 
                          (cls.CARD_PADDING * 5) +
                          cls.PROGRESS_BAR_GAP)
        
        cls.GRID_GUTTER = cls.scale(cls._BASE_GRID_GUTTER)
        cls.RIBBON_LABEL_GAP = cls.scale(cls._BASE_RIBBON_LABEL_GAP)
        cls.RIBBON_SCROLLBAR_GUTTER = cls.scale(cls._BASE_RIBBON_SCROLLBAR_GUTTER)
        cls.LARGE_SECTION_THRESHOLD = cls._BASE_LARGE_SECTION_THRESHOLD
        cls.VIEWPORT_MARGIN = cls.scale(cls._BASE_VIEWPORT_MARGIN)
        
        cls.SKELETON_PADDING = cls.scale(cls._BASE_SKELETON_PADDING)
        cls.SKELETON_ROUNDING = cls.scale(cls._BASE_SKELETON_ROUNDING)
        
        cls.SECTION_SPACING = cls.scale(cls._BASE_SECTION_SPACING)
        cls.SECTION_MARGIN_BOTTOM = cls.scale(cls._BASE_SECTION_MARGIN_BOTTOM)
        cls.SECTION_HEADER_SPACING = cls.scale(cls._BASE_SECTION_HEADER_SPACING)
        cls.SECTION_HEADER_MARGIN_TOP = cls.scale(cls._BASE_SECTION_HEADER_MARGIN_TOP)
        cls.SECTION_HEADER_HEIGHT = cls.scale(cls._BASE_SECTION_HEADER_HEIGHT)
        cls.GRID_SPACING = cls.scale(cls._BASE_GRID_SPACING)
        cls.TOOLBAR_GAP = cls.scale(cls._BASE_TOOLBAR_GAP)
        cls.TOGGLE_BUTTON_SIZE = cls.scale(cls._BASE_TOGGLE_BUTTON_SIZE)
        cls.HEADER_BUTTON_SIZE = cls.scale(cls._BASE_HEADER_BUTTON_SIZE)
        cls.LAYOUT_MARGIN_DEFAULT = cls.scale(cls._BASE_LAYOUT_MARGIN_DEFAULT)
        cls.LAYOUT_MARGIN_LARGE = cls.scale(cls._BASE_LAYOUT_MARGIN_LARGE)
        cls.DETAIL_MAX_WIDTH = cls.scale(cls._BASE_DETAIL_MAX_WIDTH)
        
        cls.POPOVER_OFFSET = cls.scale(cls._BASE_POPOVER_OFFSET)
        cls.POPOVER_ROUNDING = cls.scale(cls._BASE_POPOVER_ROUNDING)

        # Dynamic scrollbar calculation
        if app:
            from PyQt6.QtWidgets import QStyle
            cls.SCROLLBAR_SIZE = app.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent)
        else:
            cls.SCROLLBAR_SIZE = cls.scale(12)

class ThemeManager:
    _current_theme: str = "dark"
    _icon_cache: dict = {}

    @classmethod
    def get_current_theme_colors(cls) -> dict:
        return THEMES.get(cls._current_theme, THEMES["dark"])

    @classmethod
    def get_icon(cls, name: str, color_key: str = "text_main") -> QIcon:
        """
        Returns a state-aware QIcon that handles different colors for 
        Normal, Disabled, and Selected/Checked states.
        """
        cache_key = (name, color_key, cls._current_theme)
        if cache_key in cls._icon_cache:
            return cls._icon_cache[cache_key]

        # logger.debug(f"ThemeManager: get_icon('{name}', '{color_key}')")
        path = ICON_DIR / f"{name}.svg"
        if not path.exists():
            return QIcon()
            
        theme = THEMES.get(cls._current_theme, THEMES["dark"])
        
        def generate_pixmap(target_color):
            try:
                from PyQt6.QtCore import QByteArray, Qt
                from PyQt6.QtGui import QPixmap, QPainter
                from PyQt6.QtSvg import QSvgRenderer
                import re
                
                # logger.debug(f"ThemeManager: generate_pixmap for {name} with color {target_color}")
                svg_text = path.read_text(encoding='utf-8')
                
                def color_replacer(match):
                    attr = match.group(1)
                    val = match.group(2)
                    if val.lower() == 'none':
                        return match.group(0)
                    return f'{attr}="{target_color}"'

                svg_text = re.sub(r'(stroke|fill)="([^"]+)"', color_replacer, svg_text)
                
                renderer = QSvgRenderer(QByteArray(svg_text.encode('utf-8')))
                if not renderer.isValid():
                    return None
                    
                size = UIConstants.scale(64)
                pixmap = QPixmap(size, size)
                pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pixmap)
                renderer.render(painter)
                painter.end()
                return pixmap
            except Exception:
                return None

        # 1. Normal State
        main_color = theme.get(color_key, theme["text_main"])
        pm_normal = generate_pixmap(main_color)
        if pm_normal is None:
            return QIcon(str(path))
            
        icon = QIcon(pm_normal)
        
        # 2. Disabled State (Use dim color)
        pm_disabled = generate_pixmap(theme["text_dim"])
        if pm_disabled:
            icon.addPixmap(pm_disabled, QIcon.Mode.Disabled, QIcon.State.Off)
            
        # 3. Selected/Checked State
        # In dark themes, white icons look great on accent backgrounds.
        # In light themes, 'bg_item_selected' is light, so white icons have no contrast.
        # We use 'text_selected' (often the accent color itself) for light themes.
        selected_color = theme["white"]
        if cls._current_theme in ["light", "light_blue"]:
            selected_color = theme.get("text_selected", theme["accent"])
            
        pm_selected = generate_pixmap(selected_color)
        if pm_selected:
            icon.addPixmap(pm_selected, QIcon.Mode.Selected, QIcon.State.On)
            # In Qt, 'Selected' often maps to the 'Checked' state in stylesheets
            icon.addPixmap(pm_selected, QIcon.Mode.Normal, QIcon.State.On)
            
        cls._icon_cache[cache_key] = icon
        return icon

    @classmethod
    def apply_theme(cls, app: QApplication, theme_name: str):
        UIConstants.init_scale()
        s = UIConstants.scale
        
        cls._current_theme = theme_name
        cls._icon_cache.clear()
        theme = THEMES.get(theme_name, THEMES["dark"])
        
        stylesheet = f"""
            QMainWindow, QDialog {{
                background-color: {theme['bg_main']};
                color: {theme['text_main']};
            }}
            
            QFormLayout {{
                background-color: transparent;
            }}
            
            /* Broad text settings */
            QWidget {{
                font-size: {UIConstants.FONT_SIZE_DEFAULT}px;
            }}

            QLabel, QRadioButton, QCheckBox {{
                color: {theme['text_main']};
                background-color: transparent;
            }}

            QGroupBox {{
                color: {theme['text_main']};
                border: {max(1, s(1))}px solid {theme['border']};
                border-radius: {s(6)}px;
                margin-top: {s(12)}px;
                background-color: {theme['bg_main']};
            }}
            
            QHeaderView::section {{
                background-color: {theme['bg_header']};
                color: {theme['text_dim']};
                padding: {s(4)}px;
                border: none;
                border-bottom: {max(1, s(1))}px solid {theme['border']};
            }}
            
            QListView, QTreeView, QListWidget, QScrollArea, QScrollArea > QWidget > QWidget {{
                background-color: {theme['bg_main']};
                border: none;
                outline: none;
            }}
            
            QScrollArea {{
                background-color: {theme['bg_main']};
            }}
            
            QListView::item {{
                padding: 0px;
                border-radius: {s(4)}px;
            }}

            QListView::item:hover {{
                background-color: {theme['bg_item_hover']};
            }}
            
            QListWidget::item:selected {{
                background-color: {theme['bg_item_selected']};
                color: {theme['text_selected']};
            }}
            
            QPushButton {{
                background-color: {theme['bg_main']};
                color: {theme['text_main']};
                border: {max(1, s(1))}px solid {theme['border']};
                padding: {s(6)}px {s(12)}px;
                border-radius: {s(4)}px;
            }}

            QPushButton:hover {{
                background-color: {theme['bg_item_hover']};
                border-color: {theme['accent']};
            }}

            QPushButton:pressed, QPushButton:checked {{
                background-color: {theme['accent']};
                color: {theme['white']};
                border-color: {theme['accent']};
            }}

            QPushButton:disabled {{
                background-color: transparent;
                color: {theme['text_dim']};
                border-color: {theme['border']};
            }}

            /* SEGMENTED CONTROL GROUPS - Forced Shared Outline */
            QPushButton[segment] {{
                background-color: {theme['bg_header']};
                color: {theme['text_main']};
                border: {max(1, s(1))}px solid {theme['border']};
                padding: {s(4)}px {s(8)}px;
                margin: 0px;
                border-radius: 0px;
            }}
            
            QPushButton[segment="single"] {{
                border-radius: {s(6)}px;
            }}
            
            QPushButton[segment="left"] {{
                border-top-left-radius: {s(6)}px;
                border-bottom-left-radius: {s(6)}px;
            }}
            
            QPushButton[segment="mid"] {{
                margin-left: -{max(1, s(1))}px;
            }}
            
            QPushButton[segment="right"] {{
                border-top-right-radius: {s(6)}px;
                border-bottom-right-radius: {s(6)}px;
                margin-left: -{max(1, s(1))}px;
            }}
            
            QPushButton[segment]:hover {{
                background-color: {theme['bg_item_hover']};
                border-color: {theme['accent']};
            }}
            
            QPushButton[segment]:checked {{
                background-color: {theme['bg_item_selected']};
                color: {theme['accent']};
                border: {max(1, s(1))}px solid {theme['accent']};
            }}
            QPushButton#flat_button, QPushButton#icon_button, QPushButton[flat="true"] {{
                background-color: transparent;
                border: none;
                padding: {s(4)}px;
                border-radius: {s(4)}px;
            }}

            QPushButton#flat_button:hover, QPushButton#icon_button:hover, QPushButton[flat="true"]:hover {{
                background-color: {theme['bg_item_hover']};
            }}

            QPushButton#flat_button:pressed, QPushButton#icon_button:pressed, QPushButton[flat="true"]:pressed {{
                background-color: {theme['accent_dim']};
                border: {max(1, s(1))}px solid {theme['accent']};
            }}
            
            /* Ensure flat buttons when checked (like toggles) are visible */
            QPushButton#flat_button:checked, QPushButton#icon_button:checked, QPushButton[flat="true"]:checked {{
                background-color: {theme['accent_dim']};
                border: {max(1, s(1))}px solid {theme['accent']};
            }}

            QPushButton#link_button {{
                color: {theme['accent']};
                font-size: {s(13)}px;
                text-align: left;
                background: transparent;
                border: none;
                padding: 0;
            }}

            QPushButton#link_button:hover {{
                text-decoration: underline;
                color: {theme['text_main']};
            }}
            
            QPushButton#reader_button {{
                background-color: {theme['bg_reader']};
                color: {theme['text_reader']};
                border: {max(1, s(1))}px solid {theme['border']};
                border-radius: {s(4)}px;
                padding: {s(4)}px;
            }}

            QPushButton#reader_button:hover {{
                background-color: {theme['bg_item_hover']};
            }}

            QPushButton#reader_button:pressed {{
                background-color: {theme['accent']};
                color: {theme['text_on_accent']};
            }}

            QPushButton#reader_button:disabled {{
                color: {theme['text_dim']};
                background-color: transparent;
            }}



            QPushButton::menu-indicator {{
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                bottom: {s(2)}px;
                right: {s(2)}px;
                width: {s(6)}px;
                height: {s(6)}px;
            }}
            
            QPushButton[flat="true"] {{
                background-color: transparent;
                border: none;
                padding: 0;
            }}

            QPushButton#tab_button {{
                background-color: transparent;
                color: {theme['text_dim']};
                border: none;
                border-bottom: {max(1, s(2))}px solid transparent;
                border-radius: 0px;
                padding: {s(6)}px {s(15)}px;
                font-size: {s(13)}px;
            }}

            QPushButton#tab_button:hover {{
                background-color: {theme['bg_item_hover']};
                color: {theme['text_main']};
            }}

            QPushButton#tab_button:checked {{
               background-color: {theme['bg_item_hover']};
               color: {theme['accent']};
               border-bottom: {max(1, s(2))}px solid {theme['accent']};
            }}

            #section_header, #section_header_container {{
               background-color: {theme['bg_main']};
            }}
            QComboBox {{
                background-color: {theme['bg_item_hover']};
                border: {max(1, s(1))}px solid {theme['border']};
                color: {theme['text_main']};
                padding: {s(4)}px;
                border-radius: {s(4)}px;
                font-size: {UIConstants.FONT_SIZE_DEFAULT}px;
            }}

            QLineEdit, QTextEdit {{
                background-color: {theme['bg_item_hover']};
                border: {max(1, s(1))}px solid {theme['border']};
                color: {theme['text_main']};
                padding: {s(4)}px;
                border-radius: {s(4)}px;
                font-size: {UIConstants.FONT_SIZE_DEFAULT}px;
            }}

            QGroupBox {{
                border: {max(1, s(1))}px solid {theme['border']};
                border-radius: {s(6)}px;
                margin-top: {s(12)}px;
                background-color: {theme['bg_main']};
            }}

            QGroupBox::title {{
                color: {theme['accent']};
                subcontrol-origin: margin;
                left: {s(10)}px;
                padding: 0 {s(3)}px 0 {s(3)}px;
            }}

            QPushButton#action_button {{
                background-color: transparent;
                color: {theme['accent']};
                border: none;
                padding: {s(4)}px {s(8)}px;
                font-size: {UIConstants.FONT_SIZE_DETAIL_INFO}px;
            }}


            QPushButton#action_button:hover {{
                text-decoration: underline;
                background-color: {theme['bg_item_hover']};
                border-radius: {s(4)}px;
            }}

            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: {max(8, s(10))}px;
                margin: 0px;
            }}

            QScrollBar::handle:vertical {{
                background: {theme['border']};
                min-height: {s(20)}px;
                border-radius: {s(5)}px;
            }}

            QScrollBar::handle:vertical:hover {{
                background: {theme['text_dim']};
            }}

            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}

            QScrollBar:horizontal {{
                border: none;
                background: transparent;
                height: {UIConstants.SCROLLBAR_SIZE}px;
                margin: 0px;
            }}

            QScrollBar::handle:horizontal {{
                background: {theme['border']};
                min-width: {s(20)}px;
                border-radius: {s(5)}px;
            }}

            QScrollBar::handle:horizontal:hover {{
                background: {theme['text_dim']};
            }}

            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}

            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none;
            }}

            QScrollArea {{
                border: none;
                background-color: transparent;
            }}

            QWidget#selection_bar {{
                background-color: {theme['bg_header']};
                border-top: {max(1, s(1))}px solid {theme['border']};
            }}

            QWidget#section_header {{
                background-color: transparent;
            }}

            QWidget#section_header QLabel {{
                color: {theme['text_main']};
                background-color: transparent;
            }}

            /* Main shell top bars (actual headers) */
            QMainWindow > QWidget > QWidget#top_header, 
            QMainWindow > QWidget > QStackedWidget > QWidget > QWidget#top_header {{
                background-color: {theme['bg_header']};
                border-bottom: {max(1, s(1))}px solid {theme['border']};
            }}

            QWidget#top_header QLabel {{
                color: {theme['text_main']};
                background-color: transparent;
            }}

            QSlider#reader_slider {{
                height: {s(30)}px;
            }}

            QSlider#reader_slider::groove:horizontal {{
                border: none;
                height: {s(4)}px;
                background: {theme['bg_item_hover']};
                margin: {s(2)}px 0;
                border-radius: {s(2)}px;
            }}

            QSlider#reader_slider::handle:horizontal {{
                background: {theme['accent']};
                border: {max(1, s(1))}px solid {theme['accent']};
                width: {s(24)}px;
                height: {s(24)}px;
                margin: -{s(10)}px 0;
                border-radius: {s(12)}px;
            }}

            QSlider#reader_slider::handle:horizontal:hover {{
                background: {theme['text_on_accent']};
                border: {max(1, s(1))}px solid {theme['text_on_accent']};
            }}

            QSlider#reader_slider::sub-page:horizontal {{
                background: {theme['accent']};
                border-radius: {s(2)}px;
            }}

            QProgressBar {{
                border: none;
                background-color: {theme['bg_item_hover']};
                height: {s(2)}px;
                min-height: {s(2)}px;
                max-height: {s(2)}px;
                border-radius: 0px;
            }}

            QProgressBar::chunk {{
                background-color: {theme['accent']};
                border-radius: 0px;
            }}


            QFrame#sidebar {{
                background-color: {theme['bg_sidebar']};
                border: none;
                border-right: {max(1, s(1))}px solid {theme['border']};
            }}

            QFrame#top_header {{
                background-color: {theme['bg_header']};
                border: none;
                border-bottom: {max(1, s(1))}px solid {theme['border']};
            }}

            QFrame#debug_bar {{
                background-color: {theme['bg_sidebar']};
                border-bottom: {max(1, s(1))}px solid {theme['border']};
            }}

            QFrame#badge {{
                background-color: rgba(128, 128, 128, 30);
                border-radius: {s(10)}px;
                border: {max(1, s(1))}px solid rgba(128, 128, 128, 50);
            }}


            QFrame#badge:hover {{
                background-color: rgba(128, 128, 128, 50);
                border: {max(1, s(1))}px solid {theme['accent']};
            }}

            QRadioButton::indicator {{
                width: {s(14)}px;
                height: {s(14)}px;
                border-radius: {s(7)}px;
                border: {max(1, s(2))}px solid {theme['border']};
                background-color: transparent;
            }}

            QLabel#breadcrumb_active {{
                font-weight: bold;
                font-size: {UIConstants.FONT_SIZE_BREADCRUMB}px;
                color: {theme['accent']};
            }}

            QPushButton#breadcrumb_dim {{
                color: {theme['text_dim']};
                font-size: {UIConstants.FONT_SIZE_BREADCRUMB}px;
                background-color: transparent;
                border: none;
                padding: 0;
            }}

            QPushButton#breadcrumb_dim:hover {{
                color: {theme['text_main']};
                text-decoration: underline;
            }}

            QListWidget#nav_list {{
                background-color: {theme['bg_sidebar']};
                color: {theme['text_main']};
                border: none;
            }}

            QListWidget#nav_list::item {{
                color: {theme['text_main']};
                padding: {s(10)}px;
                border-radius: 0px;
                font-size: {UIConstants.FONT_SIZE_SIDEBAR}px;
            }}

            QListWidget#nav_list::item:selected {{
                background-color: {theme['bg_item_hover']};
                color: {theme['accent']};
                border-left: {max(1, s(3))}px solid {theme['accent']};
            }}

            QListWidget#search_list::item {{
                padding: 0px;
                border-radius: {s(4)}px;
            }}

            QLabel#breadcrumb_sep {{
                color: {theme['text_dim']};
                font-size: {UIConstants.FONT_SIZE_BREADCRUMB}px;
                font-weight: bold;
            }}

            /* UNIFIED ACTION BUTTONS (Read, Download, etc) */
            QPushButton#primary_button {{
                background-color: {theme['accent']};
                color: {theme['text_on_accent']};
                border: {max(1, s(1))}px solid {theme['accent']};
                border-radius: {s(4)}px;
                padding: {s(8)}px {s(16)}px;
                font-size: {UIConstants.FONT_SIZE_DETAIL_INFO}px;
                font-weight: bold;
            }}

            QPushButton#primary_button:hover {{
                background-color: {theme['accent']};
                opacity: 0.85;
            }}

            QPushButton#secondary_button {{
                background-color: {theme['bg_main']};
                color: {theme['text_main']};
                border: {max(1, s(1))}px solid {theme['border']};
                border-radius: {s(4)}px;
                padding: {s(8)}px {s(16)}px;
                font-size: {UIConstants.FONT_SIZE_DETAIL_INFO}px;
                font-weight: bold;
            }}

            QPushButton#secondary_button:hover {{
                background-color: {theme['bg_item_hover']};
                border: {max(1, s(1))}px solid {theme['accent']};
            }}

            QPushButton#primary_button:pressed,
            QPushButton#secondary_button:pressed {{
                background-color: {theme['bg_item_selected']};
                color: {theme['text_selected']};
                border-color: {theme['accent']};
            }}

            QPushButton#primary_button:disabled,
            QPushButton#secondary_button:disabled {{
                background-color: {theme['bg_item_hover']};
                color: {theme['text_dim']};
                border: {max(1, s(1))}px solid {theme['border']};
                opacity: 0.6;
            }}

            QPushButton#danger_button {{
                background-color: transparent !important;
                color: {theme['danger']} !important;
                border: {max(1, s(1))}px solid {theme['danger']} !important;
                border-radius: {s(4)}px !important;
                padding: {s(8)}px {s(20)}px !important;
                font-size: {UIConstants.FONT_SIZE_DETAIL_INFO}px !important;
            }}

            QPushButton#danger_button:hover {{
                background-color: {theme['danger']} !important;
                color: #ffffff !important;
            }}

            QPushButton#section_toggle, QPushButton#nav_link_button, QPushButton#nav_continuous_button {{
                text-align: left;
                padding-left: {s(10)}px;
                color: {theme['accent']};
                border: none;
                background-color: transparent;
            }}

            QPushButton#pin_button {{
                color: #ffd700;
                font-size: {s(16)}px;
                background-color: transparent;
                border: none;
            }}

            QPushButton#nav_link_button:hover, QPushButton#nav_continuous_button:hover {{
                background-color: {theme['bg_item_hover']};
                border-radius: {s(4)}px;
            }}

            QMenu {{
                background-color: {theme['bg_header']};
                color: {theme['text_main']};
                border: {max(1, s(1))}px solid {theme['border']};
                padding: {s(5)}px;
                font-size: {UIConstants.FONT_SIZE_DEFAULT}px;
            }}

            QMenu::item {{
                padding: {s(5)}px {s(25)}px {s(5)}px {s(20)}px;
                border-radius: {s(4)}px;
            }}

            QMenu::item:selected {{
                background-color: {theme['bg_item_hover']};
                color: {theme['accent']};
            }}

            QMenu::separator {{
                height: {max(1, s(1))}px;
                background-color: {theme['border']};
                margin: {s(5)}px {s(10)}px;
            }}
            """
        app.setStyleSheet(stylesheet)
        
        # Also set palette for some native widgets
        palette = QPalette()
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Window, QColor(theme['bg_main']))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.WindowText, QColor(theme['text_main']))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Base, QColor(theme['bg_main']))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.AlternateBase, QColor(theme['bg_sidebar']))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.ToolTipBase, QColor(theme['bg_main']))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.ToolTipText, QColor(theme['text_main']))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Text, QColor(theme['text_main']))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Button, QColor(theme['bg_main']))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.ButtonText, QColor(theme['text_main']))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.BrightText, QColor(theme['accent']))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Highlight, QColor(theme['accent']))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        app.setPalette(palette)
