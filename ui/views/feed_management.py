import asyncio
import os
from typing import Optional
from urllib.parse import urljoin, urlparse

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QLineEdit, QPushButton, QFormLayout, QGroupBox, QMessageBox,
    QDialog, QApplication, QStyle, QFrame
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap

from config import ConfigManager
from models.feed import FeedProfile
from api.client import APIClient
from api.image_manager import ImageManager
from logger import get_logger

logger = get_logger("ui.feed_management")

class ConnectionTestResultDialog(QDialog):
    def __init__(self, parent, success: bool, message: str, icon_pixmap: QPixmap = None):
        super().__init__(parent)
        self.setWindowTitle("Connection Test Result")
        self.setFixedWidth(400)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(20)
        
        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if icon_pixmap and not icon_pixmap.isNull():
            icon_label.setPixmap(icon_pixmap.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            from ui.theme_manager import ThemeManager
            icon_label.setPixmap(ThemeManager.get_icon("feeds").pixmap(80, 80))
        layout.addWidget(icon_label)
        
        status_title = QLabel("SUCCESS" if success else "CONNECTION FAILED")
        status_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_title.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {'#4caf50' if success else '#f44336'};")
        layout.addWidget(status_title)
        
        msg_label = QLabel(message)
        msg_label.setWordWrap(True)
        msg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg_label.setStyleSheet("font-size: 13px; line-height: 1.4;")
        layout.addWidget(msg_label)
        
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: rgba(128, 128, 128, 50);")
        layout.addWidget(line)

        btn_ok = QPushButton("Got it")
        btn_ok.setFixedWidth(120)
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.setMinimumHeight(40)
        btn_ok.clicked.connect(self.accept)
        
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_ok)
        btn_row.addStretch()
        layout.addLayout(btn_row)

