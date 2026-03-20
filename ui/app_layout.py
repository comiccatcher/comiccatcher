import asyncio
import os
import traceback
import urllib.parse
from pathlib import Path
from urllib.parse import urljoin

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, 
    QListWidget, QListWidgetItem, QStackedWidget, QLabel, QPushButton, QFrame,
    QDialog, QTextEdit, QMessageBox, QStyle, QApplication, QLineEdit, QScrollArea,
    QLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize, QTimer, QRect, QPoint
from PyQt6.QtGui import QIcon

from config import ConfigManager, CONFIG_DIR
from ui.flow_layout import FlowLayout
from ui.views.feed_list import FeedListView
from ui.views.library import LocalLibraryView
from ui.views.library_detail import LocalComicDetailView
from ui.views.local_reader import LocalReaderView
from ui.views.browser import BrowserView
from ui.views.detail import DetailView
from ui.views.reader import ReaderView
from ui.views.settings import SettingsView
from ui.views.downloads import DownloadsView
from ui.views.search_root import SearchRootView
from ui.theme_manager import ThemeManager
from api.download_manager import DownloadManager
from api.client import APIClient
from api.local_db import LocalLibraryDB
from api.opds_v2 import OPDS2Client
from api.image_manager import ImageManager

from logger import get_logger
logger = get_logger("ui.app_layout")

class DownloadPopover(QFrame):
    def __init__(self, parent, download_manager: DownloadManager):
        super().__init__(parent)
        self.dm = download_manager
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setFixedWidth(350)
        self.setFixedHeight(400)
        self.setObjectName("download_popover")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.downloads_view = DownloadsView(self.dm)
        layout.addWidget(self.downloads_view)

    def show_at(self, pos: QPoint):
        # Position it so the top right of the popover is near the click pos
        # but with some padding
        adjusted_pos = QPoint(pos.x() - self.width() + 20, pos.y() + 10)
        self.move(adjusted_pos)
        self.show()

