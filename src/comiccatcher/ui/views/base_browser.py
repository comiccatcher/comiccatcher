# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

from typing import Optional, Callable
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QProgressBar, QSizePolicy, QFrame, QListWidget, QListView
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QTimer, QItemSelectionModel
from comiccatcher.ui.theme_manager import ThemeManager, UIConstants
from comiccatcher.ui.view_helpers import SectionControlMixin, HelpPopoverMixin
from comiccatcher.ui.components.keyboard_nav import KeyboardBrowserNavigator


class BaseBrowserView(QWidget, SectionControlMixin, HelpPopoverMixin):
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
        self._bulk_selection_buttons = {} # {btn: icon_name}
        self._bulk_selection_mode = False
        self.init_help_popover()
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # 1. Top Header Bar
        self.header_widget = QWidget()
        self.header_widget.setObjectName("top_header")
        self.header_widget.setFixedHeight(UIConstants.HEADER_HEIGHT)
        self.header_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.header_layout = QHBoxLayout(self.header_widget)
        self.header_layout.setContentsMargins(UIConstants.LAYOUT_MARGIN_DEFAULT, 0, UIConstants.LAYOUT_MARGIN_DEFAULT, 0)
        self.layout.addWidget(self.header_widget)

        # 4. Selection Action Bar (Top - just below header)
        self.selection_bar = QWidget()
        self.selection_bar.setObjectName("selection_bar")
        self.selection_bar.setFixedHeight(UIConstants.HEADER_HEIGHT)
        self.selection_bar.setVisible(False)
        self.selection_layout = QHBoxLayout(self.selection_bar)
        self.selection_layout.setContentsMargins(UIConstants.LAYOUT_MARGIN_DEFAULT, 0, UIConstants.LAYOUT_MARGIN_DEFAULT, 0)
        self.selection_layout.setSpacing(UIConstants.LAYOUT_MARGIN_DEFAULT)
        
        self.btn_sel_cancel = self.create_bulk_selection_button("Cancel", "close", lambda: self.toggle_bulk_selection(False))
        
        self.label_sel_count = QLabel("0 items selected")
        self.label_sel_count.setObjectName("status_label")
        
        self.selection_layout.addWidget(self.btn_sel_cancel)
        self.selection_layout.addWidget(self.label_sel_count)
        self.selection_layout.addStretch()
        
        self.layout.addWidget(self.selection_bar)

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
        self._keyboard_nav = KeyboardBrowserNavigator(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_status_area_geometry()

    def _update_status_area_geometry(self):
        y = UIConstants.HEADER_HEIGHT
        if self.selection_bar.isVisible():
            y += self.selection_bar.height()
        self.status_area.setGeometry(0, y, self.width(), UIConstants.STATUS_HEIGHT)
        self.status_area.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        self.setFocus()

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

            for btn, icon_name in self._bulk_selection_buttons.items():
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

    def create_bulk_selection_button(self, text: str, icon_name: str, callback: Optional[Callable] = None) -> QPushButton:
        """Creates a standardized, themed selection bar button."""
        btn = QPushButton(text)
        btn.setObjectName("secondary_button") # Unify all selection buttons to secondary
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if callback:
            btn.clicked.connect(callback)
        
        self._bulk_selection_buttons[btn] = icon_name
        
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

    def toggle_bulk_selection(self, enabled: bool):
        """Standardized bulk selection mode toggle UI."""
        self._bulk_selection_mode = enabled
        self.selection_bar.setVisible(enabled)
        self._update_status_area_geometry()
        if hasattr(self, 'btn_select'):
            self.btn_select.setChecked(enabled)
        
        # If disabling, ensure any derived selection UI state is cleared
        if not enabled:
            self._update_selection_ui()

    def cycle_card_size(self):
        """Standard implementation for card size cycling across browser views."""
        sizes = ["small", "medium", "large"]
        current_size = getattr(self, "_card_size", "medium")
        try:
            current_idx = sizes.index(current_size)
            next_size = sizes[(current_idx + 1) % len(sizes)]
            if hasattr(self, "_on_card_size_changed"):
                self._on_card_size_changed(next_size)
        except ValueError:
            if hasattr(self, "_on_card_size_changed"):
                self._on_card_size_changed("medium")

    def cycle_display_mode(self):
        """Cycle display modes (paging). Overridden by subclasses."""
        pass

    def cycle_group_by(self):
        """Cycle grouping modes. Overridden by subclasses."""
        pass

    def keyPressEvent(self, event):
        """Handle Escape key to exit selection mode and D for bulk actions."""
        if self.help_popover.isVisible():
            self.help_popover.hide()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape and self._bulk_selection_mode:
            self.toggle_bulk_selection(False)
            event.accept()
        elif event.key() == Qt.Key.Key_D and self._bulk_selection_mode:
            self.keyboard_trigger_bulk_action()
            event.accept()
        else:
            super().keyPressEvent(event)

    def keyboard_trigger_bulk_action(self):
        """Trigger the primary bulk action for the current view. Overridden by subclasses."""
        pass

    def _toggle_labels(self):
        """Standard implementation for label toggling across browser views."""
        if hasattr(self, "toggle_labels"):
            # If the subclass has a toggle_labels method, use it
            self.toggle_labels(not getattr(self, "_show_labels", True))
        elif hasattr(self, "config_manager"):
            # Fallback to direct config manipulation if applicable
            current = self._show_labels
            self.toggle_labels(not current)

    def _cycle_card_size(self):
        """Standard implementation for card size cycling across browser views."""
        sizes = ["small", "medium", "large"]
        current_size = getattr(self, "_card_size", "medium")
        try:
            current_idx = sizes.index(current_size)
            next_size = sizes[(current_idx + 1) % len(sizes)]
            if hasattr(self, "_on_card_size_changed"):
                self._on_card_size_changed(next_size)
        except ValueError:
            if hasattr(self, "_on_card_size_changed"):
                self._on_card_size_changed("medium")

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

    def refresh_keyboard_navigation(self):
        self._keyboard_nav.sync()

    def clear_keyboard_cursor(self):
        self._keyboard_nav.clear_cursor()

    def get_keyboard_nav_views(self):
        return []

    def get_keyboard_nav_focus_objects(self):
        return []

    def get_help_popover_title(self):
        return "Browser Controls"

    def get_help_popover_sections(self):
        # We start with common global navigation keys
        sections = self.get_common_help_sections()
        
        # Add Browser-specific sections (Cursor and View)
        sections.insert(0, ("KEYBOARD CURSOR", [
            ("Ctrl + Arrows", "Enter cursor mode and move across visible cards"),
            ("Enter", "Open focused card"),
            ("Menu / Shift+F10", "Open focused card menu"),
            ("Space", "Toggle bulk-selection on focused card"),
            ("Esc / Mouse / Other key", "Exit cursor mode"),
        ]))

        sections.append(("VIEW CONTROLS", [
            ("P", "Cycle layout / paging mode"),
            ("T", "Toggle item labels"),
            ("Z", "Cycle card size (S, M, L)"),
            ("S", "Toggle bulk-selection mode"),
            ("D", "Perform bulk action (Delete / Download)"),
            ("\\", "Toggle all sections (expand/collapse)"),
            ("[", "Toggle active section"),
            ("]", "Follow section link (e.g. See All)"),
        ]))

        # Only show feed-specific shortcuts if we have an active feed session
        win = self.window()
        if win and hasattr(win, "api_client") and win.api_client:
            sections.append(("FEED CONTROLS", [
                ("Ctrl + B", "Switch to Browse tab"),
                ("/", "Switch to Search tab"),
            ]))
            
        return sections

    def get_keyboard_nav_scrollbar(self):
        return None

    def keyboard_activate_index(self, view, index):
        pass

    def keyboard_context_menu_for_index(self, view, index):
        pass

    def keyboard_toggle_bulk_item(self, view, index):
        """Uses the keyboard to toggle an item for bulk operations."""
        if not index.isValid():
            return
        if not self._bulk_selection_mode:
            self.toggle_bulk_selection(True)

        if isinstance(view, QListWidget):
            item = view.item(index.row())
            if item:
                item.setSelected(not item.isSelected())
        else:
            selection_model = view.selectionModel()
            if selection_model:
                # Bulk selection uses the standard Qt selection model for persistence
                flags = QItemSelectionModel.SelectionFlag.Toggle
                selection_model.select(index, flags)
            
        self._update_selection_ui()

    def _update_selection_ui(self):
        """Standard implementation for updating selection toolbar state. Override in subclasses."""
        pass
