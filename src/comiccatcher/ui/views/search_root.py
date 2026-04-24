# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, 
    QGroupBox, QListWidget, QListWidgetItem, QStyle, QApplication, QProgressBar
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QIcon
from comiccatcher.ui.theme_manager import ThemeManager, UIConstants
from comiccatcher.ui.views.base_browser import BaseBrowserView

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
        self.btn_pin = QPushButton()
        self.btn_pin.setObjectName("pin_button")
        self.btn_pin.setFixedSize(24, 24)
        self.btn_pin.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pin.setToolTip("Pin to favorites")
        self.btn_pin.clicked.connect(lambda: self.pin_requested.emit(self.text))
        self.btn_pin.setVisible(not is_pinned)
        layout.addWidget(self.btn_pin)

        # Remove Button
        self.btn_remove = QPushButton()
        self.btn_remove.setObjectName("icon_button")
        self.btn_remove.setFixedSize(24, 24)
        self.btn_remove.setIcon(ThemeManager.get_icon("close"))
        self.btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove.setToolTip("Remove")
        self.btn_remove.clicked.connect(lambda: self.remove_requested.emit(self.text, self.is_pinned))
        layout.addWidget(self.btn_remove)
        
        self.reapply_theme()

    def reapply_theme(self):
        theme = ThemeManager.get_current_theme_colors()
        self.label.setStyleSheet(f"color: {theme['text_main']}; font-size: {UIConstants.FONT_SIZE_BADGE}px;")
        
        # Use theme star color via SVG icon for reliable coloring
        self.btn_pin.setIcon(ThemeManager.get_icon("star", "star"))
        self.btn_pin.setStyleSheet("background: transparent; border: none;")
        
        # Ensure remove icon is colorized and visible
        self.btn_remove.setIcon(ThemeManager.get_icon("close", theme['text_dim']))
        self.btn_remove.setStyleSheet("background: transparent; border: none;")

