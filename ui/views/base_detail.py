import asyncio
from typing import Any, Dict, Optional, List
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QFrame, QProgressBar, QSizePolicy, QGraphicsOpacityEffect
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QFont

from logger import get_logger
from api.image_manager import ImageManager

class BaseDetailView(QWidget):
    def __init__(self, on_back):
        super().__init__()
        self.on_back = on_back
        self.image_manager = ImageManager(None)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(0)

        # Header (Simple Back button)
        self.header = QHBoxLayout()
        self.btn_back = QPushButton()
        self.btn_back.setProperty("flat", "true")
        from ui.theme_manager import ThemeManager
        self.btn_back.setIcon(ThemeManager.get_icon("back"))
        self.btn_back.setFixedSize(32, 32)
        self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back.clicked.connect(self.on_back)
        self.header.addWidget(self.btn_back)
        self.header.addStretch()
        self.layout.addLayout(self.header)

        # Progress bar (loading state)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.layout.addWidget(self.progress)

        # Main Scroll Area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("background: transparent;")
        
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.content_layout.setContentsMargins(0, 10, 0, 0)
        self.scroll.setWidget(self.content_widget)
        self.layout.addWidget(self.scroll)

    def _clear_layout(self, layout):
        if layout is None: return
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            else:
                sub_layout = item.layout()
                if sub_layout:
                    self._clear_layout(sub_layout)
                    sub_layout.deleteLater()

    def _setup_main_info_layout(self):
        """Creates the split view: Cover | Metadata"""
        self._clear_layout(self.content_layout)
        
        self.top_row = QHBoxLayout()
        self.top_row.setSpacing(20)
        
        # Cover + Progress Layout
        self.cover_container = QWidget()
        self.cover_layout = QVBoxLayout(self.cover_container)
        self.cover_layout.setContentsMargins(0, 0, 0, 0)
        self.cover_layout.setSpacing(5)
        
        # Cover
        self.cover_label = QLabel()
        self.cover_label.setMinimumSize(200, 300)
        self.cover_label.setMaximumSize(300, 450)
        self.cover_label.setStyleSheet("background-color: rgba(0, 0, 0, 40); border: 1px solid rgba(128, 128, 128, 30);")
        self.cover_label.setScaledContents(True)
        self.cover_layout.addWidget(self.cover_label)
        
        # Blue line progress bar
        self.cover_progress = QProgressBar()
        self.cover_progress.setFixedHeight(4)
        self.cover_progress.setTextVisible(False)
        self.cover_progress.setStyleSheet("""
            QProgressBar { border: none; background: rgba(128, 128, 128, 30); border-radius: 2px; }
        """)
        self.cover_progress.setVisible(False)
        self.cover_layout.addWidget(self.cover_progress)
        
        self.top_row.addWidget(self.cover_container, 0, Qt.AlignmentFlag.AlignTop)
        
        # Info Column
        self.info_widget = QWidget()
        self.info_layout = QVBoxLayout(self.info_widget)
        self.info_layout.setContentsMargins(0, 0, 0, 0)
        self.info_layout.setSpacing(10)
        
        self.top_row.addWidget(self.info_widget, 1)
        self.content_layout.addLayout(self.top_row)
        
        return self.info_layout

    def _update_cover_progress(self, current, total):
        if total > 0 and current > 0:
            self.cover_progress.setRange(0, total)
            self.cover_progress.setValue(current)
            self.cover_progress.setVisible(True)
        else:
            self.cover_progress.setVisible(False)

    def _add_title(self, title_text, subtitle_text=None):
        title = QLabel(title_text)
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        title.setWordWrap(True)
        self.info_layout.addWidget(title)
        
        if subtitle_text:
            subtitle = QLabel(subtitle_text)
            subtitle.setStyleSheet("font-size: 18px; font-style: italic;")
            self.info_layout.addWidget(subtitle)

    def _add_read_button(self, on_click, label="Read Now"):
        self.btn_read = QPushButton(label)
        self.btn_read.setObjectName("primary_button")
        
        # Explicitly set colors from the current theme to avoid inheritance/native issues
        from ui.theme_manager import ThemeManager, THEMES
        theme = THEMES.get(ThemeManager._current_theme, THEMES["dark"])
        self.btn_read.setStyleSheet(f"""
            QPushButton#primary_button {{
                background-color: {theme['accent']};
                color: #ffffff;
                border: 1px solid {theme['accent']};
                font-weight: bold;
                border-radius: 4px;
            }}
            QPushButton#primary_button:hover {{
                background-color: #ffffff;
                color: {theme['accent']};
                border: 1px solid {theme['accent']};
            }}
        """)
        
        self.btn_read.setMinimumHeight(40)
        self.btn_read.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_read.clicked.connect(on_click)
        
        self.actions_layout = QHBoxLayout()
        self.actions_layout.addWidget(self.btn_read)
        self.actions_layout.addStretch()
        self.info_layout.addLayout(self.actions_layout)
        return self.btn_read

    def _add_progression_label(self):
        self.progression_label = QLabel("")
        self.progression_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.info_layout.addWidget(self.progression_label)
        return self.progression_label

    def _add_metadata_row(self, label, value):
        if not value: return
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        
        l = QLabel(f"<b>{label}:</b>")
        l.setFixedWidth(100)
        
        v = QLabel(str(value))
        v.setWordWrap(True)
        
        row_layout.addWidget(l)
        row_layout.addWidget(v, 1)
        self.info_layout.addWidget(row)

    async def _load_cover_async(self, url_or_path, is_local=False):
        if is_local:
             # Handle local path loading
             pass
        else:
            await self.image_manager.get_image_b64(url_or_path)
            full_path = self.image_manager._get_cache_path(url_or_path)
            if full_path.exists():
                pixmap = QPixmap(str(full_path))
                if not pixmap.isNull():
                    self.cover_label.setPixmap(pixmap)
