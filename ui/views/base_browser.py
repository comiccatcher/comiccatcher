from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QProgressBar, QSizePolicy, QFrame
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QTimer
from ui.theme_manager import ThemeManager, UIConstants

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

        # 2. Status & Progress Area (Floating Overlay)
        self.status_area = QWidget(self)
        self.status_area.setFixedHeight(UIConstants.STATUS_HEIGHT)
        self.status_area.setVisible(False)
        self.status_area.setObjectName("status_overlay")
        self.status_layout = QHBoxLayout(self.status_area)
        self.status_layout.setContentsMargins(UIConstants.LAYOUT_MARGIN_DEFAULT, 0, UIConstants.LAYOUT_MARGIN_DEFAULT, 0)
        
        self.status_label = QLabel("")
        self.status_layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(UIConstants.PROGRESS_BAR_HEIGHT)
        self.progress_bar.setTextVisible(False)
        self.status_layout.addWidget(self.progress_bar, 1)
        
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
        
        self.btn_sel_cancel = QPushButton("Cancel")
        self.btn_sel_cancel.setObjectName("secondary_button")
        
        self.label_sel_count = QLabel("0 items selected")
        self.label_sel_count.setObjectName("status_label")
        
        self.selection_layout.addWidget(self.btn_sel_cancel)
        self.selection_layout.addWidget(self.label_sel_count)
        self.selection_layout.addStretch()
        
        self.layout.addWidget(self.selection_bar)
        
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
                    padding: 4px; 
                    background-color: transparent;
                    border-radius: 4px;
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
            """

            self.status_label.setStyleSheet(f"font-size: {UIConstants.FONT_SIZE_STATUS}px; font-weight: bold; color: {theme['text_dim']};")
            self.label_sel_count.setStyleSheet(f"font-weight: bold; font-size: 11px; color: {theme['text_main']};")
            self.status_area.setStyleSheet(f"QWidget#status_overlay {{ background-color: {theme['bg_sidebar']}; border-bottom: 1px solid {theme['border']}; }}")

            for btn, icon_name in self._header_buttons.items():
                btn.setIcon(ThemeManager.get_icon(icon_name))
                btn.setStyleSheet(btn_style)

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
        self.status_area.setVisible(bool(text) or busy)
        self.progress_bar.setVisible(busy)
        if bool(text) or busy:
            self.status_area.raise_()

    def create_header_button(self, icon_name: str, tooltip: str, checkable: bool = False) -> QPushButton:
        """Helper to create standardized header buttons."""
        btn = QPushButton()
        btn.setCheckable(checkable)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedWidth(UIConstants.HEADER_BUTTON_SIZE)
        btn.setFixedHeight(UIConstants.HEADER_BUTTON_SIZE)
        
        self._header_buttons[btn] = icon_name
        
        # Apply current theme immediately
        theme = ThemeManager.get_current_theme_colors()
        btn.setIcon(ThemeManager.get_icon(icon_name))
        
        return btn

    def toggle_selection_mode(self, enabled: bool):
        """Standardized selection mode toggle UI."""
        self.selection_bar.setVisible(enabled)
        if hasattr(self, 'btn_select'):
            self.btn_select.setChecked(enabled)

    def _style_segmented_group(self, buttons: list[QPushButton]):
        """Applies a 'segmented' (joined) look to a list of buttons."""
        if not buttons: return
        theme = ThemeManager.get_current_theme_colors()
        s = UIConstants.scale
        
        base_style = f"""
            QPushButton {{ 
                border: 1px solid {theme['border']};
                padding: {s(6)}px; 
                background-color: transparent;
                margin: 0px;
            }}
            QPushButton:hover {{ 
                background-color: {theme['bg_item_hover']}; 
            }}
            QPushButton:checked {{
                background-color: {theme['bg_item_selected']};
                border: 1px solid {theme['accent']};
            }}
        """
        
        for i, btn in enumerate(buttons):
            btn.setIconSize(QSize(s(18), s(18)))
            rad = f"{s(4)}px"
            if len(buttons) == 1:
                btn.setStyleSheet(base_style + f"QPushButton {{ border-radius: {rad}; }}")
            elif i == 0:
                btn.setStyleSheet(base_style + f"QPushButton {{ border-top-left-radius: {rad}; border-bottom-left-radius: {rad}; border-top-right-radius: 0px; border-bottom-right-radius: 0px; border-right: none; }}")
            elif i == len(buttons) - 1:
                btn.setStyleSheet(base_style + f"QPushButton {{ border-top-right-radius: {rad}; border-bottom-right-radius: {rad}; border-top-left-radius: 0px; border-bottom-left-radius: 0px; }}")
            else:
                btn.setStyleSheet(base_style + f"QPushButton {{ border-radius: 0px; border-right: none; }}")
