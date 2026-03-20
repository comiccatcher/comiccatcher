import asyncio
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, 
    QLabel, QApplication, QStyle, QPushButton, QDialog
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from config import ConfigManager
from ui.theme_manager import ThemeManager
from models.feed import FeedProfile
from api.client import APIClient
from api.image_manager import ImageManager
from ui.views.feed_management import FeedEditDialog

class FeedListView(QWidget):
    icon_loaded = pyqtSignal(str, object) # feed_id, pixmap

    def __init__(self, config_manager: ConfigManager, on_feed_selected):
        super().__init__()
        self.config_manager = config_manager
        self.on_feed_selected = on_feed_selected
        self.shared_image_manager = ImageManager(None)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        
        # Header with Title and Add Button
        header = QHBoxLayout()
        self.title = QLabel("Select a Feed")
        self.title.setStyleSheet("font-size: 24px; font-weight: bold;")
        header.addWidget(self.title)
        header.addStretch()
        
        self.btn_add = QPushButton()
        # Let's try to find a better standard plus icon or use text
        self.btn_add.setText(" + Add Feed")
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.setObjectName("primary_button")
        self.btn_add.clicked.connect(self.add_new_feed)
        header.addWidget(self.btn_add)
        
        self.layout.addLayout(header)

        self.feeds_list = QListWidget()
        self.feeds_list.setIconSize(QSize(48, 48))
        self.feeds_list.setStyleSheet("""
            QListWidget {
                border-radius: 8px;
                padding: 5px;
                margin-top: 10px;
            }
            QListWidget::item {
                padding: 15px;
                border-bottom: 1px solid rgba(128, 128, 128, 50);
            }
        """)
        self.feeds_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.layout.addWidget(self.feeds_list)
        
        self.refresh_feeds()

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

    def add_new_feed(self):
        dialog = FeedEditDialog(self, self.config_manager)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_feeds()

    def _on_item_double_clicked(self, item):
        feed = item.data(Qt.ItemDataRole.UserRole)
        if feed:
            self.on_feed_selected(feed)

    def showEvent(self, event):
        self.refresh_feeds()
        super().showEvent(event)
