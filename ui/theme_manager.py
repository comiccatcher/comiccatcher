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
        "accent": "#004bb0",
        "accent_dim": "rgba(0, 75, 176, 40)",
        "border": "#c8cdd4",
        "card_bg": "#ffffff",
        "card_border": "#d1d5db",
        "white": "#ffffff",
        "danger": "#dc3545",
        "success": "#28a745"
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
        "accent": "#007fd4",
        "accent_dim": "rgba(0, 127, 212, 40)",
        "border": "#333333",
        "card_bg": "#252526",
        "card_border": "#3f3f46",
        "white": "#ffffff",
        "danger": "#f44336",
        "success": "#4caf50"
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
        "accent": "#007fd4",
        "accent_dim": "rgba(0, 127, 212, 60)",
        "border": "#404040",
        "card_bg": "#000000",
        "card_border": "#333333",
        "white": "#ffffff",
        "danger": "#f44336",
        "success": "#4caf50"
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
        "accent": "#0ea5e9",
        "accent_dim": "rgba(14, 165, 233, 40)",
        "border": "#334155",
        "card_bg": "#1e293b",
        "card_border": "#334155",
        "white": "#ffffff",
        "danger": "#ef4444",
        "success": "#10b981"
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
        "accent": "#1d4ed8",
        "accent_dim": "rgba(29, 78, 216, 40)",
        "border": "#bfdbfe",
        "card_bg": "#ffffff",
        "card_border": "#bfdbfe",
        "white": "#ffffff",
        "danger": "#dc3545",
        "success": "#16a34a"
    }
}

