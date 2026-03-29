from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, 
    QGroupBox, QListWidget, QListWidgetItem, QStyle, QApplication, QProgressBar
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from ui.theme_manager import ThemeManager, UIConstants

class SearchItemWidget(QWidget):
    """Custom widget for history/pinned items with buttons."""
    clicked = pyqtSignal(str)
    pin_requested = pyqtSignal(str)
    remove_requested = pyqtSignal(str, bool) # query, from_pinned

    def __init__(self, text, is_pinned=False):
        super().__init__()
        self.text = text
        self.is_pinned = is_pinned
        self.setFixedHeight(36)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Main Label
        self.label = QLabel(text)
        self.label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.label.setObjectName("search_item_label")
        # Clickable label logic
        self.label.mousePressEvent = lambda e: self.clicked.emit(self.text)
        layout.addWidget(self.label, 1)

        # Pin Button (Star) - Only show in history, not in pinned list itself
        self.btn_pin = QPushButton("★")
        self.btn_pin.setObjectName("pin_button")
        self.btn_pin.setFlat(True)
        self.btn_pin.setFixedSize(24, 24)
        self.btn_pin.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pin.setToolTip("Pin to favorites")
        self.btn_pin.clicked.connect(lambda: self.pin_requested.emit(self.text))
        self.btn_pin.setVisible(not is_pinned)
        layout.addWidget(self.btn_pin)

        # Remove Button
        self.btn_remove = QPushButton()
        self.btn_remove.setFlat(True)
        self.btn_remove.setFixedSize(24, 24)
        self.btn_remove.setIcon(ThemeManager.get_icon("close"))
        self.btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove.setToolTip("Remove")
        self.btn_remove.clicked.connect(lambda: self.remove_requested.emit(self.text, self.is_pinned))
        layout.addWidget(self.btn_remove)
        
        self.reapply_theme()

    def reapply_theme(self):
        theme = ThemeManager.get_current_theme_colors()
        self.label.setStyleSheet(f"color: {theme['text_main']}; font-size: 13px;")
        self.btn_pin.setStyleSheet(f"color: {theme['accent']}; border: none; background: transparent;")
        self.btn_remove.setIcon(ThemeManager.get_icon("close"))
        self.btn_remove.setStyleSheet("border: none; background: transparent;")

class SearchRootView(QWidget):
    def __init__(self, on_search, on_pin=None, on_remove=None, on_clear=None):
        super().__init__()
        self.on_search = on_search
        self.on_pin = on_pin
        self.on_remove = on_remove
        self.on_clear = on_clear

        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.layout.setContentsMargins(60, 40, 60, 40)
        self.layout.setSpacing(20)

        # Title
        self.title_label = QLabel("Search Feed Catalog")
        self.layout.addWidget(self.title_label)

        # Search Bar
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter search query...")
        self.search_input.setMinimumHeight(45)
        self.search_input.returnPressed.connect(self._do_search)
        
        self.btn_search = QPushButton("Search")
        self.btn_search.setObjectName("primary_button")
        self.btn_search.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_search.setMinimumHeight(45)
        self.btn_search.setFixedWidth(120)
        self.btn_search.clicked.connect(self._do_search)
        
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.btn_search)
        self.layout.addLayout(search_layout)
        
        # Recent / Pinned Sections
        h_layout = QHBoxLayout()
        h_layout.setSpacing(40)
        
        # Recent Searches (History)
        self.recent_group = QGroupBox("🕒 History")
        recent_vbox = QVBoxLayout(self.recent_group)
        
        self.recent_list = QListWidget()
        self.recent_list.setObjectName("search_list")
        recent_vbox.addWidget(self.recent_list)
        
        self.btn_clear = QPushButton("Clear History")
        self.btn_clear.setFlat(True)
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.clicked.connect(lambda: self.on_clear() if self.on_clear else None)
        recent_vbox.addWidget(self.btn_clear)
        
        # Pinned Searches (Favorites)
        self.pinned_group = QGroupBox("⭐ Favorites")
        pinned_vbox = QVBoxLayout(self.pinned_group)
        
        self.pinned_list = QListWidget()
        self.pinned_list.setObjectName("search_list")
        pinned_vbox.addWidget(self.pinned_list)
        
        h_layout.addWidget(self.recent_group, 1)
        h_layout.addWidget(self.pinned_group, 1)
        self.layout.addLayout(h_layout)

        # Progress Indicator
        self.progress = QProgressBar()
        self.progress.setRange(0, 0) # Indeterminate
        self.progress.setFixedHeight(UIConstants.PROGRESS_BAR_HEIGHT)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        self.layout.addWidget(self.progress)
        
        self.reapply_theme()

    def reapply_theme(self):
        theme = ThemeManager.get_current_theme_colors()
        self.title_label.setStyleSheet(f"font-size: 28px; font-weight: bold; color: {theme['text_main']};")
        self.search_input.setStyleSheet(f"font-size: 16px; border-radius: 6px; background-color: {theme['bg_sidebar']}; color: {theme['text_main']}; border: 1px solid {theme['border']}; padding-left: 10px;")
        
        # Primary button is mostly handled by global stylesheet, but we can refine font size here
        self.btn_search.setStyleSheet("font-size: 16px; border-radius: 6px; font-weight: bold;")
        
        self.btn_clear.setStyleSheet(f"font-size: 11px; text-align: right; color: {theme['accent']}; background: transparent; border: none;")
        
        # Refresh current list widgets
        for i in range(self.recent_list.count()):
            item = self.recent_list.item(i)
            widget = self.recent_list.itemWidget(item)
            if hasattr(widget, 'reapply_theme'):
                widget.reapply_theme()
                
        for i in range(self.pinned_list.count()):
            item = self.pinned_list.item(i)
            widget = self.pinned_list.itemWidget(item)
            if hasattr(widget, 'reapply_theme'):
                widget.reapply_theme()

    def set_loading(self, loading: bool):
        self.progress.setVisible(loading)
        self.search_input.setEnabled(not loading)

    def update_data(self, history, pinned):
        """Re-populate the history and pinned lists."""
        self.recent_list.clear()
        for item_text in history:
            item = QListWidgetItem(self.recent_list)
            widget = SearchItemWidget(item_text, is_pinned=False)
            widget.clicked.connect(self._do_search_query)
            widget.pin_requested.connect(self.on_pin)
            widget.remove_requested.connect(self.on_remove)
            
            # Use fixed size hint to ensure layout consistency
            item.setSizeHint(QSize(0, 36))
            self.recent_list.addItem(item)
            self.recent_list.setItemWidget(item, widget)

        self.pinned_list.clear()
        for item_text in pinned:
            item = QListWidgetItem(self.pinned_list)
            widget = SearchItemWidget(item_text, is_pinned=True)
            widget.clicked.connect(self._do_search_query)
            widget.pin_requested.connect(self.on_pin) # Will act as Unpin
            widget.remove_requested.connect(self.on_remove)
            
            # Use fixed size hint to ensure layout consistency
            item.setSizeHint(QSize(0, 36))
            self.pinned_list.addItem(item)
            self.pinned_list.setItemWidget(item, widget)
            
        self.btn_clear.setVisible(len(history) > 0)

    def _do_search(self):
        q = self.search_input.text().strip()
        if q:
            self.on_search(q)
            
    def _do_search_query(self, q):
        self.search_input.setText(q)
        self.on_search(q)