class MainWindow(QMainWindow):
    def __init__(self, config_manager: ConfigManager):
        super().__init__()
        self.config_manager = config_manager
        self.setWindowTitle("ComicCatcher")
        self.resize(1200, 800)

        # App Icon
        icon_path = Path(__file__).parent.parent / "resources" / "app.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        
        self.api_client = None
        self.opds_client = None
        self.image_manager = None
        self.download_manager = None
        self.local_db = LocalLibraryDB(CONFIG_DIR / "library.db")
        
        # Tabbed History State
        self.active_tab = "feed" # "feed" or "search"
        self.feed_history = []
        self.feed_index = -1
        self.search_history = []
        self.search_index = -1

        # Main horizontal layout (Sidebar | Content)
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QHBoxLayout(self.central_widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Sidebar (Narrower, Icons + Text Underneath)
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(85)
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_layout.setSpacing(0)

        self.nav_list = QListWidget()
        self.nav_list.setObjectName("nav_list") # For specific styling
        self.nav_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.nav_list.setFlow(QListWidget.Flow.TopToBottom)
        self.nav_list.setMovement(QListWidget.Movement.Static)
        self.nav_list.setSpacing(0)
        self.nav_list.setIconSize(QSize(32, 32))
        
        style = QApplication.instance().style()
        
        def add_nav_item(text, icon_name):
            item = QListWidgetItem(text)
            item.setIcon(ThemeManager.get_icon(icon_name))
            item.setSizeHint(QSize(85, 85))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.nav_list.addItem(item)

        add_nav_item("Feeds", "feeds")
        add_nav_item("Library", "library")
        add_nav_item("Settings", "settings")
        
        self.nav_list.currentRowChanged.connect(self._on_sidebar_changed)
        self.sidebar_layout.addWidget(self.nav_list)
        
        self.layout.addWidget(self.sidebar)

        # Main Vertical Layout (Header | Content)
        self.main_area = QWidget()
        self.main_layout = QVBoxLayout(self.main_area)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        self.layout.addWidget(self.main_area, 1)

        # Debug Bar (at the very top)
        self.debug_bar = QFrame()
        self.debug_bar.setObjectName("debug_bar")
        self.debug_bar.setFixedHeight(25)
        self.debug_layout = QHBoxLayout(self.debug_bar)
        self.debug_layout.setContentsMargins(10, 0, 10, 0)
        self.debug_layout.setSpacing(10)
        
        self.history_counter = QLabel("[0/0]")
        self.history_counter.setStyleSheet("font-size: 10px; font-weight: bold;")
        
        self.debug_url_text = QLineEdit("")
        self.debug_url_text.setReadOnly(True)
        self.debug_url_text.setStyleSheet("font-size: 10px; background: transparent; border: none;")
        
        self.btn_logs = QPushButton("Logs")
        self.btn_logs.setFixedSize(40, 18)
        self.btn_logs.setStyleSheet("font-size: 9px;")
        self.btn_logs.clicked.connect(self._show_logs_dialog)
        
        self.btn_copy = QPushButton("Copy")
        self.btn_copy.setFixedSize(40, 18)
        self.btn_copy.setStyleSheet("font-size: 9px;")
        self.btn_copy.clicked.connect(self._copy_url_to_clipboard)
        
        self.debug_layout.addWidget(self.history_counter)
        self.debug_layout.addWidget(self.debug_url_text, 1)
        self.debug_layout.addWidget(self.btn_copy)
        self.debug_layout.addWidget(self.btn_logs)
        
        self.main_layout.addWidget(self.debug_bar)
        self.debug_bar.setVisible(os.getenv("DEBUG") == "1")

        # Top Header (Feed Info + Tabs + Breadcrumbs + Downloads)
        self.top_header = QFrame()
        self.top_header.setObjectName("top_header")
        self.header_layout = QVBoxLayout(self.top_header)
        self.header_layout.setContentsMargins(10, 5, 10, 5)
        self.header_layout.setSpacing(5)

        # Row 1: Feed Info & Tabs & Downloads
        self.feed_info_row = QHBoxLayout()
        self.btn_back_header = QPushButton("Back")
        self.btn_back_header.setIcon(ThemeManager.get_icon("back"))
        self.btn_back_header.setIconSize(QSize(18, 18))
        self.btn_back_header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back_header.setToolTip("Go back")
        self.btn_back_header.clicked.connect(self._on_header_back_clicked)
        self.btn_back_header.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 4px 10px;
                font-weight: bold;
                font-size: 13px;
                text-align: left;
            }
            QPushButton:hover {
                background-color: rgba(128, 128, 128, 30);
                border-color: rgba(128, 128, 128, 50);
            }
            QPushButton:disabled {
                color: rgba(128, 128, 128, 100);
            }
        """)
        
        self.btn_tab_feed = QPushButton("Browse")
        self.btn_tab_feed.setObjectName("tab_button")
        self.btn_tab_feed.setIcon(ThemeManager.get_icon("home", "accent"))
        self.btn_tab_feed.setCheckable(True)
        self.btn_tab_feed.setChecked(True)
        self.btn_tab_feed.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tab_feed.clicked.connect(lambda: self._on_tab_clicked("feed"))

        self.btn_tab_search = QPushButton("Search")
        self.btn_tab_search.setObjectName("tab_button")
        self.btn_tab_search.setIcon(ThemeManager.get_icon("search", "text_dim"))
        self.btn_tab_search.setCheckable(True)
        self.btn_tab_search.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tab_search.clicked.connect(lambda: self._on_tab_clicked("search"))
        
        self.feed_info_row.addWidget(self.btn_back_header)
        self.feed_info_row.addSpacing(10)
        self.feed_info_row.addWidget(self.btn_tab_feed)
        self.feed_info_row.addWidget(self.btn_tab_search)
        
        self.feed_info_row.addStretch()
        
        # Global Download Button with Badge
        self.download_container = QWidget()
        self.download_layout = QVBoxLayout(self.download_container)
        self.download_layout.setContentsMargins(0, 0, 0, 0)
        
        self.btn_downloads = QPushButton()
        self.btn_downloads.setProperty("flat", "true")
        self.btn_downloads.setIcon(ThemeManager.get_icon("download"))
        self.btn_downloads.setFixedSize(32, 32)
        self.btn_downloads.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_downloads.clicked.connect(self._toggle_downloads_popover)
        
        self.download_badge = QLabel("0", self.btn_downloads)
        self.download_badge.setFixedSize(16, 16)
        self.download_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.download_badge.setObjectName("download_badge")
        self.download_badge.move(16, 0)
        self.download_badge.hide()
        
        self.feed_info_row.addWidget(self.btn_downloads)
        
        self.header_layout.addLayout(self.feed_info_row)

        # Row 2: Breadcrumb Row
        self.breadcrumb_container = QFrame()
        self.breadcrumb_row = QHBoxLayout(self.breadcrumb_container)
        self.breadcrumb_row.setContentsMargins(0, 0, 0, 0)
        self.breadcrumb_row.setSpacing(10)
        
        self.breadcrumb_inner = QWidget()
        self.breadcrumb_items_layout = FlowLayout(self.breadcrumb_inner, spacing=5)
        
        self.btn_refresh = QPushButton()
        self.btn_refresh.setProperty("flat", "true")
        self.btn_refresh.setIcon(ThemeManager.get_icon("refresh"))
        self.btn_refresh.setFixedSize(32, 32)
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.on_manual_refresh)
        self.btn_refresh.setToolTip("Refresh current view")
        
        self.breadcrumb_row.addWidget(self.breadcrumb_inner, 1)
        self.breadcrumb_row.addWidget(self.btn_refresh, 0, Qt.AlignmentFlag.AlignTop)
        
        self.header_layout.addWidget(self.breadcrumb_container)
        
        self.main_layout.addWidget(self.top_header)

        # Content Area
        self.content_stack = QStackedWidget()
        self.main_layout.addWidget(self.content_stack)

        # Initialize Views
        self.feed_list_view = FeedListView(self.config_manager, self.on_feed_selected)
        self.settings_view = SettingsView(self.config_manager)
        self.settings_view.theme_changed.connect(self._apply_theme)
        
        # Dual Browser Views
        self.feed_browser_view = BrowserView(self.config_manager, self.on_open_detail, self.on_navigate_to_url, self.on_start_download, on_offset_change=self._on_browser_offset_changed)
        self.search_browser_view = BrowserView(self.config_manager, self.on_open_detail, self.on_navigate_to_url, self.on_start_download, on_offset_change=self._on_browser_offset_changed)
        self.search_root_view = SearchRootView(
            on_search=lambda q: asyncio.create_task(self._execute_search(q)),
            on_pin=self._on_pin_search,
            on_remove=self._on_remove_search,
            on_clear=self._on_clear_search
        )
        
        self.local_library_view = LocalLibraryView(self.config_manager, self.on_open_local_comic, self.local_db)
        self.local_library_view.nav_changed.connect(self.update_header)
        self.local_detail_view = LocalComicDetailView(self.on_back_to_local_library, self.on_read_local_comic, self.local_db)
        self.local_reader_view = LocalReaderView(self.on_exit_reader, self.local_db)
        
        self.detail_view = DetailView(self.config_manager, self.on_back_to_browser, self.on_read_book, self.on_navigate_to_url, self.on_start_download, self.on_open_detail, self.local_db)
        self.reader_view = ReaderView(self.config_manager, self.on_exit_reader)
        
        # Global Download Manager
        self.download_manager = DownloadManager(None, self.config_manager.get_library_dir())
        self.download_manager.set_callback(self._on_downloads_updated)
        self._last_completed_count = 0
        self.downloads_popover = None

        # Stack Indices:
        # 0: Feed List (Root of Feeds)
        # 1: Library
        # 2: Settings
        # 3: Feed Browser
        # 4: Local Detail
        # 5: Local Reader
        # 6: Online Detail
        # 7: Online Reader
        # 8: Search Root
        # 9: Search Browser
        self.content_stack.addWidget(self.feed_list_view)     # 0
        self.content_stack.addWidget(self.local_library_view)# 1
        self.content_stack.addWidget(self.settings_view)     # 2
        self.content_stack.addWidget(self.feed_browser_view) # 3
        self.content_stack.addWidget(self.local_detail_view) # 4
        self.content_stack.addWidget(self.local_reader_view) # 5
        self.content_stack.addWidget(self.detail_view)       # 6
        self.content_stack.addWidget(self.reader_view)       # 7
        self.content_stack.addWidget(self.search_root_view)  # 8
        self.content_stack.addWidget(self.search_browser_view)# 9

        self.feed_list_view.icon_loaded.connect(self._on_feed_icon_loaded)
        self.settings_view.feed_management.icon_loaded.connect(self._on_feed_icon_loaded)

        # Apply initial theme
        self._apply_theme()

        # Restore last state
        QTimer.singleShot(0, self._restore_last_state)

    def _apply_theme(self):
        theme_name = self.config_manager.get_theme()
        ThemeManager.apply_theme(QApplication.instance(), theme_name)
        # Force all widgets to re-evaluate the new stylesheet
        app = QApplication.instance()
        for widget in app.allWidgets():
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()
        # Refresh icons that were set at construction time with the old theme color
        icon_map = ["feeds", "library", "settings"]
        for i, icon_name in enumerate(icon_map):
            item = self.nav_list.item(i)
            if item:
                item.setIcon(ThemeManager.get_icon(icon_name))
        self.btn_refresh.setIcon(ThemeManager.get_icon("refresh"))
        self.btn_downloads.setIcon(ThemeManager.get_icon("download"))
        self.btn_back_header.setIcon(ThemeManager.get_icon("back"))
        self.local_library_view.refresh_icons()
        self.settings_view.feed_management.refresh_feeds()

    def _restore_last_state(self):
        vtype = self.config_manager.get_last_view_type()
        if vtype == "library":
            self.nav_list.setCurrentRow(1)
            self._on_sidebar_changed(1)
        elif vtype == "feed":
            feed_id = self.config_manager.get_last_feed_id()
            feed = None
            if feed_id:
                feed = self.config_manager.get_feed(feed_id)
            
            if feed:
                self.on_feed_selected(feed)
            else:
                self.nav_list.setCurrentRow(0)
                self._on_sidebar_changed(0)
        else:
            self.nav_list.setCurrentRow(0)
            self._on_sidebar_changed(0)

    def _on_downloads_updated(self):
        # Update badge
        active_count = sum(1 for t in self.download_manager.tasks.values() if t.status in ("Downloading", "Pending"))
        if active_count > 0:
            self.download_badge.setText(str(active_count))
            self.download_badge.show()
        else:
            self.download_badge.hide()

        # Check for new completions to refresh library
        completed_tasks = [t for t in self.download_manager.tasks.values() if t.status == "Completed"]
        completed_count = len(completed_tasks)
        if completed_count > self._last_completed_count:
            logger.info(f"Download completion detected: {completed_count} total. Refreshing library.")
            # Record source_urls for all completed tasks in the DB
            for t in completed_tasks:
                if t.file_path:
                    try:
                        self.local_db.set_source_url(str(t.file_path.absolute()), t.url)
                    except Exception as e:
                        logger.error(f"Error linking source_url: {e}")
            
            self.local_library_view.set_dirty()
        self._last_completed_count = completed_count

    def _on_feed_icon_loaded(self, feed_id, pixmap):
        if self.api_client and self.api_client.profile.id == feed_id:
            setattr(self.api_client.profile, "_cached_icon", pixmap)
            self.update_header()

    def _on_header_back_clicked(self):
        current_view_idx = self.content_stack.currentIndex()
        if current_view_idx == 4: # Local Detail
            self.on_back_to_local_library()
            return
        if current_view_idx == 1: # Library (Folder Up)
            self.local_library_view.go_up()
            return

        hist, idx = self.get_current_history()
        if idx > 0:
            self.on_jump_to_history(idx - 1)
        else:
            self.back_to_feed_list()

    def get_current_history(self):
        if self.active_tab == "search":
            return self.search_history, self.search_index
        return self.feed_history, self.feed_index

    def set_current_history(self, history, index):
        if self.active_tab == "search":
            self.search_history = history
            self.search_index = index
        else:
            self.feed_history = history
            self.feed_index = index

    def _on_sidebar_changed(self, index):
        # Sidebar mapping:
        # 0: Feeds
        # 1: Library
        # 2: Settings
        
        if index == 0:
            self.config_manager.set_last_view_type("feed")
            hist, idx = self.get_current_history()
            if idx < 0:
                 self.content_stack.setCurrentIndex(0) # Feed List
            else:
                 self._on_tab_clicked(self.active_tab)
            self.update_header()
            return
            
        if index == 1:
            self.config_manager.set_last_view_type("library")
            
        # Re-map index for stacked widget (Skip index 3 which is now feed browser)
        target = index
        if index > 0:
            # index 1 (Library) -> 1
            # index 2 (Settings) -> 2
            pass
            
        self.content_stack.setCurrentIndex(target)
        self.update_header()

    def _on_tab_clicked(self, tab_name):
        self.active_tab = tab_name
        self.btn_tab_feed.setChecked(tab_name == "feed")
        self.btn_tab_search.setChecked(tab_name == "search")
        
        # Colorize icons to match the text (accent if active, text_dim if inactive)
        self.btn_tab_feed.setIcon(ThemeManager.get_icon("home", "accent" if tab_name == "feed" else "text_dim"))
        self.btn_tab_search.setIcon(ThemeManager.get_icon("search", "accent" if tab_name == "search" else "text_dim"))

        hist, idx = self.get_current_history()
        
        if tab_name == "search" and (not hist or hist[idx]["type"] == "search_root"):
            self.content_stack.setCurrentIndex(8) # Search Root
            if self.api_client:
                f = self.api_client.profile
                self.search_root_view.update_data(f.search_history, f.pinned_searches)
            self.search_root_view.search_input.setFocus()
        elif idx >= 0:
            entry = hist[idx]
            if entry["type"] == "browser":
                if tab_name == "feed":
                    self.content_stack.setCurrentIndex(3)
                    self.feed_browser_view.setFocus()
                else:
                    self.content_stack.setCurrentIndex(9)
                    self.search_browser_view.setFocus()
            elif entry["type"] == "detail":
                self.detail_view.load_publication(entry["pub"], entry["url"], self.api_client, self.opds_client, self.image_manager)
                self.content_stack.setCurrentIndex(6)
        else:
            self.content_stack.setCurrentIndex(0)
                
        self.update_header()

    def _on_browser_offset_changed(self, offset):
        hist, idx = self.get_current_history()
        if idx >= 0 and hist[idx]["type"] == "browser":
            hist[idx]["offset"] = offset

    def update_header(self):
        is_debug_on = os.getenv("DEBUG") == "1"
        current_view_idx = self.content_stack.currentIndex()
        is_reader = current_view_idx in (5, 7) # LocalReader, OnlineReader
        
        self.debug_bar.setVisible(is_debug_on and not is_reader)
        
        hist, idx = self.get_current_history()
        if is_debug_on:
            self.history_counter.setText(f"[{idx + 1}/{len(hist)}]")
            if idx >= 0:
                active_entry = hist[idx]
                url_val = active_entry.get("url", "")
                self.debug_url_text.setText(url_val)
                self.debug_url_text.setCursorPosition(0)
            else:
                self.debug_url_text.setText("")

        # Clear breadcrumbs
        while self.breadcrumb_items_layout.count():
            layout_item = self.breadcrumb_items_layout.takeAt(0)
            if layout_item.widget():
                layout_item.widget().deleteLater()
        
        # Show header everywhere except the reader
        show_header = not is_reader
        self.top_header.setVisible(show_header)
        
        if not show_header:
            return

        # Determine if we are in a "Feed Context" (Browsing or searching a feed)
        in_feed_context = current_view_idx in (3, 6, 8, 9)

        # Determine if we are in a "Back-enabled Context" 
        # (Feed browser, Search browser, Detail views, or Library subfolder)
        in_back_context = (current_view_idx in (3, 4, 6, 8, 9)) or \
                         (current_view_idx == 1 and not self.local_library_view.is_at_root)
        
        # Toggle visibility of header parts
        self.btn_back_header.setVisible(show_header and in_back_context)
        self.btn_back_header.setEnabled(in_back_context)
        self.btn_tab_feed.setVisible(in_feed_context)
        self.btn_tab_search.setVisible(in_feed_context)
        self.breadcrumb_container.setVisible(in_feed_context)

        if not in_feed_context:
            return
        
        style = QApplication.instance().style()

        # Build breadcrumbs (only in feed context)
        # 1. Feed Icon & Name (Merged with history start)
        if self.api_client:
            feed = self.api_client.profile
            feed_breadcrumb = QWidget()
            fb_layout = QHBoxLayout(feed_breadcrumb)
            fb_layout.setContentsMargins(0, 0, 0, 0)
            fb_layout.setSpacing(5)
            
            icon_label = QLabel()
            icon_pixmap = getattr(feed, "_cached_icon", None)
            if icon_pixmap:
                icon_label.setPixmap(icon_pixmap.scaled(18, 18, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else:
                icon_label.setPixmap(ThemeManager.get_icon("feeds").pixmap(18, 18))
            fb_layout.addWidget(icon_label)
            
            if idx == 0:
                # Inert label if on the feed start
                label_feed = QLabel(feed.name)
                label_feed.setObjectName("breadcrumb_active")
                fb_layout.addWidget(label_feed)
            else:
                # Clickable button if deeper in history
                btn_feed = QPushButton(feed.name)
                btn_feed.setFlat(True)
                btn_feed.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_feed.setObjectName("breadcrumb_dim")
                btn_feed.clicked.connect(lambda: self.on_jump_to_history(0))
                btn_feed.setToolTip(f"Back to {feed.name} Start")
                fb_layout.addWidget(btn_feed)
            
            self.breadcrumb_items_layout.addWidget(feed_breadcrumb)
            
            # Note: NO separator here yet, as the history index 0 (Home/Search icon) follows immediately
            # making it look like part of the feed identity.

        # 2. History steps
        for i, entry in enumerate(hist):
            title = entry.get("title", "...")
            item_widget = QWidget()
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(5)
            
            if i == 0:
                icon_name = "home" if self.active_tab == "feed" else "search"
                icon = ThemeManager.get_icon(icon_name)
                if i == idx:
                    icon_label = QLabel()
                    icon_label.setPixmap(icon.pixmap(18, 18))
                    item_layout.addWidget(icon_label)
                else:
                    btn = QPushButton()
                    btn.setIcon(icon)
                    btn.setIconSize(QSize(18, 18))
                    btn.setFlat(True)
                    btn.setFixedSize(24, 24)
                    btn.setCursor(Qt.CursorShape.PointingHandCursor)
                    btn.clicked.connect(lambda _, x=i: self.on_jump_to_history(x))
                    btn.setToolTip(f"Jump back to {title}")
                    item_layout.addWidget(btn)
            else:
                if i == idx:
                    label = QLabel(title)
                    label.setObjectName("breadcrumb_active")
                    item_layout.addWidget(label)
                else:
                    btn = QPushButton(title)
                    btn.setFlat(True)
                    btn.setCursor(Qt.CursorShape.PointingHandCursor)
                    btn.setObjectName("breadcrumb_dim")
                    btn.clicked.connect(lambda _, x=i: self.on_jump_to_history(x))
                    item_layout.addWidget(btn)
            
            self.breadcrumb_items_layout.addWidget(item_widget)
            if i < len(hist) - 1:
                sep = QLabel(">")
                sep.setObjectName("breadcrumb_sep")
                self.breadcrumb_items_layout.addWidget(sep)

        self.breadcrumb_inner.updateGeometry()
        self.top_header.updateGeometry()

    def back_to_feed_list(self):
        self.api_client = None
        self.opds_client = None
        self.image_manager = None
        # Keep download_manager alive if downloads are running
        self.feed_history = []
        self.feed_index = -1
        self.search_history = []
        self.search_index = -1
        self.content_stack.setCurrentIndex(0)
        self.update_header()

    def on_feed_selected(self, feed):
        self.config_manager.set_last_view_type("feed")
        self.config_manager.set_last_feed_id(feed.id)
        
        self.api_client = APIClient(feed)
        self.opds_client = OPDS2Client(self.api_client)
        self.image_manager = ImageManager(self.api_client)
        
        # Update Download Manager's client
        self.download_manager.api_client = self.api_client
            
        self.feed_browser_view.set_feed_context(feed)
        self.search_browser_view.set_feed_context(feed)
        self.reader_view.api_client = self.api_client
        
        base_url = feed.url
        start_url = base_url if "opds" in base_url.lower() else urljoin(base_url, "/codex/opds/v2.0/")
        
        self.feed_history = [{"type": "browser", "title": "Home", "url": start_url, "offset": 0, "feed_id": feed.id}]
        self.feed_index = 0
        self.search_history = [{"type": "search_root", "title": "Search", "feed_id": feed.id}]
        self.search_index = 0
        self.active_tab = "feed"
        
        self.search_root_view.update_data(feed.search_history, feed.pinned_searches)
        
        asyncio.create_task(self.feed_browser_view.load_feed(start_url, "Home"))
        self.content_stack.setCurrentIndex(3)
        self.update_header()

    def _toggle_downloads_popover(self):
        if not self.download_manager:
            return
            
        if not self.downloads_popover:
            self.downloads_popover = DownloadPopover(self, self.download_manager)
            
        if self.downloads_popover.isVisible():
            self.downloads_popover.hide()
        else:
            # Map button global pos
            btn_pos = self.btn_downloads.mapToGlobal(QPoint(0, self.btn_downloads.height()))
            self.downloads_popover.show_at(btn_pos)

    async def _execute_search(self, query: str):
        if not self.api_client: return
        f = self.api_client.profile
        
        if query in f.search_history:
            f.search_history.remove(query)
        f.search_history.insert(0, query)
        f.search_history = f.search_history[:50]
        self.config_manager.update_feed(f)

        if not self.feed_history: return
        start_url = self.feed_history[0]["url"]
        
        try:
            feed = await self.opds_client.get_feed(start_url)
            search_link = None
            for link in (feed.links or []):
                rel = link.rel
                rels = [rel] if isinstance(rel, str) else (rel or [])
                if "search" in rels:
                    search_link = link.href
                    break
            
            if not search_link:
                QMessageBox.warning(self, "Search", "Search is not supported by this feed.")
                return
                
            safe_query = urllib.parse.quote(query)
            if "{?query}" in search_link:
                search_url = search_link.replace("{?query}", f"?query={safe_query}")
            elif "{searchTerms}" in search_link:
                search_url = search_link.replace("{searchTerms}", safe_query)
            else:
                search_url = f"{search_link}?query={safe_query}"
                
            full_search_url = urljoin(start_url, search_url)
            self.on_navigate_to_url(full_search_url, title=f"Search: '{query}'")
            
        except Exception as e:
            QMessageBox.warning(self, "Search Error", f"Could not perform search: {e}")

    def _on_pin_search(self, query):
        if not self.api_client: return
        f = self.api_client.profile
        if query in f.pinned_searches:
            f.pinned_searches.remove(query)
        else:
            f.pinned_searches.append(query)
        self.config_manager.update_feed(f)
        self.search_root_view.update_data(f.search_history, f.pinned_searches)

    def _on_remove_search(self, query, from_pinned):
        if not self.api_client: return
        f = self.api_client.profile
        if from_pinned:
            if query in f.pinned_searches:
                f.pinned_searches.remove(query)
        else:
            if query in f.search_history:
                f.search_history.remove(query)
        self.config_manager.update_feed(f)
        self.search_root_view.update_data(f.search_history, f.pinned_searches)

    def _on_clear_search(self):
        if not self.api_client: return
        f = self.api_client.profile
        f.search_history.clear()
        self.config_manager.update_feed(f)
        self.search_root_view.update_data(f.search_history, f.pinned_searches)

    def on_navigate_to_url(self, url, title="Loading...", replace=False, keep_title=False, icon=None, feed_id=None):
        hist, idx = self.get_current_history()
        if replace and idx >= 0:
            hist[idx]["url"] = url
            if not keep_title:
                hist[idx]["title"] = title
        else:
            if idx < len(hist) - 1:
                hist = hist[:idx + 1]
            hist.append({
                "type": "browser", 
                "title": title, 
                "url": url, 
                "offset": 0
            })
            idx = len(hist) - 1
            
        self.set_current_history(hist, idx)
        self.content_stack.setCurrentIndex(9 if self.active_tab == "search" else 3)
        self.update_header()
        
        browser = self.search_browser_view if self.active_tab == "search" else self.feed_browser_view
        asyncio.create_task(browser.load_feed(url, title))
        browser.setFocus()

    def on_open_detail(self, pub, self_url):
        hist, idx = self.get_current_history()
        if idx < len(hist) - 1:
            hist = hist[:idx + 1]
        hist.append({
            "type": "detail", 
            "title": pub.metadata.title, 
            "url": self_url, 
            "pub": pub
        })
        idx = len(hist) - 1
        self.set_current_history(hist, idx)
        self.content_stack.setCurrentIndex(6)
        self.update_header()
        self.detail_view.load_publication(pub, self_url, self.api_client, self.opds_client, self.image_manager)

    def on_jump_to_history(self, index):
        hist, _ = self.get_current_history()
        hist = hist[:index + 1]
        self.set_current_history(hist, index)
        entry = hist[index]
        if entry["type"] == "browser":
            self.content_stack.setCurrentIndex(9 if self.active_tab == "search" else 3)
        elif entry["type"] == "search_root":
            self.content_stack.setCurrentIndex(8)
        else:
            self.content_stack.setCurrentIndex(6)
            
        self.update_header()
        
        if entry["type"] == "browser":
            browser = self.search_browser_view if self.active_tab == "search" else self.feed_browser_view
            asyncio.create_task(browser.load_feed(entry["url"], entry["title"], initial_offset=entry.get("offset", 0)))
            browser.setFocus()
        elif entry["type"] == "search_root":
            if self.api_client:
                f = self.api_client.profile
                self.search_root_view.update_data(f.search_history, f.pinned_searches)
            self.search_root_view.search_input.setFocus()
        else:
            self.detail_view.load_publication(entry["pub"], entry["url"], self.api_client, self.opds_client, self.image_manager)

    def on_manual_refresh(self):
        hist, idx = self.get_current_history()
        if idx < 0: return
        entry = hist[idx]
        if entry["type"] == "browser":
            browser = self.search_browser_view if self.active_tab == "search" else self.feed_browser_view
            asyncio.create_task(browser.load_feed(entry["url"], entry["title"], force_refresh=True, initial_offset=entry.get("offset", 0)))
        elif entry["type"] == "search_root":
            if self.api_client:
                f = self.api_client.profile
                self.search_root_view.update_data(f.search_history, f.pinned_searches)
        else:
            self.detail_view.load_publication(entry["pub"], entry["url"], self.api_client, self.opds_client, self.image_manager, force_refresh=True)

    def _copy_url_to_clipboard(self):
        url = self.debug_url_text.text()
        if url: QApplication.clipboard().setText(url)

    def _show_logs_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("System Logs")
        dialog.resize(800, 600)
        layout = QVBoxLayout(dialog)
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet("font-family: monospace; font-size: 10px; background-color: #1e1e1e; color: #ddd;")
        if os.path.exists("comiccatcher.log"):
            with open("comiccatcher.log", "r") as f:
                text_edit.setPlainText("".join(f.readlines()[-200:]))
        layout.addWidget(text_edit)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(dialog.accept)
        layout.addWidget(btn_close)
        dialog.exec()

    def on_read_book(self, pub, manifest_url):
        self.reader_view.load_manifest(pub, manifest_url)
        self.content_stack.setCurrentIndex(7)
        self.sidebar.hide()
        self.top_header.hide()

    def on_start_download(self, pub, url):
        if self.download_manager:
            asyncio.create_task(self.download_manager.start_download(pub.identifier, pub.metadata.title, url))
            # Show popover if not already visible
            if not self.downloads_popover or not self.downloads_popover.isVisible():
                self._toggle_downloads_popover()

    def on_open_local_comic(self, path):
        self.local_detail_view.load_path(path)
        self.content_stack.setCurrentIndex(4)
        self.update_header()

    def on_back_to_local_library(self):
        self.content_stack.setCurrentIndex(1)
        self.update_header()

    def on_back_to_browser(self):
        hist, idx = self.get_current_history()
        for i in range(idx - 1, -1, -1):
            if hist[i]["type"] == "browser" or hist[i]["type"] == "search_root":
                self.on_jump_to_history(i)
                return
        self.nav_list.setCurrentRow(0)
        self.content_stack.setCurrentIndex(0)

    def on_read_local_comic(self, path):
        self.local_reader_view.load_cbz(path)
        self.content_stack.setCurrentIndex(5)
        self.sidebar.hide()
        self.top_header.hide()

    def on_exit_reader(self):
        self.sidebar.show()
        self.top_header.show()
        if self.content_stack.currentIndex() == 5:
            self.content_stack.setCurrentIndex(4)
        else:
            self.content_stack.setCurrentIndex(6)
            self.on_manual_refresh()
        self.update_header()