class UIConstants:
    """Centralized design tokens for consistent UI across all views."""
    _scale_factor = 1.0

    @classmethod
    def scale(cls, val: int) -> int:
        return max(1, int(val * cls._scale_factor)) if val > 0 else 0

    @classmethod
    def set_scale(cls, factor: float):
        cls._scale_factor = max(0.5, min(3.0, factor))
        cls.init_scale()

    @classmethod
    def init_scale(cls):
        # Only fetch screen DPI if _scale_factor is still at default 1.0
        # or we want to force a reset.
        if cls._scale_factor == 1.0:
            app = QApplication.instance()
            if app:
                screen = app.primaryScreen()
                if screen:
                    cls._scale_factor = screen.logicalDotsPerInch() / 96.0

        cls.HEADER_HEIGHT = cls.scale(50)
        cls.STATUS_HEIGHT = cls.scale(2)
        
        # Fonts
        cls.FONT_SIZE_SECTION_HEADER = cls.scale(14)
        cls.FONT_SIZE_SECTION_HEADER_UNSCALED = 14
        cls.FONT_SIZE_CARD_LABEL = cls.scale(9)
        cls.FONT_SIZE_CARD_LABEL_UNSCALED = 9
        cls.FONT_SIZE_STATUS = cls.scale(11)
        cls.FONT_SIZE_STATUS_UNSCALED = 11
        
        # Card Dimensions
        cls.CARD_WIDTH = cls.scale(140)
        cls.CARD_HEIGHT = cls.scale(240)
        cls.CARD_SPACING = cls.scale(10)
        cls.CARD_LABEL_HEIGHT = cls.scale(45)
        cls.CARD_COVER_HEIGHT = cls.scale(180)
        cls.CARD_PADDING = cls.scale(5)
        cls.CARD_ROUNDING = cls.scale(5)
        cls.CARD_BORDER_WIDTH = max(1, cls.scale(1))
        cls.CARD_BORDER_WIDTH_SELECTED = max(1, cls.scale(2))
        
        # Delegate internal offsets
        cls.FOLDER_ICON_MARGIN = cls.scale(10)
        cls.FOLDER_BADGE_SIZE = cls.scale(32)
        cls.FOLDER_BADGE_OFFSET_Y = cls.scale(4)
        
        cls.PROGRESS_BAR_HEIGHT = cls.scale(2)
        cls.PROGRESS_BAR_TOTAL_HEIGHT = cls.scale(10)
        cls.PROGRESS_BAR_MARGIN_H = cls.scale(10)
        cls.PROGRESS_BAR_OFFSET_Y = cls.scale(6)
        
        # Layout & Heuristics
        cls.GRID_GUTTER = cls.scale(10)
        cls.RIBBON_LABEL_GAP = cls.scale(25)
        cls.LARGE_SECTION_THRESHOLD = 200
        cls.VIEWPORT_MARGIN = cls.scale(20)
        
        # Skeleton / Loading
        cls.SKELETON_PADDING = cls.scale(10)
        cls.SKELETON_ROUNDING = cls.scale(3)
        
        # Layout Spacing & Margins
        from PyQt6.QtWidgets import QStyle
        cls.SCROLLBAR_SIZE = app.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent)
        
        cls.SECTION_SPACING = cls.scale(2)
        cls.SECTION_MARGIN_BOTTOM = cls.scale(5)
        cls.SECTION_HEADER_SPACING = cls.scale(5)
        cls.SECTION_HEADER_MARGIN_TOP = cls.scale(5)
        cls.SECTION_HEADER_HEIGHT = cls.scale(30)
        cls.GRID_SPACING = cls.scale(10)
        cls.TOOLBAR_GAP = cls.scale(12)
        cls.TOGGLE_BUTTON_SIZE = cls.scale(24)
        cls.HEADER_BUTTON_SIZE = cls.scale(32)
        cls.LAYOUT_MARGIN_DEFAULT = cls.scale(10)
        cls.LAYOUT_MARGIN_LARGE = cls.scale(20)
        
        # Labeling
        cls.ELIDED_TEXT_WIDTH_FACTOR = 1.85 # Factor of width for 2-line elided text
        
        # Popovers & Overlays
        cls.POPOVER_OFFSET = cls.scale(10)
        cls.POPOVER_ROUNDING = cls.scale(8)

        # Debug
        # Toggle with Ctrl+Shift+D at runtime — set True to always enable on startup
        if not hasattr(cls, 'DEBUG_OUTLINES'):
            cls.DEBUG_OUTLINES = False

        # Virtualization & Fetching
        cls.ITEMS_PER_PAGE = 100
        cls.SPARSE_FETCH_BUFFER = 1 # +/- pages around viewport
        cls.MAX_CONCURRENT_FETCHES = 3
        cls.SCROLL_DEBOUNCE_MS = 250
        cls.STATUS_UPDATE_MS = 50
        cls.RESIZE_DEBOUNCE_MS = 200

    # Initial Defaults (Will be overwritten by init_scale at startup)
    HEADER_HEIGHT = 50
    STATUS_HEIGHT = 2
    FONT_SIZE_SECTION_HEADER = 14
    FONT_SIZE_CARD_LABEL = 9
    FONT_SIZE_STATUS = 11
    CARD_WIDTH = 140
    CARD_HEIGHT = 240
    CARD_SPACING = 10
    CARD_LABEL_HEIGHT = 45
    CARD_COVER_HEIGHT = 180
    CARD_PADDING = 5
    CARD_ROUNDING = 5
    CARD_BORDER_WIDTH = 1
    CARD_BORDER_WIDTH_SELECTED = 2
    FOLDER_ICON_MARGIN = 10
    FOLDER_BADGE_SIZE = 32
    FOLDER_BADGE_OFFSET_Y = 4
    PROGRESS_BAR_HEIGHT = 4
    PROGRESS_BAR_TOTAL_HEIGHT = 10
    PROGRESS_BAR_MARGIN_H = 10
    PROGRESS_BAR_OFFSET_Y = 6
    GRID_GUTTER = 10
    RIBBON_LABEL_GAP = 25
    LARGE_SECTION_THRESHOLD = 200
    VIEWPORT_MARGIN = 20
    SKELETON_PADDING = 10
    SKELETON_ROUNDING = 3
    
    # Layout Spacing & Margins
    SECTION_SPACING = 2
    SECTION_MARGIN_BOTTOM = 5
    SECTION_HEADER_SPACING = 5
    SECTION_HEADER_MARGIN_TOP = 5
    SECTION_HEADER_HEIGHT = 30
    GRID_SPACING = 10
    TOOLBAR_GAP = 12
    TOGGLE_BUTTON_SIZE = 24
    HEADER_BUTTON_SIZE = 32
    LAYOUT_MARGIN_DEFAULT = 10
    LAYOUT_MARGIN_LARGE = 20

    # Labeling
    ELIDED_TEXT_WIDTH_FACTOR = 1.85
    
    # Popovers & Overlays
    POPOVER_OFFSET = 10
    POPOVER_ROUNDING = 8

    # Virtualization & Fetching
    ITEMS_PER_PAGE = 100
    SPARSE_FETCH_BUFFER = 1
    MAX_CONCURRENT_FETCHES = 3
    SCROLL_DEBOUNCE_MS = 250
    STATUS_UPDATE_MS = 50
    RESIZE_DEBOUNCE_MS = 200
    
    # Selection colors
    COLOR_ACCENT = "#007fd4" # Default blue

