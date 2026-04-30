# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

from __future__ import annotations
import asyncio
import os
from typing import Optional, Dict
from urllib.parse import urljoin, urlparse

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QLineEdit, QPushButton, QFormLayout, QGroupBox, QMessageBox,
    QDialog, QApplication, QStyle, QFrame, QComboBox, QTextEdit
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
        self.form_layout = QFormLayout(form_group)
        self.form_layout.setSpacing(s(10))

        self.name_input = QLineEdit()
        self.url_input = QLineEdit()
        
        # 1. Initialize ALL Auth fields and labels FIRST
        self.user_label = QLabel("Username:")
        self.user_input = QLineEdit()
        self.pass_label = QLabel("Password:")
        self.pass_input = QLineEdit()
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_label = QLabel("Token:")
        self.token_input = QLineEdit()
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.apikey_label = QLabel("API Key:")
        self.apikey_input = QLineEdit()
        self.apikey_input.setEchoMode(QLineEdit.EchoMode.Password)

        # 1.1 Custom Headers
        self.headers_label = QLabel("Custom Headers:")
        self.headers_input = QTextEdit()
        self.headers_input.setPlaceholderText("Header-Name: Value (one per line)\ne.g. User-Agent: Foliate/3.3.0")
        self.headers_input.setFixedHeight(s(80))
        self.headers_input.setTabChangesFocus(True)

        # 2. Setup Type Selector
        self.auth_type_combo = QComboBox()
        self.auth_type_combo.addItem("None", "none")
        self.auth_type_combo.addItem("Username / Password", "basic")
        self.auth_type_combo.addItem("Bearer Token", "bearer")
        self.auth_type_combo.addItem("API Key", "apikey")
        
        if feed:
            self.name_input.setText(feed.name)
            self.url_input.setText(feed.url)
            self.user_input.setText(feed.username or "")
            self.pass_input.setText(feed.password or "")
            self.token_input.setText(feed.bearer_token or "")
            self.apikey_input.setText(feed.api_key or "")
            
            # Format custom headers
            if feed.custom_headers:
                header_text = "\n".join([f"{k}: {v}" for k, v in feed.custom_headers.items()])
                self.headers_input.setText(header_text)
            
            # Set combo index based on model (Signals blocked during setup)
            self.auth_type_combo.blockSignals(True)
            idx = self.auth_type_combo.findData(feed.auth_type)
            if idx >= 0:
                self.auth_type_combo.setCurrentIndex(idx)
            else:
                # Legacy migration logic
                if feed.bearer_token: self.auth_type_combo.setCurrentIndex(2)
                elif feed.username: self.auth_type_combo.setCurrentIndex(1)
                else: self.auth_type_combo.setCurrentIndex(0)
            self.auth_type_combo.blockSignals(False)

        # Connect signal AFTER setup
        self.auth_type_combo.currentIndexChanged.connect(self._update_auth_field_visibility)

        self.form_layout.addRow("Name:", self.name_input)
        self.form_layout.addRow("URL:", self.url_input)
        self.form_layout.addRow("Auth Type:", self.auth_type_combo)
        
        # Add all dynamic rows once (they will be hidden/shown by _update_auth_field_visibility)
        self.form_layout.addRow(self.user_label, self.user_input)
        self.form_layout.addRow(self.pass_label, self.pass_input)
        self.form_layout.addRow(self.token_label, self.token_input)
        self.form_layout.addRow(self.apikey_label, self.apikey_input)
        self.form_layout.addRow(self.headers_label, self.headers_input)
        
        layout.addWidget(form_group)
        self._update_auth_field_visibility()

        # 3. Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_test = QPushButton("Test Connection")
        self.btn_test.setObjectName("secondary_button")
        self.btn_test.setIcon(ThemeManager.get_icon("refresh", "accent"))
        self.btn_test.setIconSize(QSize(s(18), s(18)))
        self.btn_test.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_test.clicked.connect(self.test_connection)
        
        is_edit = feed is not None
        self.btn_save = QPushButton("Save Feed" if is_edit else "Add Feed")
        self.btn_save.setObjectName("primary_button")
        self.btn_save.setIcon(ThemeManager.get_icon("action_read" if is_edit else "plus", "white"))
        self.btn_save.setIconSize(QSize(s(18), s(18)))
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self.save_and_close)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("secondary_button")
        self.btn_cancel.setIcon(ThemeManager.get_icon("close", "accent"))
        self.btn_cancel.setIconSize(QSize(s(18), s(18)))
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(self.btn_test)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        layout.addLayout(btn_layout)
        
        self.adjustSize()

    def _update_auth_field_visibility(self):
        """Dynamically shows/hides credential fields based on selected auth type."""
        mode = self.auth_type_combo.currentData()
        
        # Toggle visibility - QFormLayout automatically collapses hidden rows
        is_basic = (mode == "basic")
        is_bearer = (mode == "bearer")
        is_apikey = (mode == "apikey")

        self.user_label.setVisible(is_basic)
        self.user_input.setVisible(is_basic)
        self.pass_label.setVisible(is_basic)
        self.pass_input.setVisible(is_basic)
        
        self.token_label.setVisible(is_bearer)
        self.token_input.setVisible(is_bearer)
        
        self.apikey_label.setVisible(is_apikey)
        self.apikey_input.setVisible(is_apikey)
        
        # Ensure dialog shrinks/expands to fit the new rows
        self.adjustSize()

    def test_connection(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Test Connection", "Please enter a URL first.")
            return
        
        auth_type = self.auth_type_combo.currentData()
        username = self.user_input.text() or None
        password = self.pass_input.text() or None
        token = self.token_input.text() or None
        api_key = self.apikey_input.text() or None
        
        # Parse custom headers
        custom_headers = {}
        header_text = self.headers_input.toPlainText().strip()
        if header_text:
            for line in header_text.split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    custom_headers[k.strip()] = v.strip()

        self.btn_test.setEnabled(False)
        self.btn_test.setText("Testing...")
        asyncio.create_task(self._run_connection_test(url, auth_type, username, password, token, api_key, custom_headers))

    async def _run_connection_test(self, url, auth_type, username, password, token, api_key, custom_headers):
        try:
            temp_feed = FeedProfile(id="temp", name="temp", url=url, auth_type=auth_type, username=username, password=password, bearer_token=token, api_key=api_key, custom_headers=custom_headers)
            async with APIClient(temp_feed) as client:
                response = await client.get(url)
                
                pixmap = None
                if response.status_code < 400:
                    icon_url, source = await self._discover_icon(url, auth_type, username, password, token, api_key, custom_headers)
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

    async def _discover_icon(self, url: str, auth_type: str = "none", username: str = None, password: str = None, token: str = None, api_key: str = None, custom_headers: Optional[Dict[str, str]] = None) -> tuple[Optional[str], str]:
        """Discover feed icon via OPDS Auth Doc, root feed, or site HTML. Returns (url, source_name)."""
        logger.debug(f"Starting icon discovery for {url}")
        icon_url = None
        source = "None"

        async def is_valid_icon(test_url, test_client):
            if not test_url: return False
            # data: URIs are self-contained and don't need network verification
            if test_url.startswith("data:"):
                return True
            try:
                # Use GET to verify the image exists and is an image
                resp = await test_client.get(test_url, timeout=5.0)
                if resp.status_code == 200:
                    ct = resp.headers.get("content-type", "").lower()
                    # Some servers return octet-stream for images, so check extension too
                    return "image" in ct or "octet-stream" in ct or test_url.lower().endswith((".ico", ".png", ".jpg", ".jpeg"))
            except:
                pass
            return False

        try:
            temp_feed = FeedProfile(id="temp", name="temp", url=url, auth_type=auth_type, username=username, password=password, bearer_token=token, api_key=api_key, custom_headers=custom_headers or {})
            async with APIClient(temp_feed) as client:
                response = await client.get(url)
                
                auth_doc_url = None
                feed_logo_url = None
                
                if response.status_code == 200:
                    content_type = response.headers.get("content-type", "").lower()
                    is_xml = "xml" in content_type or "atom" in content_type
                    
                    if is_xml:
                        try:
                            import xml.etree.ElementTree as ET
                            root = ET.fromstring(response.text)
                            def _strip_ns(tag): return tag.split('}', 1)[1] if '}' in tag else tag
                            def _resolve(base, h):
                                if not h: return None
                                if h.startswith("data:") or h.startswith("image/") or ";base64," in h:
                                    return h if h.startswith("data:") else f"data:{h}"
                                return urljoin(base, h)

                            for child in root:
                                tag = _strip_ns(child.tag)
                                if not feed_logo_url and tag in ["icon", "logo"]:
                                    feed_logo_url = _resolve(url, child.text)
                                if tag == "link":
                                    rel = child.get("rel", "")
                                    href = child.get("href")
                                    if href:
                                        if "authenticate" in rel or "http://opds-spec.org/auth/document" in rel:
                                            auth_doc_url = _resolve(url, href)
                                        if not feed_logo_url and ("logo" in rel or "icon" in rel):
                                            feed_logo_url = _resolve(url, href)
                                        if rel == "search" and "opensearchdescription+xml" in child.get("type", ""):
                                            # Quick OSDD check
                                            try:
                                                osdd_resp = await client.get(_resolve(url, href))
                                                if osdd_resp.status_code == 200:
                                                    osdd_root = ET.fromstring(osdd_resp.text)
                                                    for os_child in osdd_root:
                                                        if _strip_ns(os_child.tag) == "Image":
                                                            feed_logo_url = _resolve(url, os_child.text)
                                                            break
                                            except: pass
                        except: pass
                    else:
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
                        candidate = None
                        for al in auth_links:
                            if al.get("rel") in ["logo", "icon"]:
                                candidate = urljoin(auth_doc_url, al.get("href"))
                                break
                        if not candidate:
                            candidate = auth_data.get("logo") or auth_data.get("icon")
                            if candidate and not candidate.startswith("http"):
                                candidate = urljoin(auth_doc_url, candidate)
                        
                        if await is_valid_icon(candidate, client):
                            icon_url = candidate
                            source = "OPDS Authentication Document"
                
                # Priority 2: Feed Logo
                if not icon_url and feed_logo_url:
                    if await is_valid_icon(feed_logo_url, client):
                        icon_url = feed_logo_url
                        source = "OPDS Feed Logo"

                # Priority 3: Site HTML Probing (Subpath-aware)
                if not icon_url:
                    parsed = urlparse(url)
                    # Try probing up the path to find the application root (e.g. /komga/ instead of just /)
                    path_parts = [p for p in parsed.path.split('/') if p]
                    search_roots = []
                    
                    # 1. Domain Root
                    search_roots.append(f"{parsed.scheme}://{parsed.netloc}/")
                    
                    # 2. Walk up the path (max 3 levels)
                    current_path = ""
                    for i in range(min(len(path_parts), 3)):
                        current_path += f"/{path_parts[i]}"
                        search_roots.append(f"{parsed.scheme}://{parsed.netloc}{current_path}/")
                    
                    # Remove duplicates and reverse so we check deeper (more specific) paths first
                    search_roots = list(dict.fromkeys(search_roots))
                    search_roots.reverse()

                    for root_url in search_roots:
                        try:
                            site_resp = await client.get(root_url, timeout=5.0)
                            if site_resp.status_code == 200 and "text/html" in site_resp.headers.get("content-type", ""):
                                import re
                                # Look for shortcut icon or icon in HTML
                                match = re.search(r'<link[^>]*rel=["\'](?:shortcut )?icon["\'][^>]*href=["\'](.*?)["\']', site_resp.text, re.IGNORECASE)
                                if match:
                                    candidate = urljoin(root_url, match.group(1))
                                    if await is_valid_icon(candidate, client):
                                        icon_url = candidate
                                        source = f"Site HTML Icon ({root_url})"
                                        break
                        except:
                            pass

                # Priority 4: Default Favicon Fallback (Domain Root)
                if not icon_url:
                    parsed = urlparse(url)
                    base = f"{parsed.scheme}://{parsed.netloc}"
                    test_url = urljoin(base, "/favicon.ico")
                    if await is_valid_icon(test_url, client):
                        icon_url = test_url
                        source = "Favicon (Fallback)"
        except Exception as e:
            logger.debug(f"Icon discovery failed for {url}: {e}")
            
        logger.debug(f"Final icon URL for {url}: {icon_url}")
        return icon_url, source

    def save_and_close(self):
        name = self.name_input.text().strip()
        url = self.url_input.text().strip()
        if not name or not url:
            QMessageBox.warning(self, "Validation Error", "Name and URL are required.")
            return

        auth_type = self.auth_type_combo.currentData()
        username = self.user_input.text() or None
        password = self.pass_input.text() or None
        token = self.token_input.text() or None
        api_key = self.apikey_input.text() or None

        # Parse custom headers
        custom_headers = {}
        header_text = self.headers_input.toPlainText().strip()
        if header_text:
            for line in header_text.split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    custom_headers[k.strip()] = v.strip()

        if self.feed:
            self.feed.name = name
            self.feed.url = url
            self.feed.auth_type = auth_type
            self.feed.username = username
            self.feed.password = password
            self.feed.bearer_token = token
            self.feed.api_key = api_key
            self.feed.custom_headers = custom_headers
            self.config_manager.update_feed(self.feed)
            asyncio.create_task(self._discover_and_save_icon(self.feed))
        else:
            new_feed = self.config_manager.add_feed(name, url, auth_type, username, password, token, api_key, custom_headers=custom_headers)
            asyncio.create_task(self._discover_and_save_icon(new_feed))
        
        self.accept()

    async def _discover_and_save_icon(self, feed: FeedProfile):
        icon_url, _ = await self._discover_icon(feed.url, feed.auth_type, feed.username, feed.password, feed.bearer_token, feed.api_key, feed.custom_headers)
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
        s = UIConstants.scale
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(s(8))

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self.title_label = QLabel("Content Feeds (OPDS)")
        header.addWidget(self.title_label)
        header.addStretch()
        self.layout.addLayout(header)

        self.feeds_list = QListWidget()
        self.feeds_list.setIconSize(QSize(UIConstants.FEED_ICON_SIZE_SMALL, UIConstants.FEED_ICON_SIZE_SMALL))
        self.feeds_list.setMinimumHeight(s(160)) # Roughly 3 items
        self.feeds_list.itemDoubleClicked.connect(self.edit_selected)
        self.layout.addWidget(self.feeds_list)

        self.list_btns = QHBoxLayout()
        self.btn_edit = QPushButton("Edit")
        self.btn_edit.setObjectName("secondary_button")
        self.btn_edit.setIcon(ThemeManager.get_icon("label", "accent"))
        self.btn_edit.setIconSize(QSize(s(18), s(18)))
        self.btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_edit.clicked.connect(self.edit_selected)
        
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setObjectName("secondary_button")
        self.btn_delete.setIcon(ThemeManager.get_icon("action_delete", "danger"))
        self.btn_delete.setIconSize(QSize(s(18), s(18)))
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.clicked.connect(self.delete_selected)
        
        self.btn_add = QPushButton("Add New Feed")
        self.btn_add.setObjectName("primary_button")
        self.btn_add.setIcon(ThemeManager.get_icon("plus", "white"))
        self.btn_add.setIconSize(QSize(s(18), s(18)))
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.clicked.connect(self.add_feed)
        
        self.list_btns.addWidget(self.btn_edit)
        self.list_btns.addWidget(self.btn_delete)
        self.list_btns.addStretch()
        self.list_btns.addWidget(self.btn_add)
        self.layout.addLayout(self.list_btns)

        self.reapply_theme()
        self.refresh_feeds()

    def reapply_theme(self):
        theme = ThemeManager.get_current_theme_colors()
        s = UIConstants.scale
        self.title_label.setStyleSheet(f"font-size: {UIConstants.FONT_SIZE_DETAIL_SUBTITLE}px; font-weight: bold; color: {theme['accent']}; margin-bottom: {s(5)}px;")
        
        # Scale list font
        font = self.feeds_list.font()
        font.setPixelSize(UIConstants.FONT_SIZE_FEED_LIST)
        self.feeds_list.setFont(font)
        
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

    def refresh_feeds(self):
        default_icon = ThemeManager.get_icon("feeds")
        theme = ThemeManager.get_current_theme_colors()
        s = UIConstants.scale
        
        self.feeds_list.clear()
        for f in self.config_manager.feeds:
            name_fs = UIConstants.FONT_SIZE_FEED_NAME_SMALL
            url_fs = UIConstants.FONT_SIZE_FEED_URL_SMALL
            rich_text = f'<b><span style="font-size: {name_fs}px;">{f.name}</span></b><br/><span style="font-size: {url_fs}px; color: {theme["text_dim"]};">{f.url}</span>'

            item = QListWidgetItem()
            self.feeds_list.addItem(item)
            
            widget = QWidget()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(s(15), s(6), s(15), s(6))
            layout.setSpacing(s(10))
            
            icon_size = UIConstants.FEED_ICON_SIZE_SMALL
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
                    scaled = pixmap.scaled(UIConstants.FEED_ICON_SIZE_SMALL, UIConstants.FEED_ICON_SIZE_SMALL, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    label.setPixmap(scaled)
                    self.icon_loaded.emit(feed.id, pixmap)
        except: pass

    def add_feed(self):
        dialog = FeedEditDialog(self.window(), self.config_manager, self.shared_image_manager)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_feeds()

    def edit_selected(self):
        item = self.feeds_list.currentItem()
        if item:
            feed = item.data(Qt.ItemDataRole.UserRole)
            dialog = FeedEditDialog(self.window(), self.config_manager, self.shared_image_manager, feed)
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
