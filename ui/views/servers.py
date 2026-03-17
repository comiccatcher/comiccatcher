import asyncio
import httpx
from typing import Optional, Dict, Any
from urllib.parse import urljoin, urlparse

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QLineEdit, QPushButton, QFormLayout, QGroupBox, QMessageBox,
    QDialog, QApplication, QStyle, QFrame
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap

from config import ConfigManager
from models.server import ServerProfile
from api.client import APIClient
from api.image_manager import ImageManager
from logger import get_logger

logger = get_logger("ui.servers")

class ConnectionTestDialog(QDialog):
    def __init__(self, parent, success: bool, message: str, icon_pixmap: QPixmap = None):
        super().__init__(parent)
        self.setWindowTitle("Connection Test Result")
        self.setFixedWidth(400)
        self.setStyleSheet("background-color: #1e1e1e; color: white;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(20)
        
        # Icon / Logo
        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if icon_pixmap and not icon_pixmap.isNull():
            icon_label.setPixmap(icon_pixmap.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            style = QApplication.style()
            icon_type = QStyle.StandardPixmap.SP_DriveNetIcon if success else QStyle.StandardPixmap.SP_MessageBoxCritical
            def_icon = style.standardIcon(icon_type)
            icon_label.setPixmap(def_icon.pixmap(80, 80))
        layout.addWidget(icon_label)
        
        # Status Text
        status_title = QLabel("SUCCESS" if success else "CONNECTION FAILED")
        status_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_title.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {'#4caf50' if success else '#f44336'};")
        layout.addWidget(status_title)
        
        # Message
        msg_label = QLabel(message)
        msg_label.setWordWrap(True)
        msg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg_label.setStyleSheet("color: #ccc; font-size: 13px; line-height: 1.4;")
        layout.addWidget(msg_label)
        
        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: #333;")
        layout.addWidget(line)

        # OK Button
        btn_ok = QPushButton("Got it")
        btn_ok.setFixedWidth(120)
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.setStyleSheet("""
            QPushButton {
                background-color: #3e3e42;
                color: white;
                border: 1px solid #454545;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #505050;
            }
        """)
        btn_ok.clicked.connect(self.accept)
        
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_ok)
        btn_row.addStretch()
        layout.addLayout(btn_row)

class ServersView(QWidget):
    icon_loaded = pyqtSignal(str, object) # profile_id, pixmap

    def __init__(self, config_manager: ConfigManager, on_profile_selected):
        super().__init__()
        self.config_manager = config_manager
        self.on_profile_selected = on_profile_selected
        self.editing_profile_id = None
        
        # Global image manager for basic caching
        self.shared_image_manager = ImageManager(None)

        self.layout = QVBoxLayout(self)

        # Profiles List
        self.layout.addWidget(QLabel("Server Profiles"))
        self.profiles_list = QListWidget()
        self.profiles_list.setIconSize(QSize(32, 32))
        self.profiles_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.layout.addWidget(self.profiles_list)

        # Buttons for selected item
        self.list_btns = QHBoxLayout()
        self.btn_browse = QPushButton("Browse")
        self.btn_browse.clicked.connect(self.browse_selected)
        self.btn_edit = QPushButton("Edit")
        self.btn_edit.clicked.connect(self.edit_selected)
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setStyleSheet("background-color: #d32f2f; color: white;")
        self.btn_delete.clicked.connect(self.delete_selected)
        
        self.list_btns.addWidget(self.btn_browse)
        self.list_btns.addWidget(self.btn_edit)
        self.list_btns.addWidget(self.btn_delete)
        self.layout.addLayout(self.list_btns)

        # Add/Edit Form
        self.form_group = QGroupBox("Add / Edit Profile")
        self.form_layout = QFormLayout(self.form_group)

        self.name_input = QLineEdit()
        self.url_input = QLineEdit()
        self.user_input = QLineEdit()
        self.pass_input = QLineEdit()
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_input = QLineEdit()
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.form_layout.addRow("Name:", self.name_input)
        self.form_layout.addRow("URL:", self.url_input)
        self.form_layout.addRow("Username:", self.user_input)
        self.form_layout.addRow("Password:", self.pass_input)
        self.form_layout.addRow("Token:", self.token_input)

        self.btn_save = QPushButton("Add Profile")
        self.btn_save.clicked.connect(self.save_profile)
        self.btn_test = QPushButton("Test Connection")
        self.btn_test.clicked.connect(self.test_connection)
        self.btn_cancel = QPushButton("Cancel Edit")
        self.btn_cancel.clicked.connect(self.cancel_edit)
        self.btn_cancel.setVisible(False)

        self.form_btns = QHBoxLayout()
        self.form_btns.addWidget(self.btn_save)
        self.form_btns.addWidget(self.btn_test)
        self.form_btns.addWidget(self.btn_cancel)
        self.form_layout.addRow(self.form_btns)

        self.layout.addWidget(self.form_group)

        self.refresh_profiles()

    def refresh_profiles(self):
        style = QApplication.style()
        default_icon = style.standardIcon(QStyle.StandardPixmap.SP_DriveNetIcon)
        
        self.profiles_list.clear()
        for p in self.config_manager.profiles:
            item = QListWidgetItem(f"{p.name}\n{p.url}")
            item.setData(Qt.ItemDataRole.UserRole, p)
            item.setIcon(default_icon)
            self.profiles_list.addItem(item)
            
            if p.icon_url:
                asyncio.create_task(self._load_cached_icon(p, item))

    async def _load_cached_icon(self, profile: ServerProfile, item: QListWidgetItem):
        try:
            client = APIClient(profile)
            asset_path = await self.shared_image_manager.get_image_asset_path(profile.icon_url, api_client=client)
            if asset_path:
                from config import CACHE_DIR
                import hashlib
                url_hash = hashlib.sha256(profile.icon_url.encode("utf-8")).hexdigest()
                full_path = CACHE_DIR / url_hash[:2] / url_hash
                if full_path.exists():
                    pixmap = QPixmap(str(full_path))
                    if not pixmap.isNull():
                        setattr(profile, "_cached_icon", pixmap)
                        if item:
                            item.setIcon(QIcon(pixmap))
                        self.icon_loaded.emit(profile.id, pixmap)
            await client.close()
        except Exception as e:
            logger.debug(f"Failed loading cached icon for {profile.name}: {e}")

    async def _discover_icon(self, url: str, username: str = None, password: str = None, token: str = None) -> tuple[Optional[str], str]:
        """Discover server icon via OPDS Auth Doc or root feed. Returns (url, source_name)."""
        logger.debug(f"Starting icon discovery for {url}")
        icon_url = None
        source = "None"
        try:
            temp_profile = ServerProfile(id="temp", name="temp", url=url, username=username, password=password, bearer_token=token)
            async with APIClient(temp_profile) as client:
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
            temp_profile = ServerProfile(id="temp", name="temp", url=url, username=username, password=password, bearer_token=token)
            async with APIClient(temp_profile) as client:
                response = await client.get(url)
                
                pixmap = None
                if response.status_code < 400:
                    icon_url, source = await self._discover_icon(url, username, password, token)
                    if icon_url:
                        asset_path = await self.shared_image_manager.get_image_asset_path(icon_url, api_client=client)
                        if asset_path:
                            from config import CACHE_DIR
                            import hashlib
                            url_hash = hashlib.sha256(icon_url.encode("utf-8")).hexdigest()
                            full_path = CACHE_DIR / url_hash[:2] / url_hash
                            if full_path.exists():
                                pixmap = QPixmap(str(full_path))
                    
                    msg = f"Connected successfully to {url}.\nStatus Code: {response.status_code}\n\nIcon found via: {source}"
                    if response.status_code == 200:
                        msg += "\n\nServer returned a valid OPDS 2.0 feed."
                    elif response.status_code == 401:
                        msg += "\n\nNote: Server requires authentication."
                    
                    dialog = ConnectionTestDialog(self, True, msg, pixmap)
                    dialog.exec()
                else:
                    msg = f"Server returned status {response.status_code} for {url}"
                    if response.status_code == 401:
                        msg += "\n\nAuthentication failed. Please check your credentials."
                    dialog = ConnectionTestDialog(self, False, msg)
                    dialog.exec()
        except Exception as e:
            dialog = ConnectionTestDialog(self, False, f"Could not connect to {url}\n\nError: {str(e)}")
            dialog.exec()
        finally:
            self.btn_test.setEnabled(True)
            self.btn_test.setText("Test Connection")

    def _on_item_double_clicked(self, item):
        profile = item.data(Qt.ItemDataRole.UserRole)
        if profile:
            self.on_profile_selected(profile)

    def browse_selected(self):
        item = self.profiles_list.currentItem()
        if item:
            profile = item.data(Qt.ItemDataRole.UserRole)
            self.on_profile_selected(profile)

    def edit_selected(self):
        item = self.profiles_list.currentItem()
        if item:
            profile = item.data(Qt.ItemDataRole.UserRole)
            self.start_edit(profile)

    def delete_selected(self):
        item = self.profiles_list.currentItem()
        if item:
            profile = item.data(Qt.ItemDataRole.UserRole)
            reply = QMessageBox.question(self, 'Delete Profile', 
                                       f"Are you sure you want to delete '{profile.name}'?",
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.config_manager.remove_profile(profile.id)
                self.refresh_profiles()

    def start_edit(self, profile: ServerProfile):
        self.editing_profile_id = profile.id
        self.name_input.setText(profile.name)
        self.url_input.setText(profile.url)
        self.user_input.setText(profile.username or "")
        self.pass_input.setText(profile.password or "")
        self.token_input.setText(profile.bearer_token or "")
        
        self.btn_save.setText("Update Profile")
        self.btn_cancel.setVisible(True)

    def cancel_edit(self):
        self.editing_profile_id = None
        self.name_input.clear()
        self.url_input.clear()
        self.user_input.clear()
        self.pass_input.clear()
        self.token_input.clear()
        
        self.btn_save.setText("Add Profile")
        self.btn_cancel.setVisible(False)

    def save_profile(self):
        name = self.name_input.text()
        url = self.url_input.text()
        if not name or not url:
            QMessageBox.warning(self, "Validation Error", "Name and URL are required.")
            return
            
        username = self.user_input.text() or None
        password = self.pass_input.text() or None
        token = self.token_input.text() or None
            
        if self.editing_profile_id:
            profile = self.config_manager.get_profile(self.editing_profile_id)
            if profile:
                profile.name = name
                profile.url = url
                profile.username = username
                profile.password = password
                profile.bearer_token = token
                self.config_manager.update_profile(profile)
                asyncio.create_task(self.discover_and_save_icon(profile))
        else:
            new_profile = self.config_manager.add_profile(
                name=name,
                url=url,
                username=username,
                password=password,
                token=token
            )
            asyncio.create_task(self.discover_and_save_icon(new_profile))
        
        self.cancel_edit()
        self.refresh_profiles()

    async def discover_and_save_icon(self, profile: ServerProfile):
        """Discovers, saves, and emits the icon for a profile."""
        icon_url, source = await self._discover_icon(profile.url, profile.username, profile.password, profile.bearer_token)
        if icon_url:
            profile.icon_url = icon_url
            self.config_manager.update_profile(profile)
        
        # Always try to load the icon into memory and emit
        item = None
        for i in range(self.profiles_list.count()):
            it = self.profiles_list.item(i)
            if it.data(Qt.ItemDataRole.UserRole).id == profile.id:
                item = it
                break
        await self._load_cached_icon(profile, item)