class ThemeManager:
    _current_theme: str = "dark"

    @classmethod
    def get_current_theme_colors(cls) -> dict:
        return THEMES.get(cls._current_theme, THEMES["dark"])

    @classmethod
    def get_icon(cls, name: str, color_key: str = "text_main") -> QIcon:
        """
        Returns a state-aware QIcon that handles different colors for 
        Normal, Disabled, and Selected/Checked states.
        """
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
            
        return icon

    @classmethod
    def apply_theme(cls, app: QApplication, theme_name: str):
        UIConstants.init_scale()
        s = UIConstants.scale
        
        cls._current_theme = theme_name
        theme = THEMES.get(theme_name, THEMES["dark"])
        
        stylesheet = f"""
            QMainWindow, QDialog {{
                background-color: {theme['bg_main']};
                color: {theme['text_main']};
            }}
            
            /* Broad text settings */
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
                background-color: {theme['bg_item_hover']};
                color: {theme['text_main']};
                border: {max(1, s(1))}px solid {theme['border']};
                padding: {s(6)}px {s(12)}px;
                border-radius: {s(4)}px;
            }}

            QPushButton:hover {{
                border-color: {theme['accent']};
                background-color: {theme['bg_item_selected']};
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
            }}

            QLineEdit, QTextEdit {{
                background-color: {theme['bg_item_hover']};
                border: {max(1, s(1))}px solid {theme['border']};
                color: {theme['text_main']};
                padding: {s(4)}px;
                border-radius: {s(4)}px;
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
            }}


            QPushButton#action_button:hover {{
                text-decoration: underline;
                background-color: {theme['bg_item_hover']};
                border-radius: {s(4)}px;
            }}

            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: {UIConstants.SCROLLBAR_SIZE}px;
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
                background: {theme['white']};
                border: {max(1, s(1))}px solid {theme['white']};
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
                color: {theme['accent']};
            }}

            QPushButton#breadcrumb_dim {{
                color: {theme['text_dim']};
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
                font-size: {s(12)}px;
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
                font-weight: bold;
            }}

            /* THE ABSOLUTE HIGHEST SPECIFICITY FOR THE PRIMARY BUTTON */
            /* Using multiple selectors to ensure it wins the specificity war */
            QWidget QPushButton#primary_button {{
                background-color: {theme['accent']} !important;
                color: #ffffff !important;
                border: 1px solid {theme['accent']} !important;
                border-radius: {s(4)}px !important;
                padding: {s(8)}px {s(20)}px !important;
            }}

            QWidget QPushButton#primary_button:hover {{
                background-color: {theme['accent']} !important;
                opacity: 0.8 !important;
            }}

            QWidget QPushButton#danger_button {{
                background-color: transparent !important;
                color: {theme['danger']} !important;
                border: 1px solid {theme['danger']} !important;
            }}

            QWidget QPushButton#danger_button:hover {{
                background-color: {theme['danger']} !important;
                color: #ffffff !important;
            }}

            QWidget QPushButton#secondary_button {{
                background-color: transparent !important;
                color: {theme['text_main']} !important;
                border: {max(1, s(1))}px solid {theme['border']} !important;
                border-radius: {s(4)}px !important;
                padding: {s(8)}px {s(20)}px !important;
            }}

            QWidget QPushButton#secondary_button:hover {{
                background-color: {theme['bg_item_hover']} !important;
                border-color: {theme['accent']} !important;
            }}

            QWidget QPushButton#secondary_button:pressed {{
                background-color: {theme['bg_item_selected']} !important;
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