class FeedEditDialog(QDialog):
    def __init__(self, parent, config_manager: ConfigManager, feed: Optional[FeedProfile] = None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.feed = feed
        self.shared_image_manager = ImageManager(None)
        
        self.setWindowTitle("Edit Feed" if feed else "Add New Feed")
        self.setFixedWidth(500)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        form_group = QGroupBox("Feed Details")
        form_layout = QFormLayout(form_group)
        form_layout.setSpacing(10)

        self.name_input = QLineEdit()
        self.url_input = QLineEdit()
        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("(optional)")
        self.pass_input = QLineEdit()
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_input.setPlaceholderText("(optional)")
        self.token_input = QLineEdit()
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_input.setPlaceholderText("(optional)")

        if feed:
            self.name_input.setText(feed.name)
            self.url_input.setText(feed.url)
            self.user_input.setText(feed.username or "")
            self.pass_input.setText(feed.password or "")
            self.token_input.setText(feed.bearer_token or "")

        form_layout.addRow("Name:", self.name_input)
        form_layout.addRow("URL:", self.url_input)
        form_layout.addRow("Username:", self.user_input)
        form_layout.addRow("Password:", self.pass_input)
        form_layout.addRow("Token:", self.token_input)
        layout.addWidget(form_group)

        btn_layout = QHBoxLayout()
        self.btn_test = QPushButton("Test Connection")
        self.btn_test.clicked.connect(self.test_connection)
        
        self.btn_save = QPushButton("Save Feed" if feed else "Add Feed")
        self.btn_save.setObjectName("primary_button")
        self.btn_save.setMinimumHeight(40)
        self.btn_save.clicked.connect(self.save_and_close)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setMinimumHeight(40)
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_test)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        layout.addLayout(btn_layout)

    def test_connection(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Test Connection", "Please enter a URL first.")
            return
        
        username = self.user_input.text() or None
        password = self.pass_input.text() or None
        token = self.token_input.text() or None
        
        self.btn_test.setEnabled(False)
        self.btn_test.setText("Testing...")
        asyncio.create_task(self._run_connection_test(url, username, password, token))

    async def _run_connection_test(self, url, username, password, token):
        try:
            temp_feed = FeedProfile(id="temp", name="temp", url=url, username=username, password=password, bearer_token=token)
            async with APIClient(temp_feed) as client:
                response = await client.get(url)
                
                pixmap = None
                if response.status_code < 400:
                    icon_url, source = await self._discover_icon(url, username, password, token)
                    if icon_url:
                        await self.shared_image_manager.get_image_b64(icon_url, api_client=client)
                        full_path = self.shared_image_manager._get_cache_path(icon_url)
                        if full_path.exists():
                            pixmap = QPixmap(str(full_path))
                    
                    msg = f"Connected successfully to {url}.\nStatus Code: {response.status_code}"
                    if os.getenv("DEBUG") == "1":
                        msg += f"\n\nIcon found via: {source}"
                        
                    dialog = ConnectionTestResultDialog(self, True, msg, pixmap)
                    dialog.exec()
                else:
                    msg = f"Server returned status {response.status_code}"
                    dialog = ConnectionTestResultDialog(self, False, msg)
                    dialog.exec()
        except Exception as e:
            dialog = ConnectionTestResultDialog(self, False, f"Error: {str(e)}")
            dialog.exec()
        finally:
            self.btn_test.setEnabled(True)
            self.btn_test.setText("Test Connection")

    async def _discover_icon(self, url: str, username: str = None, password: str = None, token: str = None) -> tuple[Optional[str], str]:
        """Discover feed icon via OPDS Auth Doc or root feed. Returns (url, source_name)."""
        logger.debug(f"Starting icon discovery for {url}")
        icon_url = None
        source = "None"
        try:
            temp_feed = FeedProfile(id="temp", name="temp", url=url, username=username, password=password, bearer_token=token)
            async with APIClient(temp_feed) as client:
                response = await client.get(url)
                
                auth_doc_url = None
                feed_logo_url = None
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        to_scan = [data]
                        while to_scan and not auth_doc_url:
                            item = to_scan.pop(0)
                            if not isinstance(item, dict): continue
                            
                            rels = item.get("rel", "")
                            rels = [rels] if isinstance(rels, str) else (rels or [])
                            href = item.get("href")
                            
                            if href:
                                if "authenticate" in rels or "http://opds-spec.org/auth/document" in rels:
                                    auth_doc_url = urljoin(url, href)
                                    break
                                
                                props = item.get("properties", {})
                                if isinstance(props, dict) and "authenticate" in props:
                                    p_auth = props["authenticate"]
                                    if isinstance(p_auth, dict) and p_auth.get("href"):
                                        auth_doc_url = urljoin(url, p_auth["href"])
                                        break
                                        
                                if not feed_logo_url and ("logo" in rels or "icon" in rels):
                                    feed_logo_url = urljoin(url, href)

                            for key in ["links", "navigation", "publications", "groups"]:
                                val = item.get(key)
                                if isinstance(val, list):
                                    to_scan.extend([v for v in val if isinstance(v, dict)])
                                elif isinstance(val, dict):
                                    to_scan.append(val)
                    except: pass
                elif response.status_code == 401:
                    link_header = response.headers.get("Link", "")
                    if 'rel="authenticate"' in link_header or 'rel="http://opds-spec.org/auth/document"' in link_header:
                        import re
                        match = re.search(r'<(.*?)>;\s*rel="(?:authenticate|http://opds-spec.org/auth/document)"', link_header)
                        if match:
                            auth_doc_url = urljoin(url, match.group(1))

                # Priority 1: Auth Document
                if auth_doc_url:
                    auth_resp = await client.get(auth_doc_url)
                    if auth_resp.status_code == 200:
                        auth_data = auth_resp.json()
                        auth_links = auth_data.get("links", [])
                        for al in auth_links:
                            if al.get("rel") in ["logo", "icon"]:
                                icon_url = urljoin(auth_doc_url, al.get("href"))
                                source = "OPDS Authentication Document"
                                break
                        if not icon_url:
                            icon_url = auth_data.get("logo") or auth_data.get("icon")
                            if icon_url: source = "OPDS Authentication Document"
                        
                        if icon_url and not icon_url.startswith("http"):
                            icon_url = urljoin(auth_doc_url, icon_url)
                
                # Priority 2: Feed Logo
                if not icon_url and feed_logo_url:
                    icon_url = feed_logo_url
                    source = "OPDS Feed Logo"

                # Priority 3: Favicon
                if not icon_url:
                    parsed = urlparse(url)
                    base = f"{parsed.scheme}://{parsed.netloc}"
                    icon_url = urljoin(base, "/favicon.ico")
                    source = "Favicon (Fallback)"
        except Exception as e:
            logger.debug(f"Icon discovery failed for {url}: {e}")
            
        if icon_url:
            if "komgaandroid" in icon_url:
                icon_url = icon_url.replace("komgaandroid", "komga/android")

        logger.debug(f"Final icon URL for {url}: {icon_url}")
        return icon_url, source

    def save_and_close(self):
        name = self.name_input.text().strip()
        url = self.url_input.text().strip()
        if not name or not url:
            QMessageBox.warning(self, "Validation Error", "Name and URL are required.")
            return

        username = self.user_input.text() or None
        password = self.pass_input.text() or None
        token = self.token_input.text() or None

        if self.feed:
            self.feed.name = name
            self.feed.url = url
            self.feed.username = username
            self.feed.password = password
            self.feed.bearer_token = token
            self.config_manager.update_feed(self.feed)
            asyncio.create_task(self._discover_and_save_icon(self.feed))
        else:
            new_feed = self.config_manager.add_feed(name, url, username, password, token)
            asyncio.create_task(self._discover_and_save_icon(new_feed))
        
        self.accept()

    async def _discover_and_save_icon(self, feed: FeedProfile):
        icon_url, _ = await self._discover_icon(feed.url, feed.username, feed.password, feed.bearer_token)
        if icon_url:
            feed.icon_url = icon_url
            self.config_manager.update_feed(feed)

class FeedManagementView(QWidget):
    icon_loaded = pyqtSignal(str, object) # feed_id, pixmap

    def __init__(self, config_manager: ConfigManager):
        super().__init__()
        self.config_manager = config_manager
        self.shared_image_manager = ImageManager(None)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        header.addWidget(QLabel("Configured Feeds"))
        header.addStretch()
        
        self.btn_add = QPushButton("Add New Feed")
        self.btn_add.setObjectName("primary_button")
        self.btn_add.setMinimumHeight(35)
        self.btn_add.clicked.connect(self.add_feed)
        header.addWidget(self.btn_add)
        self.layout.addLayout(header)

        self.feeds_list = QListWidget()
        self.feeds_list.setIconSize(QSize(32, 32))
        self.feeds_list.setStyleSheet("""
            QListWidget { 
                border-radius: 4px; 
            }
            QListWidget::item { 
                padding: 10px; 
                border-bottom: 1px solid rgba(128, 128, 128, 30); 
            }
        """)
        self.feeds_list.itemDoubleClicked.connect(self.edit_selected)
        self.layout.addWidget(self.feeds_list)

        self.list_btns = QHBoxLayout()
        self.btn_edit = QPushButton("Edit")
        self.btn_edit.setMinimumHeight(35)
        self.btn_edit.clicked.connect(self.edit_selected)
        
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setMinimumHeight(35)
        self.btn_delete.setStyleSheet("background-color: #d32f2f; color: white;")
        self.btn_delete.clicked.connect(self.delete_selected)
        
        self.list_btns.addWidget(self.btn_edit)
        self.list_btns.addWidget(self.btn_delete)
        self.list_btns.addStretch()
        self.layout.addLayout(self.list_btns)

        self.refresh_feeds()

    def refresh_feeds(self):
        from ui.theme_manager import ThemeManager
        default_icon = ThemeManager.get_icon("feeds")
        
        self.feeds_list.clear()
        for f in self.config_manager.feeds:
            item = QListWidgetItem(f"{f.name}\n{f.url}")
            item.setData(Qt.ItemDataRole.UserRole, f)
            item.setIcon(default_icon)
            self.feeds_list.addItem(item)
            if f.icon_url:
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
                        item.setIcon(QIcon(pixmap))
                    self.icon_loaded.emit(feed.id, pixmap)
            await client.close()
        except: pass

    def add_feed(self):
        dialog = FeedEditDialog(self, self.config_manager)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_feeds()

    def edit_selected(self):
        item = self.feeds_list.currentItem()
        if item:
            feed = item.data(Qt.ItemDataRole.UserRole)
            dialog = FeedEditDialog(self, self.config_manager, feed)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.refresh_feeds()

    def delete_selected(self):
        item = self.feeds_list.currentItem()
        if item:
            feed = item.data(Qt.ItemDataRole.UserRole)
            reply = QMessageBox.question(self, 'Delete Feed', 
                                       f"Are you sure you want to delete '{feed.name}'?",
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.config_manager.remove_feed(feed.id)
                self.refresh_feeds()
