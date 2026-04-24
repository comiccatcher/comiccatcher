# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QSizePolicy
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from typing import Optional, Callable
from comiccatcher.ui.theme_manager import ThemeManager, UIConstants

class SectionHeader(QWidget):
    """
    Standardized header for sections. Used by CollapsibleSection (layout-based) 
    and ScrolledFeedView (virtual-based).
    """
    toggled = pyqtSignal(bool)

    def __init__(self, title: str, action_widget: Optional[QWidget] = None, 
                 is_collapsed: bool = False, on_context_menu: Optional[Callable] = None, parent=None):
        super().__init__(parent)
        self._is_collapsed = is_collapsed
        self.action_widget = action_widget
        self._on_context_menu = None

        self.setObjectName("section_header_container")
        self.setFixedHeight(UIConstants.SECTION_HEADER_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, UIConstants.SECTION_HEADER_MARGIN_TOP, 0, 0)
        self.layout.setSpacing(UIConstants.SECTION_HEADER_SPACING)

        # 1. Toggle Button
        s = UIConstants.scale
        self.btn_toggle = QPushButton()
        self.btn_toggle.setObjectName("icon_button")
        self.btn_toggle.setIconSize(QSize(s(16), s(16)))
        self.btn_toggle.setFixedSize(UIConstants.TOGGLE_BUTTON_SIZE, UIConstants.TOGGLE_BUTTON_SIZE)
        self.btn_toggle.setFlat(True)
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.clicked.connect(self.toggle)
        self.layout.addWidget(self.btn_toggle)

        # 2. Title Label
        self.header_label = QLabel(title)
        self.header_label.setCursor(Qt.CursorShape.PointingHandCursor)
        
        def label_press(e):
            if e.button() == Qt.MouseButton.LeftButton:
                self.toggle()
                return
            QLabel.mousePressEvent(self.header_label, e)

        self.header_label.mousePressEvent = label_press
        self.layout.addWidget(self.header_label)

        self.layout.addStretch()
        
        # 3. Action Widget (e.g., 'See All')
        if action_widget:
            self.layout.addWidget(action_widget)

        # 4. Context Menu Setup
        if on_context_menu:
            self.on_context_menu = on_context_menu

        self.reapply_theme()

    @property
    def on_context_menu(self):
        return self._on_context_menu

    @on_context_menu.setter
    def on_context_menu(self, callback: Optional[Callable]):
        """Sets or updates the context menu callback for the header and its children."""
        if self._on_context_menu:
            try:
                self.customContextMenuRequested.disconnect(self._on_context_menu)
                for w in [self.btn_toggle, self.header_label]:
                    w.customContextMenuRequested.disconnect(self._on_context_menu)
            except (TypeError, RuntimeError):
                pass
        
        self._on_context_menu = callback
        if callback:
            self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.customContextMenuRequested.connect(callback)
            for w in [self.btn_toggle, self.header_label]:
                w.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                w.customContextMenuRequested.connect(callback)
        else:
            self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
            for w in [self.btn_toggle, self.header_label]:
                w.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

    def set_right_margin(self, margin: int):
        """Adjusts the right margin to account for vertical scrollbars."""
        m = self.layout.contentsMargins()
        self.layout.setContentsMargins(m.left(), m.top(), margin, m.bottom())

    def toggle(self):
        self._is_collapsed = not self._is_collapsed
        self._update_ui_state()
        self.toggled.emit(self._is_collapsed)

    def set_collapsed(self, collapsed: bool):
        if self._is_collapsed != collapsed:
            self.toggle()

    def _update_ui_state(self):
        icon_name = "chevron_right" if self._is_collapsed else "chevron_down"
        self.btn_toggle.setIcon(ThemeManager.get_icon(icon_name, "accent"))

    def reapply_theme(self):
        theme = ThemeManager.get_current_theme_colors()
        self.header_label.setStyleSheet(f"font-size: {UIConstants.FONT_SIZE_SECTION_HEADER}px; font-weight: bold; color: {theme['text_main']};")
        self._update_ui_state()
