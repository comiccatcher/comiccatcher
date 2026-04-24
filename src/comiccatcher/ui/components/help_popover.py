# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

from typing import Optional, Callable, List, Tuple
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
)
from PyQt6.QtCore import Qt, QSize
from comiccatcher.ui.theme_manager import ThemeManager, UIConstants

class BrowserHelpPopover(QFrame):
    """
    Standardized popup for keyboard shortcuts.
    Displays a title and sections of key-description pairs.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        s = UIConstants.scale
        self.setFixedWidth(s(470))

        self.container = QFrame(self)
        self.container.setObjectName("browser_help_container")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(s(10), s(10), s(10), s(10))
        layout.addWidget(self.container)

        self.inner = QVBoxLayout(self.container)
        self.inner.setContentsMargins(s(25), s(25), s(25), s(25))
        self.inner.setSpacing(s(8))

        self.header = QLabel()
        self.header.setObjectName("header")
        self.header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.inner.addWidget(self.header)
        self.inner.addSpacing(s(10))
        self._rows: list[QWidget] = []
        self.footer = QLabel("Press any key or click anywhere to close")
        self.footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.inner.addSpacing(s(10))
        self.inner.addWidget(self.footer)
        self.rebuild("Browser Controls", [])

    def rebuild(self, title: str, sections: List[Tuple[str, List[Tuple[str, str]]]]):
        while self._rows:
            widget = self._rows.pop()
            self.inner.removeWidget(widget)
            widget.deleteLater()

        self.header.setText(title)
        insert_at = 2
        for section_title, rows in sections:
            section = QLabel(section_title)
            section.setObjectName("section")
            self.inner.insertWidget(insert_at, section)
            self._rows.append(section)
            insert_at += 1
            for key, desc in rows:
                row_widget = QWidget()
                row = QHBoxLayout(row_widget)
                row.setContentsMargins(0, 0, 0, 0)
                key_label = QLabel(key)
                key_label.setObjectName("key")
                desc_label = QLabel(desc)
                row.addWidget(key_label)
                row.addWidget(desc_label, 1)
                self.inner.insertWidget(insert_at, row_widget)
                self._rows.append(row_widget)
                insert_at += 1

        theme = ThemeManager.get_current_theme_colors()
        s = UIConstants.scale
        self.container.setStyleSheet(f"""
            QFrame#browser_help_container {{
                background-color: {theme['bg_header']};
                border: {max(1, s(2))}px solid {theme['accent']};
                border-radius: {s(15)}px;
            }}
            QLabel {{
                color: {theme['text_main']};
                background: transparent;
                font-size: {s(13)}px;
            }}
            QLabel#header {{
                font-weight: bold;
                font-size: {s(18)}px;
                color: {theme['accent']};
            }}
            QLabel#section {{
                font-weight: bold;
                font-size: {s(14)}px;
                color: {theme['accent']};
                margin-top: {s(10)}px;
            }}
            QLabel#key {{
                font-family: monospace;
                font-weight: bold;
                color: {theme['text_main']};
                background: rgba(128,128,128,40);
                border-radius: {s(3)}px;
                padding: 0 {s(4)}px;
            }}
        """)
        self.footer.setStyleSheet(f"color: {theme['text_dim']}; font-style: italic; font-size: {s(11)}px;")

    def mousePressEvent(self, event):
        self.hide()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        self.hide()
        event.accept()

    def show_at_center(self, target_rect):
        """Show and center the popover within the provided target_rect."""
        self.show()
        # Geometry is only reliable after show() for widgets with dynamic content
        self.adjustSize() 
        center = target_rect.center()
        self.move(
            center.x() - self.width() // 2,
            center.y() - self.height() // 2
        )
