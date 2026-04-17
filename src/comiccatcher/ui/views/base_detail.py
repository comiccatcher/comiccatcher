# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

import asyncio
from typing import Any, Dict, Optional, List
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QFrame, QProgressBar, QSizePolicy, QGraphicsOpacityEffect,
    QSpacerItem
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QFont

from comiccatcher.logger import get_logger
from comiccatcher.api.image_manager import ImageManager
from comiccatcher.ui.theme_manager import ThemeManager, UIConstants

class BaseDetailView(QWidget):
    def __init__(self, on_back, image_manager: ImageManager):
        super().__init__()
        self.on_back = on_back
        self.image_manager = image_manager
        self._metadata_rows = [] # (label_widget, value_widget)
        self._labels = [] # List of other labels (title, subtitle, etc.)
        self._action_buttons = [] # List of buttons
        self._descriptions = [] # List of (container, label, btn_more, [dividers])
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(UIConstants.LAYOUT_MARGIN_DEFAULT, UIConstants.LAYOUT_MARGIN_DEFAULT, UIConstants.LAYOUT_MARGIN_DEFAULT, UIConstants.LAYOUT_MARGIN_DEFAULT)
        self.layout.setSpacing(0)

        # Header (Redundant since MainWindow has a unified header)
        self.header = QHBoxLayout()
        self.btn_back = QPushButton()
        self.btn_back.setProperty("flat", "true")
        self.btn_back.setIcon(ThemeManager.get_icon("back"))
        self.btn_back.setFixedSize(UIConstants.HEADER_BUTTON_SIZE, UIConstants.HEADER_BUTTON_SIZE)
        self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back.clicked.connect(self.on_back)
        self.btn_back.setVisible(False) # Now hidden
        self.header.addWidget(self.btn_back)
        self.header.addStretch()
        # We keep the layout but hide its contents or use 0 height
        self.layout.addLayout(self.header)
        self.header.setContentsMargins(0, 0, 0, 0)

        # Progress bar (loading state) - Make it an overlay child of self
        self.progress = QProgressBar(self)
        self.progress.setFixedHeight(UIConstants.PROGRESS_BAR_HEIGHT)
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.progress.raise_()

        # Main Scroll Area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        # Center horizontally and align to top
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        
        self.content_widget = QWidget()
        # Prevent content from stretching too far on wide screens
        self.content_widget.setMaximumWidth(UIConstants.DETAIL_MAX_WIDTH)
        
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.content_layout.setContentsMargins(0, UIConstants.LAYOUT_MARGIN_DEFAULT, 0, 0)
        
        # Add a permanent widget-based spacer at the bottom to ensure items always stick to the top
        self._bottom_spacer = QWidget()
        self._bottom_spacer.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        self.content_layout.addWidget(self._bottom_spacer)
        
        self.scroll.setWidget(self.content_widget)
        self.layout.addWidget(self.scroll)
        
        self.reapply_theme()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Position progress overlay at the top of the content area (just below our hidden header)
        self.progress.setGeometry(0, 0, self.width(), UIConstants.scale(4))
        self.progress.raise_()

    def create_action_button(self, text: str, callback: Optional[Any] = None, object_name: str = "secondary_button", icon_name: Optional[str] = None) -> QPushButton:
        """Creates a standardized, themed action button with optional icon and uniform sizing."""
        btn = QPushButton(text)
        btn.setObjectName(object_name)
        
        s = UIConstants.scale
        if object_name in ["primary_button", "secondary_button"]:
            btn.setMinimumHeight(s(40))
            btn.setMinimumWidth(s(150))
        elif object_name == "action_button":
            btn.setObjectName("link_button")
            
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        
        if icon_name:
            color_key = "white" if object_name == "primary_button" else "accent"
            btn.setIcon(ThemeManager.get_icon(icon_name, color_key))
            btn.setIconSize(QSize(s(20), s(20)))
            
        if callback:
            btn.clicked.connect(callback)
            
        self._action_buttons.append(btn)
        return btn

    def add_content_widget(self, widget: QWidget):
        """Standardized helper to add a widget to the main content layout (before the spacer)."""
        self.content_layout.insertWidget(self.content_layout.count() - 1, widget)

    def update_header_margins(self):
        """Standardized helper to update child header margins."""
        # Since content is now centered and limited in width, it typically 
        # won't overlap the scrollbar area on wide screens.
        # We use a consistent small margin.
        header_margin = UIConstants.scale(10)
        
        from comiccatcher.ui.components.section_header import SectionHeader
        from comiccatcher.ui.components.collapsible_section import CollapsibleSection
        
        # Check standard layout items (carousels in FeedDetail often use layouts directly)
        # but also check for any widget children.
        for hdr in self.findChildren(SectionHeader):
            hdr.set_right_margin(header_margin)
        for section in self.findChildren(CollapsibleSection):
            section.set_right_margin(header_margin)
            
        # Specific check for FeedDetailView's manual carousel layouts if they contain headers
        # will be handled by the specialized override if needed.

    def reapply_theme(self):
        theme = ThemeManager.get_current_theme_colors()
        s = UIConstants.scale
        self.scroll.setStyleSheet("background: transparent;")
        
        if hasattr(self, 'cover_label'):
            self.cover_label.setStyleSheet(f"background-color: {theme['card_bg']}; border: {max(1, s(1))}px solid {theme['card_border']}; border-radius: {s(4)}px;")
            
        # Re-apply for all dynamically added labels and buttons
        for label, subtitle in self._labels:
            label.setStyleSheet(f"font-size: {UIConstants.FONT_SIZE_DETAIL_TITLE}px; font-weight: bold; color: {theme['text_main']};")
            if subtitle:
                subtitle.setStyleSheet(f"font-size: {UIConstants.FONT_SIZE_DETAIL_SUBTITLE}px; font-style: italic; color: {theme['text_dim']};")
        
        if hasattr(self, 'progression_label') and self.progression_label:
            try:
                # Use font-size and weight, but allow Rich Text to override color for parts of it
                self.progression_label.setStyleSheet(f"font-size: {UIConstants.FONT_SIZE_DETAIL_INFO}px; font-weight: bold; color: {theme['accent']};")
            except RuntimeError:
                self.progression_label = None

        if hasattr(self, 'cover_footer') and self.cover_footer:
            try:
                self.cover_footer.setStyleSheet(f"font-size: {s(13)}px; font-family: monospace; color: {theme['text_dim']}; margin-top: {s(5)}px;")
            except RuntimeError:
                self.cover_footer = None
            
        for l, v in self._metadata_rows:
            try:
                l.setStyleSheet(f"font-weight: bold; font-size: {UIConstants.FONT_SIZE_DETAIL_INFO}px; color: {theme['text_dim']};")
                v.setStyleSheet(f"font-size: {UIConstants.FONT_SIZE_DETAIL_INFO}px; color: {theme['text_main']};")
            except RuntimeError:
                pass
        
        for item in self._descriptions:
            try:
                # Handle both 3-tuple (new) and 4-tuple (old, if still in memory)
                if len(item) == 3:
                    container, label, btn = item
                    dividers = []
                else:
                    container, label, btn, dividers = item

                label.setStyleSheet(f"color: {theme['text_main']}; line-height: 1.4; font-size: {s(13)}px;")
                if btn:
                    btn.setStyleSheet(f"color: {theme['accent']}; font-weight: bold; font-size: {s(11)}px; text-align: left; padding: {s(2)}px 0;")
                for div in dividers:
                    div.setStyleSheet(f"color: {theme['border']}; font-size: {s(14)}px; margin: {s(5)}px 0;")
            except RuntimeError:
                pass

    def _clear_layout(self, layout):
        if layout is None: return
        self._metadata_rows.clear()
        self._labels.clear()
        self._action_buttons.clear()
        self._descriptions.clear()
        
        # If this is the main content_layout, we want to keep the permanent spacer at the end
        is_main = (layout == self.content_layout)
        limit = 1 if is_main else 0
        
        while layout.count() > limit:
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            else:
                sub_layout = item.layout()
                if sub_layout:
                    self._clear_layout(sub_layout)
                    sub_layout.deleteLater()
        
        if is_main:
            # Reset stretch for the spacer
            layout.setStretch(layout.count() - 1, 100)

    def _setup_main_info_layout(self):
        """Creates the split view: Cover | Metadata"""
        self._clear_layout(self.content_layout)
        if hasattr(self, 'actions_layout'):
            delattr(self, 'actions_layout')
        
        s = UIConstants.scale
        # Explicitly reset button references
        self.btn_read = None
        self.btn_delete = None
        self.progression_label = None
        
        self.top_row = QHBoxLayout()
        self.top_row.setSpacing(s(20))
        
        # Cover + Progress Layout
        self.cover_container = QWidget()
        self.cover_layout = QVBoxLayout(self.cover_container)
        self.cover_layout.setContentsMargins(0, 0, 0, 0)
        self.cover_layout.setSpacing(s(5))
        
        # Cover
        self.cover_label = QLabel()
        # Calculate cover width as 1/3 of max width (approx 250px at 1.0x scale)
        cover_w = UIConstants.DETAIL_MAX_WIDTH // 3
        cover_h = int(cover_w * 1.5) # Maintain 2:3 aspect ratio for the placeholder
        self.cover_label.setFixedSize(cover_w, cover_h)
        self.cover_label.setScaledContents(False)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_layout.addWidget(self.cover_label)
        
        # Blue line progress bar
        self.cover_progress = QProgressBar()
        self.cover_progress.setFixedHeight(s(4))
        self.cover_progress.setTextVisible(False)
        self.cover_progress.setVisible(False)
        self.cover_layout.addWidget(self.cover_progress)
        
        # Cover footer (e.g. for file path)
        self.cover_footer = QLabel()
        self.cover_footer.setWordWrap(True)
        self.cover_footer.setAlignment(Qt.AlignmentFlag.AlignLeft)
        # Match cover width
        self.cover_footer.setFixedWidth(cover_w)
        self.cover_layout.addWidget(self.cover_footer)
        
        self.top_row.addWidget(self.cover_container, 0, Qt.AlignmentFlag.AlignTop)
        
        # Info Column
        self.info_widget = QWidget()
        self.info_layout = QVBoxLayout(self.info_widget)
        self.info_layout.setContentsMargins(0, 0, 0, 0)
        self.info_layout.setSpacing(s(10))
        
        self.top_row.addWidget(self.info_widget, 1)
        self.content_layout.insertLayout(0, self.top_row)
        
        self.reapply_theme() # Apply initial styles to newly created cover_label
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
        title.setObjectName("detail_title")
        title.setWordWrap(True)
        self.info_layout.addWidget(title)

        subtitle = None
        if subtitle_text:
            subtitle = QLabel(subtitle_text)
            subtitle.setObjectName("detail_subtitle")
            self.info_layout.addWidget(subtitle)

        self._labels.append((title, subtitle))
        self.reapply_theme()
    def _add_progression_label(self, text=""):
        self.progression_label = QLabel(text)
        self.progression_label.setObjectName("detail_progression")
        self.info_layout.addWidget(self.progression_label)
        self.reapply_theme()
        return self.progression_label

    def _add_description(self, text):
        if not text: return
        
        s = UIConstants.scale
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, s(5), 0, s(5))
        container_layout.setSpacing(s(5))
        
        container_layout.addSpacing(s(5))
        
        label = QLabel()
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignJustify)
        
        TRUNC_LIMIT = 400
        is_long = len(text) > TRUNC_LIMIT
        btn_more = None
        
        if is_long:
            # Simple truncation at word boundary
            truncated_text = text[:TRUNC_LIMIT].rsplit(' ', 1)[0] + "..."
            label.setText(truncated_text)
            
            btn_more = QPushButton("Show More")
            btn_more.setFlat(True)
            btn_more.setCursor(Qt.CursorShape.PointingHandCursor)
            
            def toggle_more():
                if btn_more.text() == "Show More":
                    label.setText(text)
                    btn_more.setText("Show Less")
                else:
                    label.setText(truncated_text)
                    btn_more.setText("Show More")
            
            btn_more.clicked.connect(toggle_more)
            
            container_layout.addWidget(label)
            container_layout.addWidget(btn_more)
        else:
            label.setText(text)
            container_layout.addWidget(label)
            
        container_layout.addSpacing(s(5))
        
        self.info_layout.addWidget(container)
        self._descriptions.append((container, label, btn_more))
        self.reapply_theme()
        return container

    def _add_metadata_row(self, label, value, monospace=False):
        if not value: return
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        
        s = UIConstants.scale
        l = QLabel(f"<b>{label}:</b>")
        l.setFixedWidth(s(100))
        
        v = QLabel(str(value))
        v.setWordWrap(True)
        if monospace:
            v.setFont(QFont("Monospace"))
            v.setStyleSheet("font-family: monospace;")
        
        row_layout.addWidget(l)
        row_layout.addWidget(v, 1)
        self.info_layout.addWidget(row)
        self._metadata_rows.append((l, v))
        self.reapply_theme()

    def set_cover_pixmap(self, pixmap: QPixmap):
        """Sets the cover pixmap, scaling it to fit while preserving aspect ratio."""
        if not pixmap or pixmap.isNull():
            self.cover_label.clear()
            self.cover_label.setText("No Cover")
            return

        scaled = pixmap.scaled(
            self.cover_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.cover_label.setPixmap(scaled)

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
                    self.set_cover_pixmap(pixmap)
