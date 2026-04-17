# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

from typing import Optional, List, Set
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal, QSize

from comiccatcher.ui.theme_manager import ThemeManager, UIConstants

class PagingControl(QWidget):
    """
    Encapsulated pagination control for OPDS feeds.
    Contains First, Previous, Page Label, Next, and Last buttons.
    """
    # Emits the relation string: "first", "previous", "next", or "last"
    nav_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self.reapply_theme()

    def _setup_ui(self):
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # 1. Create Widgets
        self.btn_first = self._create_nav_button("chevrons_left", "First Page", "first")
        self.btn_prev = self._create_nav_button("chevron_left", "Previous Page", "previous")
        
        self.page_label = QLabel("Page 1")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_label.setStyleSheet(f"font-weight: bold; margin: 0 {UIConstants.SECTION_HEADER_SPACING}px;")
        
        self.btn_next = self._create_nav_button("chevron_right", "Next Page", "next")
        self.btn_last = self._create_nav_button("chevrons_right", "Last Page", "last")

        self._buttons = [self.btn_first, self.btn_prev, self.btn_next, self.btn_last]

        # 2. Add to Layout
        self.layout.addWidget(self.btn_first)
        self.layout.addWidget(self.btn_prev)
        self.layout.addWidget(self.page_label)
        self.layout.addWidget(self.btn_next)
        self.layout.addWidget(self.btn_last)

    def _create_nav_button(self, icon_name: str, tooltip: str, rel: str) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("icon_button")
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedWidth(UIConstants.HEADER_BUTTON_SIZE)
        btn.setFixedHeight(UIConstants.HEADER_BUTTON_SIZE)
        btn.setIcon(ThemeManager.get_icon(icon_name))
        btn.clicked.connect(lambda: self.nav_requested.emit(rel))
        return btn

    def set_buttons_visible(self, visible: bool):
        """Shows or hides the navigation buttons (used when switching to scrolled mode)."""
        for btn in self._buttons:
            btn.setVisible(visible)

    def set_text(self, text: str):
        """Directly sets the text of the page label."""
        self.page_label.setText(text)

    def update_state(self, current_page: int, total_pages: Optional[int], available_rels: Set[str]):
        """Updates the label and button enabled states based on current feed data."""
        page_text = f"Page {current_page}"
        if total_pages:
            page_text += f" (of {total_pages})"
        self.page_label.setText(page_text)
        
        self.btn_first.setEnabled("first" in available_rels)
        self.btn_prev.setEnabled("previous" in available_rels)
        self.btn_next.setEnabled("next" in available_rels)
        self.btn_last.setEnabled("last" in available_rels)

    def set_loading_state(self, rel: str, current_page: int, total_pages: Optional[int]):
        """Optimistically updates the UI to reflect a pending page load."""
        target = current_page
        if rel == "first": target = 1
        elif rel == "last": target = total_pages or current_page
        elif rel == "next": target = current_page + 1
        elif rel == "previous": target = max(1, current_page - 1)
        
        page_text = f"Loading Page {target}..."
        if total_pages:
            page_text = f"Page {target} (of {total_pages})"
            
        self.page_label.setText(page_text)
        
        # Disable all navigation while loading
        for btn in [self.btn_first, self.btn_prev, self.btn_next, self.btn_last]:
            btn.setEnabled(False)

    def reapply_theme(self):
        """Refreshes themed icons and stylesheets."""
        theme = ThemeManager.get_current_theme_colors()
        s = UIConstants.scale
        
        # Sync label font size
        self.page_label.setStyleSheet(f"font-weight: bold; font-size: {UIConstants.FONT_SIZE_PAGING}px; margin: 0 {UIConstants.SECTION_HEADER_SPACING}px; color: {theme['text_main']};")
        
        # Standard icon button style
        btn_style = f"""
            QPushButton {{ 
                border: none; 
                padding: {s(4)}px; 
                background-color: transparent;
            }} 
            QPushButton:hover {{ 
                background-color: {theme['bg_item_hover']}; 
                border-radius: {s(4)}px; 
            }}
            QPushButton:disabled {{
                opacity: 0.3;
            }}
        """
        
        icon_map = {
            self.btn_first: "chevrons_left",
            self.btn_prev: "chevron_left",
            self.btn_next: "chevron_right",
            self.btn_last: "chevrons_right"
        }
        
        for btn, icon_name in icon_map.items():
            btn.setStyleSheet(btn_style)
            btn.setIcon(ThemeManager.get_icon(icon_name))
            btn.setIconSize(QSize(s(20), s(20)))
