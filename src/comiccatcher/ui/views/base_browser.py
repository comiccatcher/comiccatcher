# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

from typing import Optional, Callable
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QProgressBar, QSizePolicy, QFrame
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QTimer
from comiccatcher.ui.theme_manager import ThemeManager, UIConstants

class BaseBrowserView(QWidget):
    """
    Base class for browser-style views (Library and Feed Browser).
    Provides a standardized header, status bar, and selection bar.
    
    Layout Structure:
    1. Header Bar (Top)
    2. Status/Progress Area (Overlay below Header)
    3. Content Area (Flexible)
    4. Selection Bar (Bottom, hidden by default)
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._header_buttons = {} # {btn: icon_name}
        self._selection_buttons = {} # {btn: icon_name}
        self._selection_mode = False
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 1. Top Header Bar
        self.header_widget = QWidget()
        self.header_widget.setObjectName("top_header")
        self.header_widget.setFixedHeight(UIConstants.HEADER_HEIGHT)
        self.header_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.header_layout = QHBoxLayout(self.header_widget)
        self.header_layout.setContentsMargins(UIConstants.LAYOUT_MARGIN_DEFAULT, 0, UIConstants.LAYOUT_MARGIN_DEFAULT, 0)
        self.layout.addWidget(self.header_widget)

        # 1.1 Left Group (Status)
        self.left_group = QWidget()
        self.left_layout = QHBoxLayout(self.left_group)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.left_layout.addWidget(self.status_label)
        self.header_layout.addWidget(self.left_group)

        # 1.2 Center Group (Navigation/Paging) - Stretches to keep centered
        self.header_layout.addStretch(1)
        
        self.center_group = QWidget()
        self.center_layout = QHBoxLayout(self.center_group)
        self.center_layout.setContentsMargins(0, 0, 0, 0)
        self.center_layout.setSpacing(0)
        self.header_layout.addWidget(self.center_group)
        
        self.header_layout.addStretch(1)

        # 1.3 Right Group (Actions/Modes) - Right aligned
        self.right_group = QWidget()
        self.right_layout = QHBoxLayout(self.right_group)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_layout.setSpacing(UIConstants.scale(10))
        self.header_layout.addWidget(self.right_group)

        # 2. Status & Progress Area (Floating Overlay)
        self.status_area = QWidget(self)
        self.status_area.setFixedHeight(UIConstants.STATUS_HEIGHT)
        self.status_area.setVisible(False)
        self.status_area.setObjectName("status_overlay")
        self.status_layout = QVBoxLayout(self.status_area)
        self.status_layout.setContentsMargins(0, 0, 0, 0)
        self.status_layout.setSpacing(0)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(UIConstants.PROGRESS_BAR_HEIGHT)
        self.progress_bar.setTextVisible(False)
        self.status_layout.addWidget(self.progress_bar)
        
        self.status_area.raise_()

        # 3. Content Area (Flexible)
        self.content_container = QWidget()
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        self.layout.addWidget(self.content_container, 1)

        # 4. Selection Action Bar (Bottom)
        self.selection_bar = QWidget()
        self.selection_bar.setObjectName("selection_bar")
        self.selection_bar.setFixedHeight(UIConstants.HEADER_HEIGHT)
        self.selection_bar.setVisible(False)
        self.selection_layout = QHBoxLayout(self.selection_bar)
        self.selection_layout.setContentsMargins(UIConstants.LAYOUT_MARGIN_DEFAULT, UIConstants.SECTION_HEADER_MARGIN_TOP, UIConstants.LAYOUT_MARGIN_DEFAULT, UIConstants.SECTION_HEADER_MARGIN_TOP)
        self.selection_layout.setSpacing(UIConstants.LAYOUT_MARGIN_DEFAULT)
        
        self.btn_sel_cancel = self.create_selection_button("Cancel", "close", lambda: self.toggle_selection_mode(False))
        
        self.label_sel_count = QLabel("0 items selected")
        self.label_sel_count.setObjectName("status_label")
        
        self.selection_layout.addWidget(self.btn_sel_cancel)
        self.selection_layout.addWidget(self.label_sel_count)
        self.selection_layout.addStretch()
        
        self.layout.addWidget(self.selection_bar)

        # 5. Bottom Status Bar (VS Code style)
        self.bottom_status_bar = QFrame()
        self.bottom_status_bar.setObjectName("bottom_status_bar")
        self.bottom_status_layout = QHBoxLayout(self.bottom_status_bar)
        self.bottom_status_layout.setContentsMargins(UIConstants.LAYOUT_MARGIN_DEFAULT, 0, UIConstants.LAYOUT_MARGIN_DEFAULT, 0)
        self.bottom_status_layout.setSpacing(0)
        
        self.bottom_status_label = QLabel("")
        self.bottom_status_label.setObjectName("bottom_status_label")
        self.bottom_status_layout.addWidget(self.bottom_status_label)
        
        self.layout.addWidget(self.bottom_status_bar)
        
        # Initial theme application
        QTimer.singleShot(0, self.reapply_theme)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.status_area.setGeometry(0, UIConstants.HEADER_HEIGHT, self.width(), UIConstants.STATUS_HEIGHT)
        self.status_area.raise_()

    def reapply_theme(self):
        """Refreshes all theme-dependent styles and icons."""
        if hasattr(self, "_in_reapply_theme") and self._in_reapply_theme:
            return
        self._in_reapply_theme = True

        try:
            if not self.isVisible() and not self.parent():
                return

            theme = ThemeManager.get_current_theme_colors()
            
            btn_style = f"""
                QPushButton {{ 
                    border: none; 
                    padding: {UIConstants.scale(4)}px; 
                    background-color: transparent;
                    border-radius: {UIConstants.scale(4)}px;
                }}
                QPushButton:hover {{ 
                    background-color: {theme['bg_item_hover']}; 
                }}
                QPushButton:checked {{
                    background-color: {theme['bg_item_selected']};
                }}
                QPushButton:disabled {{ 
                    opacity: 0.3; 
                }}
                QPushButton::menu-indicator {{
                    subcontrol-origin: border;
                    subcontrol-position: bottom right;
                    right: {UIConstants.scale(2)}px;
                    bottom: {UIConstants.scale(2)}px;
                    width: {UIConstants.scale(6)}px;
                    height: {UIConstants.scale(6)}px;
                }}
            """

            self.status_label.setStyleSheet(f"font-size: {UIConstants.FONT_SIZE_STATUS}px; font-weight: bold; color: {theme['text_dim']};")
            self.label_sel_count.setStyleSheet(f"font-weight: bold; font-size: {UIConstants.FONT_SIZE_STATUS}px; color: {theme['text_main']};")
            self.status_area.setStyleSheet(f"QWidget#status_overlay {{ background-color: {theme['bg_sidebar']}; border-bottom: {max(1, UIConstants.scale(1))}px solid {theme['border']}; }}")

            self.bottom_status_bar.setFixedHeight(UIConstants.BOTTOM_BAR_HEIGHT)
            self.bottom_status_bar.setStyleSheet(f"""
                QFrame#bottom_status_bar {{ 
                    background-color: {theme['bg_sidebar']}; 
                    border-top: {max(1, UIConstants.scale(1))}px solid {theme['border']};
                }}
            """)
            self.bottom_status_label.setStyleSheet(f"""
                QLabel#bottom_status_label {{ 
                    font-size: {UIConstants.FONT_SIZE_BOTTOM_BAR}px; 
                    font-weight: bold; 
                    color: {theme['text_dim']};
                }}
            """)

            for btn, icon_name in self._header_buttons.items():
                btn.setIcon(ThemeManager.get_icon(icon_name))
                btn.setStyleSheet(btn_style)

            for btn, icon_name in self._selection_buttons.items():
                if icon_name:
                    # In selection bar, use text_dim for inactive state visual if needed, 
                    # but for buttons with text #secondary_button styles it correctly.
                    # We just need to load the icon.
                    btn.setIcon(ThemeManager.get_icon(icon_name, "text_dim" if not btn.isEnabled() else "accent"))

            self.header_widget.update()
            self.selection_bar.update()
        finally:
            self._in_reapply_theme = False

    def add_content_widget(self, widget: QWidget, stretch: int = 1):
        """Standardized helper to add main content."""
        self.content_layout.addWidget(widget, stretch)

    def set_status(self, text: str, busy: bool = False):
        """Standardized status/progress display."""
        self.status_label.setText(text)
        self.status_area.setVisible(busy)
        self.progress_bar.setVisible(busy)
        if busy:
            self.status_area.raise_()

    def create_action_button(self, text: str, callback: Optional[Callable] = None, object_name: str = "link_button") -> QPushButton:
        """Creates a standardized, themed action button (e.g., 'See All')."""
        btn = QPushButton(text)
        btn.setObjectName(object_name) # Triggers themed style from ThemeManager
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if callback:
            btn.clicked.connect(callback)
        return btn

    def create_selection_button(self, text: str, icon_name: str, callback: Optional[Callable] = None) -> QPushButton:
        """Creates a standardized, themed selection bar button."""
        btn = QPushButton(text)
        btn.setObjectName("secondary_button") # Unify all selection buttons to secondary
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if callback:
            btn.clicked.connect(callback)
        
        self._selection_buttons[btn] = icon_name
        
        btn.setIcon(ThemeManager.get_icon(icon_name, "accent"))
        return btn

    def create_header_button(self, icon_name: str, tooltip: str, checkable: bool = False) -> QPushButton:
        """Helper to create standardized header buttons."""
        btn = QPushButton()
        btn.setObjectName("icon_button")
        btn.setCheckable(checkable)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedWidth(UIConstants.HEADER_BUTTON_SIZE)
        btn.setFixedHeight(UIConstants.HEADER_BUTTON_SIZE)
        btn.setIconSize(QSize(UIConstants.ICON_SIZE_STANDARD, UIConstants.ICON_SIZE_STANDARD))
        
        self._header_buttons[btn] = icon_name
        
        # Apply current theme immediately
        btn.setIcon(ThemeManager.get_icon(icon_name))
        
        return btn

    def toggle_selection_mode(self, enabled: bool):
        """Standardized selection mode toggle UI."""
        self._selection_mode = enabled
        self.selection_bar.setVisible(enabled)
        if hasattr(self, 'btn_select'):
            self.btn_select.setChecked(enabled)

    def keyPressEvent(self, event):
        """Handle Escape key to exit selection mode."""
        if event.key() == Qt.Key.Key_Escape and self._selection_mode:
            self.toggle_selection_mode(False)
            event.accept()
        else:
            super().keyPressEvent(event)

    def set_all_sections_collapsed(self, collapsed: bool):
        """Universal helper to expand/collapse all CollapsibleSection children."""
        from comiccatcher.ui.components.collapsible_section import CollapsibleSection
        for section in self.findChildren(CollapsibleSection):
            section.set_collapsed(collapsed)

    def _style_segmented_group(self, buttons: list[QPushButton]):
        """Applies a 'segmented' (joined) look to a list of buttons using global stylesheets."""
        if not buttons: return
        
        for i, btn in enumerate(buttons):
            btn.setIconSize(QSize(UIConstants.ICON_SIZE_STANDARD, UIConstants.ICON_SIZE_STANDARD))
            # Remove any specific object name that might conflict with [segment] styling
            if btn.objectName() == "icon_button":
                btn.setObjectName("")
            
            # Ensure no inline stylesheet overrides our margin-left logic
            btn.setStyleSheet("")
            
            if len(buttons) == 1:
                btn.setProperty("segment", "single")
            elif i == 0:
                btn.setProperty("segment", "left")
            elif i == len(buttons) - 1:
                btn.setProperty("segment", "right")
            else:
                btn.setProperty("segment", "mid")
                
            btn.style().unpolish(btn)
            btn.style().polish(btn)
