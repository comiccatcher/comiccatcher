from __future__ import annotations
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

from comiccatcher.config import ConfigManager
from comiccatcher.models.feed import FeedProfile
from comiccatcher.api.client import APIClient
from comiccatcher.api.image_manager import ImageManager
from comiccatcher.ui.theme_manager import ThemeManager, UIConstants
from comiccatcher.logger import get_logger

logger = get_logger("ui.feed_management")

class ConnectionTestResultDialog(QDialog):
    def __init__(self, parent, success: bool, message: str, icon_pixmap: QPixmap = None):
        super().__init__(parent)
        s = UIConstants.scale
        self.setWindowTitle("Connection Test Result")
        self.setFixedWidth(s(400))
        self.success = success
        self.message = message
        self.icon_pixmap = icon_pixmap
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(s(25), s(25), s(25), s(25))
        self.layout.setSpacing(s(20))
        
        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.icon_label)
        
        self.status_title = QLabel()
        self.status_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.status_title)
        
        self.msg_label = QLabel(message)
        self.msg_label.setWordWrap(True)
        self.msg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.msg_label)
        
        self.line = QFrame()
        self.line.setFrameShape(QFrame.Shape.HLine)
        self.line.setFrameShadow(QFrame.Shadow.Sunken)
        self.layout.addWidget(self.line)

        self.btn_ok = QPushButton("Got it")
        self.btn_ok.setObjectName("secondary_button")
        self.btn_ok.setFixedWidth(s(120))
        self.btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ok.setMinimumHeight(s(40))
        self.btn_ok.clicked.connect(self.accept)
        
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self.btn_ok)
        btn_row.addStretch()
        self.layout.addLayout(btn_row)
        
        self.reapply_theme()

    def reapply_theme(self):
        theme = ThemeManager.get_current_theme_colors()
        s = UIConstants.scale
        
        if self.icon_pixmap and not self.icon_pixmap.isNull():
            self.icon_label.setPixmap(self.icon_pixmap.scaled(s(80), s(80), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.icon_label.setPixmap(ThemeManager.get_icon("feeds").pixmap(s(80), s(80)))
            
        self.status_title.setText("SUCCESS" if self.success else "CONNECTION FAILED")
        self.status_title.setStyleSheet(f"font-size: {s(20)}px; font-weight: bold; color: {theme['success'] if self.success else theme['danger']};")
        self.msg_label.setStyleSheet(f"font-size: {s(13)}px; line-height: 1.4; color: {theme['text_main']};")
        self.line.setStyleSheet(f"background-color: {theme['border']};")
        self.btn_ok.setStyleSheet("font-weight: bold;")

class FeedEditDialog(QDialog):
    def __init__(self, parent, config_manager: ConfigManager, image_manager: ImageManager, feed: Optional[FeedProfile] = None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.feed = feed
        self.shared_image_manager = image_manager
        
        s = UIConstants.scale
        self.setWindowTitle("Edit Feed" if feed else "Add New Feed")
        self.setFixedWidth(s(500))
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(s(20), s(20), s(20), s(20))
        layout.setSpacing(s(15))

        form_group = QGroupBox("Feed Details")
        form_layout = QFormLayout(form_group)
        form_layout.setSpacing(s(10))

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
        self.btn_test.setObjectName("secondary_button")
        self.btn_test.clicked.connect(self.test_connection)
        
        s = UIConstants.scale
        self.btn_save = QPushButton("Save Feed" if feed else "Add Feed")
        self.btn_save.setObjectName("primary_button")
        self.btn_save.setMinimumHeight(s(40))
        self.btn_save.clicked.connect(self.save_and_close)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("secondary_button")
        self.btn_cancel.setMinimumHeight(s(40))
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_test)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        layout.addLayout(btn_layout)

        self.reapply_theme()

    def reapply_theme(self):
        theme = ThemeManager.get_current_theme_colors()
        self.setStyleSheet(f"""
            QDialog {{ background-color: {theme['bg_main']}; color: {theme['text_main']}; }}
            QGroupBox {{ font-weight: bold; font-size: {UIConstants.FONT_SIZE_DETAIL_INFO}px; color: {theme['text_main']}; }}
            QLabel {{ font-size: {UIConstants.FONT_SIZE_DETAIL_INFO}px; color: {theme['text_main']}; }}
            QLineEdit {{ font-size: {UIConstants.FONT_SIZE_DETAIL_INFO}px; padding: {UIConstants.scale(4)}px; }}
        """)

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

    def __init__(self, config_manager: ConfigManager, image_manager: ImageManager):
        super().__init__()
        self.config_manager = config_manager
        self.shared_image_manager = image_manager

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        s = UIConstants.scale
        header = QHBoxLayout()
        self.title_label = QLabel("Configured Feeds")
        header.addWidget(self.title_label)
        header.addStretch()
        
        self.btn_add = QPushButton("Add New Feed")
        self.btn_add.setObjectName("secondary_button")
        self.btn_add.setIcon(ThemeManager.get_icon("plus", "accent"))
        self.btn_add.setMinimumHeight(s(35))
        self.btn_add.clicked.connect(self.add_feed)
        header.addWidget(self.btn_add)
        self.layout.addLayout(header)

        self.feeds_list = QListWidget()
        self.feeds_list.setIconSize(QSize(s(32), s(32)))
        self.feeds_list.setMinimumHeight(s(180)) # Roughly 3 items
        self.feeds_list.itemDoubleClicked.connect(self.edit_selected)
        self.layout.addWidget(self.feeds_list)

        self.list_btns = QHBoxLayout()
        self.btn_edit = QPushButton("Edit")
        self.btn_edit.setObjectName("secondary_button")
        self.btn_edit.setIcon(ThemeManager.get_icon("label", "accent"))
        self.btn_edit.setMinimumHeight(s(35))
        self.btn_edit.clicked.connect(self.edit_selected)
        
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setObjectName("secondary_button")
        self.btn_delete.setIcon(ThemeManager.get_icon("action_delete", "accent"))
        self.btn_delete.setMinimumHeight(s(35))
        self.btn_delete.clicked.connect(self.delete_selected)
        
        self.list_btns.addWidget(self.btn_edit)
        self.list_btns.addWidget(self.btn_delete)
        self.list_btns.addStretch()
        self.layout.addLayout(self.list_btns)

        self.reapply_theme()
        self.refresh_feeds()

    def reapply_theme(self):
        theme = ThemeManager.get_current_theme_colors()
        s = UIConstants.scale
        self.title_label.setStyleSheet(f"font-size: {UIConstants.FONT_SIZE_SECTION_HEADER}px; font-weight: bold; color: {theme['text_main']};")
        
        # Explicitly set the font for the list widget to ensure the text scales
        font = self.feeds_list.font()
        font.setPixelSize(UIConstants.FONT_SIZE_FEED_LIST)
        self.feeds_list.setFont(font)
        
        # Scale buttons
        for btn in [self.btn_add, self.btn_edit, self.btn_delete]:
            btn.setStyleSheet(f"font-size: {UIConstants.FONT_SIZE_DETAIL_INFO}px;")
        
        self.feeds_list.setStyleSheet(f"""
            QListWidget {{ 
                background-color: {theme['bg_sidebar']};
                border: {max(1, s(1))}px solid {theme['border']};
                border-radius: {s(4)}px; 
                color: {theme['text_main']};
            }}
            QListWidget::item {{ 
                padding: 0px; 
                border-bottom: {max(1, s(1))}px solid {theme['border']}; 
            }}
            QListWidget::item:selected {{
                background-color: {theme['bg_item_selected']};
                color: {theme['text_selected']};
            }}
        """)

    def refresh_feeds(self):
        default_icon = ThemeManager.get_icon("feeds")
        s = UIConstants.scale
        
        self.feeds_list.clear()
        for f in self.config_manager.feeds:
            name_fs = s(16) # Slightly smaller than root list but still bumped
            url_fs = s(12)
            rich_text = f'<b><span style="font-size: {name_fs}px;">{f.name}</span></b><br/><span style="font-size: {url_fs}px; color: #888;">{f.url}</span>'

            item = QListWidgetItem()
            self.feeds_list.addItem(item)
            
            widget = QWidget()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(s(15), s(6), s(15), s(6))
            layout.setSpacing(s(10))
            
            icon_label = QLabel()
            icon_label.setFixedSize(s(32), s(32))
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
                scaled = icon_pixmap.scaled(s(32), s(32), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                icon_label.setPixmap(scaled)
                f._cached_icon = icon_pixmap
            else:
                icon_label.setPixmap(default_icon.pixmap(s(32), s(32)))

            if f.icon_url and (not icon_pixmap or icon_pixmap.isNull()):
                asyncio.create_task(self._load_cached_icon_widget(f, icon_label))

    async def _load_cached_icon_widget(self, feed: FeedProfile, label: QLabel):
        try:
            icon_path = self.shared_image_manager._get_cache_path(feed.icon_url)
            if not icon_path.exists():
                client = APIClient(feed)
                await self.shared_image_manager.get_image_b64(feed.icon_url, api_client=client)
                await client.close()
            
            if icon_path.exists():
                pixmap = QPixmap(str(icon_path))
                if not pixmap.isNull():
                    feed._cached_icon = pixmap
                    s = UIConstants.scale
                    scaled = pixmap.scaled(s(32), s(32), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    label.setPixmap(scaled)
                    self.icon_loaded.emit(feed.id, pixmap)
        except: pass

    def add_feed(self):
        dialog = FeedEditDialog(self, self.config_manager, self.shared_image_manager)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_feeds()

    def edit_selected(self):
        item = self.feeds_list.currentItem()
        if item:
            feed = item.data(Qt.ItemDataRole.UserRole)
            dialog = FeedEditDialog(self, self.config_manager, self.shared_image_manager, feed)
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
