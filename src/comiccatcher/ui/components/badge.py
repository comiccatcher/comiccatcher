# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt
from comiccatcher.ui.theme_manager import ThemeManager, UIConstants

class Badge(QFrame):
    def __init__(self, text, on_click=None):
        super().__init__()
        self.on_click = on_click
        self.setFrameShape(QFrame.Shape.NoFrame)
        obj_name = "badge" if on_click else "badge_static"
        self.setObjectName(obj_name)

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(text)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.label)

        if on_click:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reapply_theme()

    def reapply_theme(self):
        theme = ThemeManager.get_current_theme_colors()
        s = UIConstants.scale
        is_clickable = self.on_click is not None
        obj_name = self.objectName()

        bg = theme['bg_sidebar'] if is_clickable else "rgba(128, 128, 128, 20)"
        border_color = theme['layout_divider'] if is_clickable else "rgba(128, 128, 128, 50)"

        self.setStyleSheet(f"""
            QFrame#{obj_name} {{
                border-radius: {s(10)}px;
                padding: {s(1)}px {s(10)}px;
                border: {max(1, s(1))}px solid {border_color};
                background-color: {bg};
            }}
            QFrame#{obj_name}:hover {{
                background-color: {theme['bg_item_hover'] if is_clickable else bg};
                border-color: {theme['brand_primary'] if is_clickable else border_color};
            }}
        """)
        self.label.setStyleSheet(f"font-size: {UIConstants.FONT_SIZE_BADGE}px; border: none; background: transparent; color: {theme['content_primary'] if is_clickable else theme['content_secondary']};")
        
    def mousePressEvent(self, event):
        if self.on_click:
            self.on_click()
        super().mousePressEvent(event)