class SearchRootView(BaseBrowserView):
    def __init__(self, on_search, on_pin=None, on_remove=None, on_clear=None):
        super().__init__()
        self.on_search = on_search
        self.on_pin = on_pin
        self.on_remove = on_remove
        self.on_clear = on_clear

        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.content_layout.setContentsMargins(60, 40, 60, 40)
        self.content_layout.setSpacing(20)

        # Title
        self.title_label = QLabel("Search Feed Catalog")
        self.content_layout.addWidget(self.title_label)

        # Search Bar
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter search query...")
        self.search_input.setMinimumHeight(45)
        self.search_input.returnPressed.connect(self._do_search)
        
        self.btn_search = QPushButton("Search")
        self.btn_search.setObjectName("primary_button")
        self.btn_search.setIcon(ThemeManager.get_icon("search", "white"))
        self.btn_search.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_search.setMinimumHeight(45)
        self.btn_search.setFixedWidth(120)
        self.btn_search.clicked.connect(self._do_search)
        
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.btn_search)
        self.content_layout.addLayout(search_layout)
        
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
        self.btn_clear.setObjectName("link_button")
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.clicked.connect(lambda: self.on_clear() if self.on_clear else None)
        recent_vbox.addWidget(self.btn_clear)
        
        # Pinned Searches (Favorites)
        self.pinned_group = QGroupBox("⭐ Favorites")
        pinned_vbox = QVBoxLayout(self.pinned_group)
        
        self.pinned_list = QListWidget()
        self.pinned_list.setObjectName("search_list")
        pinned_vbox.addWidget(self.pinned_list)
        
        # Spacer to match the height of the "Clear History" button in the other column
        self.favorites_spacer = QWidget()
        pinned_vbox.addWidget(self.favorites_spacer)

        # Install filters for custom navigation
        self.search_input.installEventFilter(self)
        self.recent_list.installEventFilter(self)
        self.pinned_list.installEventFilter(self)
        
        h_layout.addWidget(self.recent_group, 1)
        h_layout.addWidget(self.pinned_group, 1)
        self.content_layout.addLayout(h_layout)

        # Progress Indicator (using base class overlay if possible, or keeping local)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0) # Indeterminate
        self.progress.setFixedHeight(UIConstants.PROGRESS_BAR_HEIGHT)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        self.content_layout.addWidget(self.progress)
        
        self.reapply_theme()

    def reapply_theme(self):
        if not hasattr(self, 'title_label'):
            return
        super().reapply_theme()
        theme = ThemeManager.get_current_theme_colors()
        s = UIConstants.scale
        self.title_label.setStyleSheet(f"font-size: {UIConstants.FONT_SIZE_SEARCH_TITLE}px; font-weight: bold; color: {theme['text_main']};")
        
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                font-size: {UIConstants.FONT_SIZE_SEARCH_INPUT}px; 
                border-radius: {s(6)}px; 
                background-color: {theme['bg_sidebar']}; 
                color: {theme['text_main']}; 
                border: {max(1, s(1))}px solid {theme['border']}; 
                padding-left: {s(10)}px;
            }}
            QLineEdit:focus {{
                border: {max(2, s(2))}px solid {theme['accent']};
            }}
        """)

        # Shared list styling with focus indicator
        list_style = f"""
            QListWidget {{
                background-color: {theme['bg_sidebar']};
                border: {max(1, s(1))}px solid {theme['border']};
                border-radius: {s(8)}px;
                padding: {s(5)}px;
                color: {theme['text_main']};
                outline: none;
            }}
            QListWidget:focus {{
                border: {max(2, s(2))}px solid {theme['accent']};
            }}
            QListWidget::item {{
                padding: 0px;
                border-bottom: {max(1, s(1))}px solid {theme['border']};
            }}
            QListWidget::item:selected {{
                background-color: {theme['bg_item_selected']};
            }}
        """
        self.recent_list.setStyleSheet(list_style)
        self.pinned_list.setStyleSheet(list_style)

        group_style = f"""
            QGroupBox {{
                border: none;
                margin-top: {s(20)}px;
                font-weight: bold;
                font-size: {UIConstants.FONT_SIZE_BADGE}px;
                color: {theme['text_dim']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 {s(5)}px;
            }}
        """
        self.recent_group.setStyleSheet(group_style)
        self.pinned_group.setStyleSheet(group_style)

        # Primary button is mostly handled by global stylesheet, but we can refine font size here
        self.btn_search.setStyleSheet(f"font-size: {UIConstants.FONT_SIZE_SEARCH_INPUT}px; border-radius: {s(6)}px; font-weight: bold;")

        self.btn_clear.setStyleSheet(f"font-size: {UIConstants.FONT_SIZE_BADGE}px; text-align: right; color: {theme['accent']}; background: transparent; border: none;")
        
        # Ensure the spacer matches the button height for symmetry
        self.favorites_spacer.setFixedHeight(self.btn_clear.sizeHint().height())

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
            item.setSizeHint(QSize(0, UIConstants.SEARCH_ITEM_HEIGHT))
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
            item.setSizeHint(QSize(0, UIConstants.SEARCH_ITEM_HEIGHT))
            self.pinned_list.addItem(item)
            self.pinned_list.setItemWidget(item, widget)
            
        self.btn_clear.setVisible(len(history) > 0)

    def clear_input(self):
        """Clears the search text input."""
        self.search_input.clear()

    def _do_search(self):
        q = self.search_input.text().strip()
        if q:
            self.on_search(q)
            
    def _do_search_query(self, q):
        self.search_input.setText(q)
        self.on_search(q)

    def mousePressEvent(self, event):
        """Clicking background returns focus to the search box."""
        self.search_input.setFocus()
        super().mousePressEvent(event)

    def _handle_list_action_keys(self, list_widget, key, is_pinned_list):
        """Internal helper to handle action keys (Enter, D, P) on a list widget."""
        item = list_widget.currentItem()
        if not item:
            return False
            
        widget = list_widget.itemWidget(item)
        if not widget or not hasattr(widget, 'text'):
            return False
            
        query = widget.text
        
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._do_search_query(query)
            return True
        elif key == Qt.Key.Key_D:
            if self.on_remove:
                self.on_remove(query, is_pinned_list)
            return True
        elif key == Qt.Key.Key_P and not is_pinned_list:
            if self.on_pin:
                self.on_pin(query)
            return True
            
        return False

    def eventFilter(self, obj, event):
        if event.type() == event.Type.KeyPress:
            key = event.key()
            
            # 1. Intercept H and / everywhere in this view
            if key == Qt.Key.Key_H:
                self.toggle_help_popover()
                return True
            if key == Qt.Key.Key_Slash and obj != self.search_input:
                self.search_input.setFocus()
                self.search_input.selectAll()
                return True

            # 2. Navigation from Search Box
            if obj == self.search_input:
                if key == Qt.Key.Key_Down:
                    # Move to history if it has items
                    if self.recent_list.count() > 0:
                        self.recent_list.setFocus()
                        # Explicitly set current and selected for visible highlight
                        self.recent_list.setCurrentRow(0)
                        if (item := self.recent_list.item(0)):
                            item.setSelected(True)
                        return True
                    # Otherwise try pinned
                    elif self.pinned_list.count() > 0:
                        self.pinned_list.setFocus()
                        self.pinned_list.setCurrentRow(0)
                        if (item := self.pinned_list.item(0)):
                            item.setSelected(True)
                        return True

            # 3. Navigation and Actions from Recent List (History)
            elif obj == self.recent_list:
                if self._handle_list_action_keys(self.recent_list, key, False):
                    return True
                if key == Qt.Key.Key_Up and self.recent_list.currentRow() <= 0:
                    self.recent_list.setCurrentRow(-1)
                    self.recent_list.clearSelection()
                    self.search_input.setFocus()
                    return True
                elif key == Qt.Key.Key_Right:
                    if self.pinned_list.count() > 0:
                        self.pinned_list.setFocus()
                        self.pinned_list.setCurrentRow(0)
                        if (item := self.pinned_list.item(0)):
                            item.setSelected(True)
                        return True

            # 4. Navigation and Actions from Pinned List (Favorites)
            elif obj == self.pinned_list:
                if self._handle_list_action_keys(self.pinned_list, key, True):
                    return True
                if key == Qt.Key.Key_Up and self.pinned_list.currentRow() <= 0:
                    self.pinned_list.setCurrentRow(-1)
                    self.pinned_list.clearSelection()
                    self.search_input.setFocus()
                    return True
                elif key == Qt.Key.Key_Left:
                    if self.recent_list.count() > 0:
                        self.recent_list.setFocus()
                        self.recent_list.setCurrentRow(0)
                        if (item := self.recent_list.item(0)):
                            item.setSelected(True)
                        return True

        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        # Most keys are handled by eventFilter or super, 
        # but we catch base cases here if focus is somehow lost.
        if event.key() == Qt.Key.Key_H:
            self.toggle_help_popover()
            return
        elif event.key() == Qt.Key.Key_Slash:
            self.search_input.setFocus()
            self.search_input.selectAll()
            return
        super().keyPressEvent(event)

    def get_help_popover_title(self):
        return "Search Dashboard"

    def get_help_popover_sections(self):
        sections = self.get_common_help_sections()
        sections.insert(0, ("SEARCH DASHBOARD", [
            ("/", "Focus search box"),
            ("Enter", "Perform search with selected"),
            ("Down", "Move from search box to list"),
            ("Up", "Move from list back to search box"),
            ("Left / Right", "Switch between History and Favorites"),
            ("D", "Delete selected item"),
            ("P", "Pin to favorites (History only)"),
        ]))
        return sections
