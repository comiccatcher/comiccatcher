# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy
from PyQt6.QtCore import pyqtSignal
from typing import Optional, Callable
from comiccatcher.ui.theme_manager import UIConstants
from comiccatcher.ui.components.section_header import SectionHeader

class CollapsibleSection(QWidget):
    """
    A unified reusable component for collapsible sections with headers and content.
    Used by Library View and Paged Feed Browser.
    """
    toggled = pyqtSignal(bool) # Emits the new is_collapsed state

    def __init__(self, title: str, content_widget: QWidget, action_widget: Optional[QWidget] = None, 
                 is_collapsed: bool = False, on_context_menu: Optional[Callable] = None, parent=None):
        super().__init__(parent)
        self.content_widget = content_widget
        
        self.setObjectName("series_section")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, UIConstants.SECTION_MARGIN_BOTTOM)
        self.layout.setSpacing(0)

        # 1. Header component
        self.header = SectionHeader(
            title=title, 
            action_widget=action_widget, 
            is_collapsed=is_collapsed, 
            on_context_menu=on_context_menu
        )
        self.header.toggled.connect(self._on_header_toggled)
        self.layout.addWidget(self.header)

        # 2. Content
        if self.content_widget:
            self.layout.addWidget(self.content_widget)

        self._update_ui_state()

    @property
    def _is_collapsed(self):
        return self.header._is_collapsed

    @property
    def action_widget(self):
        return self.header.action_widget

    def set_content_widget(self, widget: QWidget):
        """Standardized helper to set or update the content widget."""
        if self.content_widget:
            self.layout.removeWidget(self.content_widget)
        self.content_widget = widget
        self.layout.addWidget(self.content_widget)
        self._update_ui_state()

    def toggle(self):
        self.header.toggle()

    def set_collapsed(self, collapsed: bool):
        self.header.set_collapsed(collapsed)

    def _on_header_toggled(self, collapsed: bool):
        self._update_ui_state()
        self.toggled.emit(collapsed)

    def _update_ui_state(self):
        if self.content_widget:
            self.content_widget.setVisible(not self._is_collapsed)
            if self._is_collapsed:
                self.content_widget.setFixedHeight(0)
            else:
                if self.content_widget.minimumHeight() == self.content_widget.maximumHeight() and self.content_widget.minimumHeight() > 0:
                    pass # Keep fixed height (Ribbons)
                else:
                    self.content_widget.setMinimumHeight(0)
                    self.content_widget.setMaximumHeight(16777215)

    def set_right_margin(self, margin: int):
        self.header.set_right_margin(margin)

    def reapply_theme(self):
        self.header.reapply_theme()
        self._update_ui_state()
