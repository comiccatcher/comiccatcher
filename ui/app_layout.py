import asyncio
import os
import traceback
from pathlib import Path
from urllib.parse import urljoin

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, 
    QListWidget, QListWidgetItem, QStackedWidget, QLabel, QPushButton, QFrame,
    QDialog, QTextEdit, QMessageBox, QStyle, QApplication
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon

from config import ConfigManager
from ui.views.servers import ServersView
from ui.views.library import LocalLibraryView
from ui.views.library_detail import LocalComicDetailView
from ui.views.local_reader import LocalReaderView
from ui.views.browser import BrowserView
from ui.views.detail import DetailView
from ui.views.reader import ReaderView
from ui.views.settings import SettingsView
from ui.views.downloads import DownloadsView
from api.download_manager import DownloadManager
import logger

class MainWindow(QMainWindow):
    def __init__(self, config_manager: ConfigManager):
        super().__init__()
        self.config_manager = config_manager
        self.setWindowTitle("ComicCatcher")
        self.resize(1200, 800)

        self.api_client = None
        self.opds_client = None
        self.image_manager = None
        self.download_manager = None
        
        # History state for breadcrumbs
        self.history = []
        self.current_index = -1

        # Main horizontal layout (Sidebar | Content)
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QHBoxLayout(self.central_widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Sidebar
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(160)
        self.sidebar.setStyleSheet("background-color: #1e1e1e; color: white;")
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(0, 20, 0, 5)

        self.nav_list = QListWidget()
        self.nav_list.setStyleSheet("""
            QListWidget {
                border: none;
                outline: none;
                background-color: transparent;
            }
            QListWidget::item {
                padding: 12px;
                color: #ccc;
                border-left: 3px solid transparent;
            }
            QListWidget::item:selected {
                background-color: #2d2d2d;
                color: white;
                border-left: 3px solid #3791ef;
            }
            QListWidget::item:hover {
                background-color: #252525;
            }
        """)
        self.nav_list.setIconSize(QSize(20, 20))
        
        style = QApplication.instance().style()
        
        def add_nav_item(text, icon_type):
            item = QListWidgetItem(text)
            item.setIcon(style.standardIcon(icon_type))
            self.nav_list.addItem(item)

        add_nav_item("Servers", QStyle.StandardPixmap.SP_ComputerIcon)
        add_nav_item("Settings", QStyle.StandardPixmap.SP_FileDialogDetailedView)
        add_nav_item("Browser", QStyle.StandardPixmap.SP_FileDialogContentsView)
        add_nav_item("Library", QStyle.StandardPixmap.SP_DirHomeIcon)
        add_nav_item("Downloads", QStyle.StandardPixmap.SP_ArrowDown)
        
        self.nav_list.currentRowChanged.connect(self._on_sidebar_changed)
        self.sidebar_layout.addWidget(self.nav_list)
        
        self.layout.addWidget(self.sidebar)

        # Main Vertical Layout (Header | Content)
        self.main_area = QWidget()
        self.main_layout = QVBoxLayout(self.main_area)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        self.layout.addWidget(self.main_area, 1)

        # Top Header (Debug + Breadcrumbs)
        self.top_header = QFrame()
        self.top_header.setFixedHeight(80)
        self.top_header.setStyleSheet("background-color: #252526; border-bottom: 1px solid #333;")
        self.header_layout = QVBoxLayout(self.top_header)
        self.header_layout.setContentsMargins(10, 5, 10, 5)
        self.header_layout.setSpacing(2)

        # Debug Row
        self.debug_row = QFrame()
        self.debug_layout = QHBoxLayout(self.debug_row)
        self.debug_layout.setContentsMargins(0, 0, 0, 0)
        
        self.history_counter = QLabel("[0/0]")
        self.history_counter.setStyleSheet("color: #3791ef; font-size: 10px; font-weight: bold;")
        self.debug_url_text = QLabel("")
        self.debug_url_text.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")
        
        self.btn_logs = QPushButton("Logs")
        self.btn_logs.setFixedSize(40, 20)
        self.btn_logs.setStyleSheet("font-size: 9px;")
        self.btn_logs.clicked.connect(self._show_logs_dialog)
        
        self.btn_copy = QPushButton("Copy")
        self.btn_copy.setFixedSize(40, 20)
        self.btn_copy.setStyleSheet("font-size: 9px;")
        self.btn_copy.clicked.connect(self._copy_url_to_clipboard)
        
        self.debug_layout.addWidget(self.history_counter)
        self.debug_layout.addWidget(self.debug_url_text, 1)
        self.debug_layout.addWidget(self.btn_copy)
        self.debug_layout.addWidget(self.btn_logs)
        self.header_layout.addWidget(self.debug_row)

        # Breadcrumb Row
        self.breadcrumb_container = QFrame()
        self.breadcrumb_row = QHBoxLayout(self.breadcrumb_container)
        self.breadcrumb_row.setContentsMargins(0, 0, 0, 0)
        
        self.breadcrumb_items_layout = QHBoxLayout()
        self.breadcrumb_items_layout.setSpacing(5)
        
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setFixedSize(60, 25)
        self.btn_refresh.clicked.connect(self.on_manual_refresh)
        
        self.breadcrumb_row.addLayout(self.breadcrumb_items_layout)
        self.breadcrumb_row.addStretch()
        self.breadcrumb_row.addWidget(self.btn_refresh)
        
        self.header_layout.addWidget(self.breadcrumb_container)
        
        self.main_layout.addWidget(self.top_header)

        # Content Area
        self.content_stack = QStackedWidget()
        self.main_layout.addWidget(self.content_stack)

        # Initialize Views
        self.servers_view = ServersView(self.config_manager, self.on_profile_selected)
        self.servers_view.icon_loaded.connect(self._on_server_icon_loaded)
        self.settings_view = SettingsView(self.config_manager)
        self.browser_view = BrowserView(self.config_manager, self.on_open_detail, self.on_navigate_to_url, on_offset_change=self._on_browser_offset_changed)
        self.local_library_view = LocalLibraryView(self.config_manager, self.on_open_local_comic)
        self.local_detail_view = LocalComicDetailView(self.on_back_to_local_library, self.on_read_local_comic)
        self.local_reader_view = LocalReaderView(self.on_exit_reader)
        
        self.detail_view = DetailView(self.on_back_to_browser, self.on_read_book, self.on_navigate_to_url, self.on_start_download, self.on_open_detail)
        self.reader_view = ReaderView(None, self.on_exit_reader)
        self.downloads_view = DownloadsView(None)

        self.content_stack.addWidget(self.servers_view)      # Index 0
        self.content_stack.addWidget(self.settings_view)     # Index 1
        self.content_stack.addWidget(self.browser_view)       # Index 2
        self.content_stack.addWidget(self.local_library_view)  # Index 3
        self.content_stack.addWidget(self.downloads_view)     # Index 4
        self.content_stack.addWidget(self.local_detail_view)   # Index 5
        self.content_stack.addWidget(self.local_reader_view)   # Index 6
        self.content_stack.addWidget(self.detail_view)         # Index 7
        self.content_stack.addWidget(self.reader_view)         # Index 8

        self.nav_list.setCurrentRow(0)
        self.update_header()

    def _on_sidebar_changed(self, index):
        self.content_stack.setCurrentIndex(index)
        self.top_header.setVisible(index not in (6, 8))
        if index == 2: # Browser
            self.browser_view.setFocus()

    def _on_browser_offset_changed(self, offset):
        if self.current_index >= 0 and self.history[self.current_index]["type"] == "browser":
            self.history[self.current_index]["offset"] = offset

    def _on_server_icon_loaded(self, profile_id, pixmap):
        # Update history entries that belong to this specific profile
        updated = False
        for entry in self.history:
            if entry.get("profile_id") == profile_id:
                # Always update the icon if we got a new one, to replace defaults
                entry["icon"] = pixmap
                updated = True
        
        if updated:
            self.update_header()

    def update_header(self):
        # Clear breadcrumbs
        for i in reversed(range(self.breadcrumb_items_layout.count())):
            item = self.breadcrumb_items_layout.itemAt(i)
            if item.widget():
                item.widget().setParent(None)
        
        if not self.history:
            self.top_header.setVisible(False)
            return
            
        self.top_header.setVisible(self.content_stack.currentIndex() not in (6, 8))
        
        # Debug Data
        entry = self.history[self.current_index]
        self.debug_url_text.setText(entry.get("url", ""))
        self.history_counter.setText(f"[{self.current_index + 1}/{len(self.history)}]")
        self.debug_row.setVisible(os.getenv("DEBUG") == "1")
        
        for i, entry in enumerate(self.history):
            title = entry.get("title", "...")
            
            # Container for icon + text
            item_widget = QWidget()
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(5)
            
            if i == 0:
                icon_pixmap = entry.get("icon")
                icon_label = QLabel()
                if icon_pixmap:
                    icon_label.setPixmap(icon_pixmap.scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                else:
                    from PyQt6.QtWidgets import QApplication, QStyle
                    icon_label.setPixmap(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DriveNetIcon).pixmap(16, 16))
                item_layout.addWidget(icon_label)

            if i == self.current_index:
                label = QLabel(title)
                label.setStyleSheet("font-weight: bold; color: #3791ef; font-size: 14px;")
                item_layout.addWidget(label)
            else:
                btn = QPushButton(title)
                btn.setFlat(True)
                btn.setStyleSheet("text-align: left; padding: 2px; color: #ccc; font-size: 14px;")
                btn.clicked.connect(lambda _, idx=i: self.on_jump_to_history(idx))
                item_layout.addWidget(btn)
            
            self.breadcrumb_items_layout.addWidget(item_widget)
                
            if i < len(self.history) - 1:
                sep = QLabel(">")
                sep.setStyleSheet("color: #666;")
                self.breadcrumb_items_layout.addWidget(sep)

    def on_profile_selected(self, profile):
        from api.client import APIClient
        from api.opds_v2 import OPDS2Client
        from api.image_manager import ImageManager
        
        self.api_client = APIClient(profile)
        self.opds_client = OPDS2Client(self.api_client)
        self.image_manager = ImageManager(self.api_client)
        self.download_manager = DownloadManager(self.api_client, self.config_manager.get_library_dir())
        
        self.browser_view.load_profile(profile)
        self.reader_view.api_client = self.api_client
        self.downloads_view.dm = self.download_manager
        self.download_manager.set_callback(self.downloads_view.refresh_tasks)
        
        self.history.clear()
        self.current_index = -1
        
        base_url = profile.url
        start_url = base_url if "opds" in base_url.lower() else urljoin(base_url, "/codex/opds/v2.0/")
        
        # Capture the icon from the profile
        icon = getattr(profile, "_cached_icon", None)
        
        # Trigger discovery to find a better icon (e.g. via Auth Doc) 
        # even if we have a generic favicon URL already.
        if not icon:
            # Fallback to default immediately
            from PyQt6.QtWidgets import QApplication, QStyle
            icon = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DriveNetIcon).pixmap(16, 16)
            
        # Always try to discover/refresh the icon in the background
        asyncio.create_task(self.servers_view.discover_and_save_icon(profile))
        
        # Store profile_id in the navigation call
        self.on_navigate_to_url(start_url, title=profile.name, icon=icon, profile_id=profile.id)
        self.nav_list.setCurrentRow(2)

    def on_navigate_to_url(self, url, title="Loading...", replace=False, keep_title=False, icon=None, profile_id=None):
        if replace and self.current_index >= 0:
            self.history[self.current_index]["url"] = url
            if not keep_title:
                self.history[self.current_index]["title"] = title
            if icon:
                self.history[self.current_index]["icon"] = icon
        else:
            if self.current_index < len(self.history) - 1:
                self.history = self.history[:self.current_index + 1]
            
            # Inherit profile_id from previous entry if not provided (paging/sub-navigation)
            pid = profile_id
            if not pid and self.current_index >= 0:
                pid = self.history[self.current_index].get("profile_id")
            
            # Icon is only stored for the root entry (server)
            ic = icon if len(self.history) == 0 else None

            self.history.append({
                "type": "browser", 
                "title": title, 
                "url": url, 
                "pub": None, 
                "icon": ic, 
                "profile_id": pid,
                "offset": 0
            })
            self.current_index = len(self.history) - 1
            
        self.update_header()
        asyncio.create_task(self.browser_view.load_feed(url, title))
        self.content_stack.setCurrentIndex(2)
        self.browser_view.setFocus()

    def on_open_detail(self, pub, self_url):
        if self.current_index < len(self.history) - 1:
            self.history = self.history[:self.current_index + 1]
        
        # Inherit profile for detail view too (but no icon needed here)
        pid = self.history[self.current_index].get("profile_id") if self.current_index >= 0 else None

        self.history.append({
            "type": "detail", 
            "title": pub.metadata.title, 
            "url": self_url, 
            "pub": pub,
            "profile_id": pid,
            "icon": None
        })
        self.current_index = len(self.history) - 1
        
        self.update_header()
        self.detail_view.load_publication(pub, self_url, self.api_client, self.opds_client, self.image_manager)
        self.content_stack.setCurrentIndex(7)

    def on_jump_to_history(self, index):
        self.history = self.history[:index + 1]
        self.current_index = index
        entry = self.history[index]
        
        self.update_header()
        if entry["type"] == "browser":
            asyncio.create_task(self.browser_view.load_feed(entry["url"], entry["title"], initial_offset=entry.get("offset", 0)))
            self.content_stack.setCurrentIndex(2)
            self.browser_view.setFocus()
        else:
            self.detail_view.load_publication(entry["pub"], entry["url"], self.api_client, self.opds_client, self.image_manager)
            self.content_stack.setCurrentIndex(7)

    def on_manual_refresh(self):
        if self.current_index < 0: return
        entry = self.history[self.current_index]
        if entry["type"] == "browser":
            asyncio.create_task(self.browser_view.load_feed(entry["url"], entry["title"], force_refresh=True, initial_offset=entry.get("offset", 0)))
        else:
            self.detail_view.load_publication(entry["pub"], entry["url"], self.api_client, self.opds_client, self.image_manager, force_refresh=True)

    def _copy_url_to_clipboard(self):
        url = self.debug_url_text.text()
        if url:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(url)

    def _show_logs_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("System Logs")
        dialog.resize(800, 600)
        layout = QVBoxLayout(dialog)
        
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet("font-family: monospace; font-size: 10px; background-color: #1e1e1e; color: #ddd;")
        
        try:
            if os.path.exists("comiccatcher.log"):
                with open("comiccatcher.log", "r") as f:
                    text_edit.setPlainText("".join(f.readlines()[-200:]))
            else:
                text_edit.setPlainText("Log file not found.")
        except Exception as e:
            text_edit.setPlainText(f"Error reading logs: {e}")
            
        layout.addWidget(text_edit)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(dialog.accept)
        layout.addWidget(btn_close)
        dialog.exec()

    def on_read_book(self, pub, manifest_url):
        self.reader_view.load_manifest(pub, manifest_url)
        self.content_stack.setCurrentIndex(8)
        self.sidebar.hide()
        self.top_header.hide()

    def on_start_download(self, pub, url):
        if self.download_manager:
            asyncio.create_task(self.download_manager.start_download(pub.id, pub.metadata.title, url))
            self.nav_list.setCurrentRow(4)

    def on_open_local_comic(self, path):
        self.local_detail_view.load_path(path)
        self.content_stack.setCurrentIndex(5)

    def on_back_to_local_library(self):
        self.content_stack.setCurrentIndex(3)

    def on_back_to_browser(self):
        for i in range(self.current_index - 1, -1, -1):
            if self.history[i]["type"] == "browser":
                self.on_jump_to_history(i)
                self.browser_view.setFocus()
                return
        self.nav_list.setCurrentRow(0)

    def on_read_local_comic(self, path):
        self.local_reader_view.load_cbz(path)
        self.content_stack.setCurrentIndex(6)
        self.sidebar.hide()
        self.top_header.hide()

    def on_exit_reader(self):
        self.sidebar.show()
        self.top_header.show()
        if self.content_stack.currentIndex() == 6:
            self.content_stack.setCurrentIndex(5)
        else:
            self.content_stack.setCurrentIndex(7)
