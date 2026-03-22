import asyncio
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, 
    QLabel, QApplication, QStyle, QPushButton, QDialog
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from config import ConfigManager
from ui.theme_manager import ThemeManager, UIConstants
from models.feed import FeedProfile
from api.client import APIClient
from api.image_manager import ImageManager
from ui.views.feed_management import FeedEditDialog

class FeedListView(QWidget):
    icon_loaded = pyqtSignal(str, object) # feed_id, pixmap

    def __init__(self, config_manager: ConfigManager, image_manager: ImageManager, on_feed_selected):
        super().__init__()
        self.config_manager = config_manager
        self.on_feed_selected = on_feed_selected
        self.shared_image_manager = image_manager

        self.layout = QVBoxLayout(self)
        s = UIConstants.scale
        self.layout.setContentsMargins(s(20), s(20), s(20), s(20))
        
        # Header with Title and Add Button
        self.header = QHBoxLayout()
        self.title_label = QLabel("Select a Feed")
        self.header.addWidget(self.title_label)
        self.header.addStretch()
        
        self.btn_add = QPushButton()
        self.btn_add.setText(" + Add Feed")
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.setObjectName("primary_button")
        self.btn_add.clicked.connect(self.add_feed)
        self.header.addWidget(self.btn_add)
        
        self.layout.addLayout(self.header)

        self.feeds_list = QListWidget()
        self.feeds_list.setIconSize(QSize(s(48), s(48)))
        self.feeds_list.itemClicked.connect(self._on_item_clicked)
        self.layout.addWidget(self.feeds_list)
        
        self.reapply_theme()
        self.refresh_feeds()

    def reapply_theme(self):
        theme = ThemeManager.get_current_theme_colors()
        s = UIConstants.scale
        self.title_label.setStyleSheet(f"font-size: {s(24)}px; font-weight: bold; color: {theme['text_main']};")
        
        # Main list styling
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
                padding: {s(15)}px;
                border-bottom: {max(1, s(1))}px solid {theme['border']};
                color: {theme['text_main']};
            }}
            QListWidget::item:selected {{
                background-color: {theme['bg_item_selected']};
                color: {theme['text_selected']};
            }}
        """)
        
    def refresh_feeds(self):
        default_icon = ThemeManager.get_icon("feeds")
        
        self.feeds_list.clear()
        for f in self.config_manager.feeds:
            item = QListWidgetItem(f"{f.name}\n{f.url}")
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            item.setData(Qt.ItemDataRole.UserRole, f)
            
            # Check for cached icon synchronously to avoid flash
            icon_set = False
            if f.icon_url:
                cache_path = self.shared_image_manager._get_cache_path(f.icon_url)
                if cache_path.exists():
                    pixmap = QPixmap(str(cache_path))
                    if not pixmap.isNull():
                        item.setIcon(QIcon(pixmap))
                        icon_set = True
            
            if not icon_set:
                item.setIcon(default_icon)
                
            self.feeds_list.addItem(item)
            
            if f.icon_url and not icon_set:
                asyncio.create_task(self._load_cached_icon(f, item))

    async def _load_cached_icon(self, feed: FeedProfile, item: QListWidgetItem):
        try:
            client = APIClient(feed)
            await self.shared_image_manager.get_image_b64(feed.icon_url, api_client=client)
            full_path = self.shared_image_manager._get_cache_path(feed.icon_url)
            if full_path.exists():
                pixmap = QPixmap(str(full_path))
                if not pixmap.isNull():
                    feed._cached_icon = pixmap
                    if item:
                        try:
                            item.setIcon(QIcon(pixmap))
                        except RuntimeError:
                            pass
                    self.icon_loaded.emit(feed.id, pixmap)
            await client.close()
        except:
            pass

    def add_feed(self):
        dialog = FeedEditDialog(self, self.config_manager, self.shared_image_manager)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_feeds()

    def _on_item_clicked(self, item):
        feed = item.data(Qt.ItemDataRole.UserRole)
        if feed:
            self.on_feed_selected(feed)

    def showEvent(self, event):
        self.refresh_feeds()
        super().showEvent(event)
