# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

import asyncio
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, 
    QLabel, QApplication, QStyle, QPushButton, QDialog
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from comiccatcher.config import ConfigManager
from comiccatcher.ui.theme_manager import ThemeManager, UIConstants
from comiccatcher.models.feed import FeedProfile
from comiccatcher.api.client import APIClient
from comiccatcher.api.image_manager import ImageManager
from comiccatcher.ui.views.feed_management import FeedEditDialog

from comiccatcher.ui.views.base_browser import BaseBrowserView

class FeedListView(BaseBrowserView):
    icon_loaded = pyqtSignal(str, object) # feed_id, pixmap

    def __init__(self, config_manager: ConfigManager, image_manager: ImageManager, on_feed_selected):
        self.config_manager = config_manager
        super().__init__()
        self.on_feed_selected = on_feed_selected
        self.shared_image_manager = image_manager

        # Disable the complex navigator for this simple list view
        if hasattr(self, "_keyboard_nav"):
            self._keyboard_nav.sync() # Clean up filters
            self._keyboard_nav.deleteLater()
            self._keyboard_nav = None

        s = UIConstants.scale
        self.content_layout.setContentsMargins(s(20), s(20), s(20), s(20))
        
        # Header with Title and Add Button
        self.header = QHBoxLayout()
        self.title_label = QLabel("Select a Feed")
        self.header.addWidget(self.title_label)
        self.header.addStretch()
        
        self.btn_add = QPushButton("Add Feed")
        self.btn_add.setIcon(ThemeManager.get_icon("plus", "white"))
        s = UIConstants.scale
        self.btn_add.setIconSize(QSize(s(18), s(18)))
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.setObjectName("primary_button")
        self.btn_add.clicked.connect(self.add_feed)
        self.header.addWidget(self.btn_add)
        
        self.content_layout.addLayout(self.header)

        self.feeds_list = QListWidget()
        self.feeds_list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.feeds_list.setIconSize(QSize(UIConstants.FEED_ICON_SIZE_LARGE, UIConstants.FEED_ICON_SIZE_LARGE))
        self.feeds_list.itemClicked.connect(self._on_item_clicked)
        self.feeds_list.installEventFilter(self)
        self.content_layout.addWidget(self.feeds_list)
        
        self.reapply_theme()
        self.refresh_feeds()

    def _on_item_clicked(self, item):
        feed = item.data(Qt.ItemDataRole.UserRole)
        if feed:
            self.on_feed_selected(feed)

    def reapply_theme(self):
        if not hasattr(self, 'title_label'):
            return
        theme = ThemeManager.get_current_theme_colors()
        s = UIConstants.scale
        self.title_label.setStyleSheet(f"font-size: {UIConstants.FONT_SIZE_DETAIL_TITLE}px; font-weight: bold; color: {theme['text_main']};")
        
        # Explicitly set the font for the list widget to ensure the text scales
        font = self.feeds_list.font()
        font.setPixelSize(UIConstants.FONT_SIZE_FEED_LIST)
        self.feeds_list.setFont(font)
        
        # Main list styling
        # Note: We set item padding to 0 because we use setItemWidget with its own internal margins.
        self.feeds_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {theme['bg_sidebar']};
                border: {max(1, s(1))}px solid {theme['border']};
                border-radius: {s(8)}px;
                padding: {s(5)}px;
                margin-top: {s(10)}px;
                color: {theme['text_main']};
            }}
            QListWidget::item {{
                padding: 0px;
                border-bottom: {max(1, s(1))}px solid {theme['border']};
                color: {theme['text_main']};
            }}
            QListWidget::item:selected {{
                background-color: {theme['bg_item_selected']};
                color: {theme['text_selected']};
            }}
        """)
        
    def refresh(self):
        self.refresh_feeds()

    def refresh_feeds(self):
        default_icon = ThemeManager.get_icon("feeds")
        theme = ThemeManager.get_current_theme_colors()
        s = UIConstants.scale
        
        self.feeds_list.clear()
        for f in self.config_manager.feeds:
            # Use rich text to bump name font size
            name_fs = UIConstants.FONT_SIZE_FEED_NAME_LARGE
            url_fs = UIConstants.FONT_SIZE_FEED_URL_LARGE
            rich_text = f'<b><span style="font-size: {name_fs}px;">{f.name}</span></b><br/><span style="font-size: {url_fs}px; color: {theme["text_dim"]};">{f.url}</span>'
            
            item = QListWidgetItem()
            self.feeds_list.addItem(item)
            
            # Since QListWidgetItem doesn't support rich text directly via setText,
            # we can use a custom widget or just use the item's font for the whole thing.
            # But the user asked for ONLY the name to be increased.
            # Standard QListWidget items don't support per-line font sizes without custom delegates.
            # A quick way is to use setItemWidget.
            
            widget = QWidget()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(s(15), s(8), s(15), s(8))
            layout.setSpacing(s(15))
            
            icon_size = UIConstants.FEED_ICON_SIZE_LARGE
            icon_label = QLabel()
            icon_label.setFixedSize(icon_size, icon_size)
            icon_label.setScaledContents(False)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            text_label = QLabel(rich_text)
            text_label.setStyleSheet("background: transparent; border: none;")
            text_label.setWordWrap(True)
            
            layout.addWidget(icon_label)
            layout.addWidget(text_label, 1)
            
            # Ensure the widget's layout calculates the correct size
            sh = widget.sizeHint()
            # Add a small vertical buffer for safety with rich text
            sh.setHeight(sh.height() + s(2))
            item.setSizeHint(sh)
            item.setData(Qt.ItemDataRole.UserRole, f)
            self.feeds_list.setItemWidget(item, widget)
            
            # Handle Icon
            icon_pixmap = None
            if f.icon_url:
                cache_path = self.shared_image_manager._get_cache_path(f.icon_url)
                if cache_path.exists():
                    icon_pixmap = QPixmap(str(cache_path))
            
            if icon_pixmap and not icon_pixmap.isNull():
                scaled = icon_pixmap.scaled(icon_size, icon_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                icon_label.setPixmap(scaled)
                f._cached_icon = icon_pixmap
            else:
                icon_label.setPixmap(default_icon.pixmap(icon_size, icon_size))
            
            # We no longer trigger a background fetch for every feed here.
            # Icons will be fetched only when the feed is visited (managed in FeedBrowser)
            # or explicitly refreshed in management.
            
        # Select first item by default if nothing selected
        if self.feeds_list.count() > 0 and not self.feeds_list.currentItem():
            self.feeds_list.setCurrentRow(0)

    async def _load_cached_icon_widget(self, feed: FeedProfile, label: QLabel):
        try:
            client = APIClient(feed)
            await self.shared_image_manager.get_image_b64(feed.icon_url, api_client=client)
            full_path = self.shared_image_manager._get_cache_path(feed.icon_url)
            if full_path.exists():
                pixmap = QPixmap(str(full_path))
                if not pixmap.isNull():
                    feed._cached_icon = pixmap
                    s = UIConstants.scale
                    scaled = pixmap.scaled(UIConstants.FEED_ICON_SIZE_LARGE, UIConstants.FEED_ICON_SIZE_LARGE, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    label.setPixmap(scaled)
                    self.icon_loaded.emit(feed.id, pixmap)
            await client.close()
        except: pass

    def add_feed(self):
        dialog = FeedEditDialog(self, self.config_manager, self.shared_image_manager)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_feeds()

    def get_keyboard_nav_views(self):
        if not hasattr(self, "feeds_list"):
            return []
        return [self.feeds_list]

    def keyboard_activate_index(self, view, index):
        if not hasattr(self, "feeds_list"):
            return
        item = self.feeds_list.item(index.row())
        if item:
            self._on_item_clicked(item)

    def eventFilter(self, obj, event):
        """Intercepts keys from the list widget before they are swallowed."""
        if obj == self.feeds_list and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key.Key_H:
                self.toggle_help_popover()
                return True
            if event.key() == Qt.Key.Key_A:
                self.add_feed()
                return True
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                item = self.feeds_list.currentItem()
                if item:
                    self._on_item_clicked(item)
                return True
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        """Clicking the background returns focus to the list."""
        self.feeds_list.setFocus()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        """Redirects navigation and activation keys to the list if it's not focused."""
        # If the list isn't focused, but user is hitting navigation keys, forward them
        if not self.feeds_list.hasFocus():
            if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown, Qt.Key.Key_Return, Qt.Key.Key_Enter):
                # We use the list's own keyPressEvent to avoid going back through our eventFilter
                self.feeds_list.keyPressEvent(event)
                return

        super().keyPressEvent(event)

    def get_help_popover_title(self):
        return "Feed Selection Controls"

    def get_help_popover_sections(self):
        sections = self.get_common_help_sections()
        sections.insert(0, ("FEED LIST", [
            ("Arrows", "Navigate feeds"),
            ("Enter", "Select focused feed"),
            ("A", "Add a new OPDS feed"),
        ]))
        return sections

    def showEvent(self, event):
        self.refresh_feeds()
        # Use singleShot to ensure focus is applied after any parent stack transitions
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self.feeds_list.setFocus)
        # Ensure navigator sees the list
        if hasattr(self, "navigator"):
            self.navigator.sync()
        super().showEvent(event)
