from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QSizePolicy
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from typing import Optional, Callable
from ui.theme_manager import ThemeManager, UIConstants

class SectionHeader(QWidget):
    """
    A lightweight header-only version of CollapsibleSection.
    Ideal for virtualized lists where the content is in separate rows.
    """
    toggled = pyqtSignal(bool)

    def __init__(self, title: str, action_widget: Optional[QWidget] = None, 
                 is_collapsed: bool = False, on_context_menu: Optional[Callable] = None, parent=None):
        super().__init__(parent)
        self._is_collapsed = is_collapsed

        self.setObjectName("section_header_container")
        self.setFixedHeight(UIConstants.SECTION_HEADER_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, UIConstants.SECTION_HEADER_MARGIN_TOP, 0, 0)
        self.layout.setSpacing(UIConstants.SECTION_HEADER_SPACING)

        # 1. Initialize Children FIRST
        s = UIConstants.scale
        self.btn_toggle = QPushButton()
        self.btn_toggle.setIconSize(QSize(s(16), s(16)))
        self.btn_toggle.setFixedSize(UIConstants.TOGGLE_BUTTON_SIZE, UIConstants.TOGGLE_BUTTON_SIZE)
        self.btn_toggle.setFlat(True)
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.clicked.connect(self.toggle)
        self.layout.addWidget(self.btn_toggle)

        self.header_label = QLabel(title)
        theme = ThemeManager.get_current_theme_colors()
        self.header_label.setStyleSheet(f"font-size: {UIConstants.FONT_SIZE_SECTION_HEADER}px; font-weight: bold; color: {theme['text_main']};")
        self.header_label.setCursor(Qt.CursorShape.PointingHandCursor)
        
        def label_press(e):
            if e.button() == Qt.MouseButton.LeftButton:
                self.toggle()
                return
            QLabel.mousePressEvent(self.header_label, e)

        self.header_label.mousePressEvent = label_press
        self.layout.addWidget(self.header_label)

        self.layout.addStretch()
        
        if action_widget:
            self.layout.addWidget(action_widget)

        # 2. Context Menu Setup (requires children to exist)
        if on_context_menu:
            self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.customContextMenuRequested.connect(on_context_menu)
            
            # Ensure children also propagate the context menu request
            self.btn_toggle.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.btn_toggle.customContextMenuRequested.connect(on_context_menu)
            self.header_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.header_label.customContextMenuRequested.connect(on_context_menu)

        self._update_ui_state()

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
