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
        "border": "#c8cdd4",
        "card_bg": "#ffffff"
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
        "border": "#333333",
        "card_bg": "#252526"
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
        "border": "#404040",
        "card_bg": "#000000"
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
        "border": "#334155",
        "card_bg": "#1e293b"
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
        "border": "#bfdbfe",
        "card_bg": "#ffffff"
    }
}

class ThemeManager:
    _current_theme: str = "dark"

    @classmethod
    def get_icon(cls, name: str, color_key: str = "text_main") -> QIcon:
        path = ICON_DIR / f"{name}.svg"
        if not path.exists():
            return QIcon()
        theme = THEMES.get(cls._current_theme, THEMES["dark"])
        color = theme.get(color_key, theme["text_main"])
        try:
            from PyQt6.QtCore import QByteArray
            from PyQt6.QtGui import QPixmap
            svg = path.read_bytes()
            svg = svg.replace(b'stroke="white"', f'stroke="{color}"'.encode())
            svg = svg.replace(b'fill="white"', f'fill="{color}"'.encode())
            pixmap = QPixmap()
            if pixmap.loadFromData(QByteArray(svg), "SVG"):
                return QIcon(pixmap)
        except Exception:
            pass
        return QIcon(str(path))

    @classmethod
    def apply_theme(cls, app: QApplication, theme_name: str):
        cls._current_theme = theme_name
        theme = THEMES.get(theme_name, THEMES["dark"])
        
        stylesheet = f"""
            QMainWindow, QDialog {{
                background-color: {theme['bg_main']};
                color: {theme['text_main']};
            }}
            
            /* Broad text settings */
            QLabel, QRadioButton, QCheckBox, QGroupBox {{
                color: {theme['text_main']};
            }}
            
            QHeaderView::section {{
                background-color: {theme['bg_header']};
                color: {theme['text_dim']};
                padding: 4px;
                border: none;
                border-bottom: 1px solid {theme['border']};
            }}
            
            QListView, QTreeView, QListWidget {{
                background-color: {theme['bg_main']};
                border: none;
                outline: none;
            }}
            
            QListView::item {{
                padding: 8px;
                border-radius: 4px;
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
                border: 1px solid {theme['border']};
                padding: 6px 12px;
                border-radius: 4px;
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
                border-bottom: 2px solid transparent;
                border-radius: 0px;
                padding: 6px 15px;
                font-weight: bold;
                font-size: 13px;
            }}

            QPushButton#tab_button:hover {{
                background-color: {theme['bg_item_hover']};
                color: {theme['text_main']};
            }}

            QPushButton#tab_button:checked {{
                background-color: {theme['bg_item_hover']};
                color: {theme['accent']};
                border-bottom: 2px solid {theme['accent']};
            }}
            
            QComboBox {{
                background-color: {theme['bg_item_hover']};
                border: 1px solid {theme['border']};
                color: {theme['text_main']};
                padding: 4px;
                border-radius: 4px;
            }}
            
            QLineEdit, QTextEdit {{
                background-color: {theme['bg_item_hover']};
                border: 1px solid {theme['border']};
                color: {theme['text_main']};
                padding: 4px;
                border-radius: 4px;
            }}
            
            QGroupBox {{
                border: 1px solid {theme['border']};
                border-radius: 6px;
                margin-top: 12px;
                font-weight: bold;
                background-color: {theme['bg_main']};
            }}

            QGroupBox::title {{
                color: {theme['accent']};
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }}
            
            QPushButton#see_all_button {{
                background-color: transparent;
                color: {theme['accent']};
                border: none;
                padding: 4px 8px;
                font-weight: bold;
                margin-top: 15px;
            }}
            
            QPushButton#see_all_button:hover {{
                text-decoration: underline;
                background-color: {theme['bg_item_hover']};
                border-radius: 4px;
            }}

            QScrollBar:vertical {{
                border: none;
                background: {theme['bg_main']};
                width: 10px;
                margin: 0px;
            }}
            
            QScrollBar::handle:vertical {{
                background: {theme['border']};
                min-height: 20px;
                border-radius: 5px;
            }}
            
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}

            QScrollBar:horizontal {{
                border: none;
                background: {theme['bg_main']};
                height: 10px;
                margin: 0px;
            }}
            
            QScrollBar::handle:horizontal {{
                background: {theme['border']};
                min-width: 20px;
                border-radius: 5px;
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
            
            QProgressBar {{
                border: none;
                background-color: {theme['bg_item_hover']};
                height: 4px;
                text-align: center;
                border-radius: 2px;
            }}
            
            QProgressBar::chunk {{
                background-color: {theme['accent']};
                border-radius: 2px;
            }}
            
            QFrame#badge {{
                background-color: rgba(128, 128, 128, 30);
                border-radius: 10px;
                border: 1px solid rgba(128, 128, 128, 50);
            }}
            
            QFrame#badge:hover {{
                background-color: rgba(128, 128, 128, 50);
                border: 1px solid {theme['accent']};
            }}

            QGroupBox QWidget {{
                background-color: transparent;
            }}

            QRadioButton::indicator {{
                width: 14px;
                height: 14px;
                border-radius: 7px;
                border: 2px solid {theme['border']};
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
                padding: 10px;
                border-radius: 0px;
                font-weight: bold;
                font-size: 12px;
            }}
            
            QListWidget#nav_list::item:selected {{
                background-color: {theme['bg_item_hover']};
                color: {theme['accent']};
                border-left: 3px solid {theme['accent']};
            }}

            QListWidget#search_list::item {{
                padding: 0px;
                border-radius: 4px;
            }}

            QLabel#breadcrumb_sep {{
                color: {theme['border']};
                font-weight: bold;
            }}

            /* EXTREMELY SPECIFIC PRIMARY BUTTON RULES - FORCED OVERRIDE */
            /* Using background: to ensure it overrides all sub-properties */
            QPushButton#primary_button {{
                background: {theme['accent']};
                background-color: {theme['accent']};
                color: #ffffff;
                font-weight: bold;
                border: 1px solid {theme['accent']};
                border-radius: 4px;
                padding: 10px 24px;
            }}

            QPushButton#primary_button:hover {{
                background: #ffffff;
                background-color: #ffffff;
                color: {theme['accent']};
                border: 2px solid {theme['accent']};
            }}

            QPushButton#primary_button:disabled {{
                background: {theme['border']};
                background-color: {theme['border']};
                color: {theme['text_dim']};
                border: none;
            }}

            QPushButton#section_toggle, QPushButton#nav_link_button, QPushButton#nav_continuous_button {{
                text-align: left;
                padding-left: 10px;
                font-weight: bold;
                color: {theme['accent']};
                border: none;
                background-color: transparent;
            }}

            QPushButton#pin_button {{
                color: #ffd700;
                font-size: 16px;
                background-color: transparent;
                border: none;
            }}

            QPushButton#nav_link_button:hover, QPushButton#nav_continuous_button:hover {{
                background-color: {theme['bg_item_hover']};
                border-radius: 4px;
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
