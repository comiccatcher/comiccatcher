from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSizePolicy
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from typing import Optional, Callable
from comiccatcher.ui.theme_manager import ThemeManager, UIConstants

class CollapsibleSection(QWidget):
    """
    A unified reusable component for collapsible sections with headers.
    Used by both Library View and Feed Browser.
    """
    toggled = pyqtSignal(bool) # Emits the new is_collapsed state

    def __init__(self, title: str, content_widget: QWidget, action_widget: Optional[QWidget] = None, 
                 is_collapsed: bool = False, on_context_menu: Optional[Callable] = None, parent=None):
        super().__init__(parent)
        self.content_widget = content_widget
        self._is_collapsed = is_collapsed

        self.setObjectName("series_section")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, UIConstants.SECTION_MARGIN_BOTTOM)
        self.layout.setSpacing(0)

        # 1. Header Area
        s = UIConstants.scale
        self.header_widget = QWidget()
        self.header_widget.setFixedHeight(UIConstants.SECTION_HEADER_HEIGHT)
        self.header_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.header_widget.setObjectName("section_header")
        
        self.header_layout = QHBoxLayout(self.header_widget)
        self.header_layout.setContentsMargins(0, UIConstants.SECTION_HEADER_MARGIN_TOP, 0, 0)
        self.header_layout.setSpacing(UIConstants.SECTION_HEADER_SPACING)

        # Initialize children FIRST
        self.btn_toggle = QPushButton()
        self.btn_toggle.setObjectName("icon_button")
        self.btn_toggle.setIconSize(QSize(s(16), s(16)))
        self.btn_toggle.setFixedSize(UIConstants.TOGGLE_BUTTON_SIZE, UIConstants.TOGGLE_BUTTON_SIZE)
        self.btn_toggle.setFlat(True)
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.clicked.connect(self.toggle)
        self.header_layout.addWidget(self.btn_toggle)

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
        self.header_layout.addWidget(self.header_label)

        self.header_layout.addStretch()
        
        if action_widget:
            self.header_layout.addWidget(action_widget)

        self._on_context_menu = None
        if on_context_menu:
            self.on_context_menu = on_context_menu

        self.layout.addWidget(self.header_widget)
        if self.content_widget:
            self.layout.addWidget(self.content_widget)

        self._update_ui_state()

    @property
    def on_context_menu(self):
        return self._on_context_menu

    @on_context_menu.setter
    def on_context_menu(self, callback: Callable):
        """Standardized setter that connects the context menu signal to all header components."""
        self._on_context_menu = callback
        if not callback:
            return

        # Set on the main widget itself as well
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        try: self.customContextMenuRequested.disconnect()
        except: pass
        self.customContextMenuRequested.connect(callback)
        
        # Header components
        widgets = [self.header_widget, self.btn_toggle, self.header_label]
        for w in widgets:
            w.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            try: w.customContextMenuRequested.disconnect()
            except: pass
            w.customContextMenuRequested.connect(callback)

    def set_content_widget(self, widget: QWidget):
        """Standardized helper to set or update the content widget."""
        if self.content_widget:
            self.layout.removeWidget(self.content_widget)
        self.content_widget = widget
        self.layout.addWidget(self.content_widget)
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
        
        if self.content_widget:
            self.content_widget.setVisible(not self._is_collapsed)
            if self._is_collapsed:
                self.content_widget.setFixedHeight(0)
            else:
                # If the widget has a fixed height (like Ribbons or calculated Grids), 
                # don't reset it to standard maximums.
                if self.content_widget.minimumHeight() == self.content_widget.maximumHeight() and self.content_widget.minimumHeight() > 0:
                    pass # Keep fixed height
                else:
                    self.content_widget.setMinimumHeight(0)
                    self.content_widget.setMaximumHeight(16777215) # Default QWIDGET_SIZE_MAX

    def set_right_margin(self, margin: int):
        """Adjusts the right margin of the header, typically for scrollbar awareness."""
        m = self.header_layout.contentsMargins()
        self.header_layout.setContentsMargins(m.left(), m.top(), margin, m.bottom())
