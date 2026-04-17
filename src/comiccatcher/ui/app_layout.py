# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

import asyncio
import os
import enum
import traceback
import urllib.parse
from pathlib import Path
from urllib.parse import urljoin

from typing import List, Dict, Optional, Set, Any, Union, Tuple
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
    QListWidget, QListWidgetItem, QStackedWidget, QLabel, QPushButton, QFrame,
    QDialog, QTextEdit, QMessageBox, QStyle, QApplication, QLineEdit, QScrollArea,
    QLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize, QTimer, QRect, QPoint
from PyQt6.QtGui import QIcon, QPixmap

from comiccatcher.config import ConfigManager, CONFIG_DIR
from comiccatcher.ui.flow_layout import FlowLayout
from comiccatcher.ui.theme_manager import ThemeManager, UIConstants
from comiccatcher.ui.views.feed_list import FeedListView
from comiccatcher.ui.views.local_library import LocalLibraryView
from comiccatcher.ui.views.local_detail import LocalDetailView
from comiccatcher.ui.views.local_reader import LocalReaderView
from comiccatcher.ui.views.feed_detail import FeedDetailView
from comiccatcher.ui.views.feed_reader import FeedReaderView
from comiccatcher.ui.views.settings import SettingsView
from comiccatcher.ui.views.downloads import DownloadsView
from comiccatcher.ui.views.search_root import SearchRootView
from comiccatcher.ui.views.feed_browser import FeedBrowser
from comiccatcher.ui.theme_manager import ThemeManager
from comiccatcher.api.download_manager import DownloadManager
from comiccatcher.api.client import APIClient
from comiccatcher.api.local_db import LocalLibraryDB
from comiccatcher.api.opds_v2 import OPDS2Client
from comiccatcher.api.image_manager import ImageManager

from comiccatcher.logger import get_logger
logger = get_logger("ui.app_layout")

class ViewIndex(enum.IntEnum):
    FEED_LIST = 0
    LIBRARY = 1
    SETTINGS = 2
    LOCAL_DETAIL = 3
    LOCAL_READER = 4
    DETAIL = 5
    READER_ONLINE = 6
    SEARCH_ROOT = 7
    FEED_BROWSER = 8

class DownloadPopover(QFrame):
    def __init__(self, parent, download_manager: DownloadManager):
        super().__init__(parent)
        self.dm = download_manager
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        s = UIConstants.scale
        self.setFixedWidth(s(350))
        self.setFixedHeight(s(400))
        self.setObjectName("download_popover")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.downloads_view = DownloadsView(self.dm)
        layout.addWidget(self.downloads_view)

    def show_at(self, pos: QPoint):
        # Position it so the top right of the popover is near the click pos
        # but with some padding
        s = UIConstants.scale
        adjusted_pos = QPoint(pos.x() - self.width() + s(20), pos.y() + s(10))
        self.move(adjusted_pos)
        self.show()

class MainWindow(QMainWindow):
    def __init__(self, config_manager: ConfigManager):
        super().__init__()
        self.config_manager = config_manager
        
        # Restore manual scaling before UI construction
        UIConstants.init_scale(manual_factor=self.config_manager.get_ui_scale())
        s = UIConstants.scale
        
        self.setWindowTitle("ComicCatcher")
        self.resize(s(1200), s(800))

        # App Icon
        icon_path = Path(__file__).parent.parent / "resources" / "app.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        
        self.api_client = None
        self.opds_client = OPDS2Client(None) # persistent cache
        self.image_manager = ImageManager(None) # persistent cache
        self.download_manager = None
        self.local_db = LocalLibraryDB(CONFIG_DIR / "library.db")
        
        # Tabbed History State (Per-Feed)
        self.active_tab = "feed" # "feed" or "search"
        self.last_active_tabs = {}  # {feed_id: "feed" | "search"}
        self.current_feed_id = None
        self.feed_histories = {}    # {feed_id: [history_list]}
        self.feed_indices = {}      # {feed_id: index}
        self.search_histories = {}  # {feed_id: [history_list]}
        self.search_indices = {}    # {feed_id: index}

        # Main horizontal layout (Sidebar | Content)
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QHBoxLayout(self.central_widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Sidebar (Narrower, Icons + Text Underneath)
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(UIConstants.SIDEBAR_WIDTH)
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_layout.setSpacing(0)

        self.nav_list = QListWidget()
        self.nav_list.setObjectName("nav_list") # For specific styling
        self.nav_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.nav_list.setFlow(QListWidget.Flow.TopToBottom)
        self.nav_list.setMovement(QListWidget.Movement.Static)
        self.nav_list.setSpacing(0)
        self.nav_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav_list.setIconSize(QSize(UIConstants.NAV_ICON_SIZE, UIConstants.NAV_ICON_SIZE))
        
        def add_nav_item(text, icon_name):
            item = QListWidgetItem(text)
            item.setIcon(ThemeManager.get_icon(icon_name))
            item.setSizeHint(QSize(UIConstants.SIDEBAR_WIDTH, UIConstants.SIDEBAR_WIDTH))
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
        s = UIConstants.scale
        self.debug_bar.setFixedHeight(s(30))
        self.debug_layout = QHBoxLayout(self.debug_bar)
        self.debug_layout.setContentsMargins(s(10), 0, s(10), 0)
        self.debug_layout.setSpacing(s(10))
        
        self.history_counter = QLabel("[0/0]")
        self.history_counter.setStyleSheet(f"font-size: {s(10)}px; font-weight: bold;")
        
        self.debug_url_text = QLineEdit("")
        self.debug_url_text.setReadOnly(True)
        self.debug_url_text.setStyleSheet(f"font-size: {s(10)}px; background: transparent; border: none;")
        
        theme = ThemeManager.get_current_theme_colors()
        debug_btn_qss = f"""
            QPushButton {{
                background-color: {theme['bg_item_hover']};
                color: {theme['text_main']};
                border: {max(1, s(1))}px solid {theme['border']};
                border-radius: {s(4)}px;
                padding: 0px;
                font-size: {s(9)}px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {theme['bg_item_selected']};
            }}
        """

        self.btn_logs = QPushButton("Logs")
        self.btn_logs.setFixedSize(s(60), s(24))
        self.btn_logs.setStyleSheet(debug_btn_qss)
        self.btn_logs.clicked.connect(self._show_logs_dialog)

        self.btn_copy = QPushButton("Copy")
        self.btn_copy.setFixedSize(s(60), s(24))
        self.btn_copy.setStyleSheet(debug_btn_qss)
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
        self.header_layout.setContentsMargins(UIConstants.LAYOUT_MARGIN_DEFAULT, UIConstants.SECTION_HEADER_MARGIN_TOP, UIConstants.LAYOUT_MARGIN_DEFAULT, UIConstants.SECTION_HEADER_MARGIN_TOP)
        self.header_layout.setSpacing(UIConstants.TOOLBAR_GAP)

        # Row 1: Feed Info & Tabs & Downloads
        self.feed_info_row = QGridLayout()
        self.feed_info_row.setContentsMargins(0, 0, 0, 0)
        
        # Left side: Back + Tabs
        self.left_box = QWidget()
        self.left_layout = QHBoxLayout(self.left_box)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.setSpacing(s(10))
        
        self.btn_back_header = QPushButton()
        self.btn_back_header.setObjectName("icon_button")
        self.btn_back_header.setIcon(ThemeManager.get_icon("back"))
        s = UIConstants.scale
        self.btn_back_header.setIconSize(QSize(s(20), s(20)))
        self.btn_back_header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back_header.setToolTip("Go back")
        self.btn_back_header.clicked.connect(self._on_header_back_clicked)
        
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
        
        self.left_layout.addWidget(self.btn_back_header)
        self.left_layout.addWidget(self.btn_tab_feed)
        self.left_layout.addWidget(self.btn_tab_search)
        self.left_layout.addStretch()

        # Center: Server Identity (Pill)
        self.server_identity_container = QFrame()
        self.server_identity_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.server_identity_layout = QHBoxLayout(self.server_identity_container)
        self.server_identity_layout.setContentsMargins(s(16), s(6), s(20), s(6))
        self.server_identity_layout.setSpacing(s(10))
        self.server_identity_container.setObjectName("server_identity_pill")
        
        self.server_icon_label = QLabel()
        self.server_name_label = QLabel()
        self.server_name_label.setObjectName("server_name_label")
        
        self.server_identity_layout.addWidget(self.server_icon_label)
        self.server_identity_layout.addWidget(self.server_name_label)
        self.server_identity_container.setCursor(Qt.CursorShape.PointingHandCursor)
        self.server_identity_container.setToolTip("Back to Server Home")
        self.server_identity_container.mousePressEvent = self._on_server_pill_clicked
        
        # Right side: Downloads
        self.right_box = QWidget()
        self.right_layout = QHBoxLayout(self.right_box)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_layout.setSpacing(0)
        
        # Global Download Button with Badge
        self.download_container = QWidget()
        self.download_layout = QVBoxLayout(self.download_container)
        self.download_layout.setContentsMargins(0, 0, 0, 0)
        
        self.btn_downloads = QPushButton()
        self.btn_downloads.setObjectName("icon_button")
        self.btn_downloads.setIcon(ThemeManager.get_icon("download"))
        self.btn_downloads.setFixedSize(UIConstants.HEADER_BUTTON_SIZE, UIConstants.HEADER_BUTTON_SIZE)
        self.btn_downloads.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_downloads.clicked.connect(self._toggle_downloads_popover)
        
        self.download_badge = QLabel("0", self.btn_downloads)
        self.download_badge.setFixedSize(s(16), s(16))
        self.download_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.download_badge.setObjectName("download_badge")
        self.download_badge.move(s(16), 0)
        self.download_badge.hide()
        
        self.right_layout.addStretch()
        self.right_layout.addWidget(self.btn_downloads)
        
        # Assemble Grid
        self.feed_info_row.addWidget(self.left_box, 0, 0)
        self.feed_info_row.addWidget(self.server_identity_container, 0, 1, Qt.AlignmentFlag.AlignCenter)
        self.feed_info_row.addWidget(self.right_box, 0, 2)
        
        self.feed_info_row.setColumnStretch(0, 1)
        self.feed_info_row.setColumnStretch(1, 0)
        self.feed_info_row.setColumnStretch(2, 1)
        
        self.header_layout.addLayout(self.feed_info_row)

        # Row 2: Breadcrumb Row
        self.breadcrumb_container = QFrame()
        self.breadcrumb_row = QHBoxLayout(self.breadcrumb_container)
        self.breadcrumb_row.setContentsMargins(0, 0, 0, 0)
        self.breadcrumb_row.setSpacing(UIConstants.LAYOUT_MARGIN_DEFAULT)
        
        self.breadcrumb_inner = QWidget()
        self.breadcrumb_items_layout = FlowLayout(self.breadcrumb_inner, spacing=UIConstants.SECTION_HEADER_SPACING + UIConstants.scale(3))
        
        self.btn_refresh = QPushButton()
        self.btn_refresh.setObjectName("icon_button")
        self.btn_refresh.setIcon(ThemeManager.get_icon("refresh"))
        self.btn_refresh.setFixedSize(UIConstants.HEADER_BUTTON_SIZE, UIConstants.HEADER_BUTTON_SIZE)
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
        self.feed_list_view = FeedListView(self.config_manager, self.image_manager, self.on_feed_selected)
        
        self.settings_view = SettingsView(self.config_manager, self.image_manager, self.opds_client, self.local_db)
        self.settings_view.theme_changed.connect(self._apply_theme)
        
        self.search_root_view = SearchRootView(
            on_search=lambda q: asyncio.create_task(self._execute_search(q)),
            on_pin=self._on_pin_search,
            on_remove=self._on_remove_search,
            on_clear=self._on_clear_search
        )
        
        self.local_library_view = LocalLibraryView(self.config_manager, self.on_open_local_comic, self.image_manager, self.local_db)
        self.local_library_view.nav_changed.connect(self.update_header)
        self.settings_view.library_reset.connect(self.local_library_view.set_dirty)
        
        self.local_detail_view = LocalDetailView(self.config_manager, self.on_back_to_local_library, self.image_manager, self.on_read_local_comic, self.local_db)
        
        self.local_reader_view = LocalReaderView(
            self.on_exit_reader, 
            self.image_manager, 
            self.config_manager,
            on_get_adjacent=self._on_reader_boundary_reached,
            on_transition=self.on_reader_transition_local,
            local_db=self.local_db
        )
        
        self.feed_detail_view = FeedDetailView(self.config_manager, self.on_back_to_browser, self.on_read_book, self.on_navigate_to_url, self.on_start_download, self.on_open_detail, self.image_manager, self.local_db)
        
        self.feed_reader_view = FeedReaderView(
            self.config_manager, 
            self.on_exit_reader, 
            self.image_manager,
            on_get_adjacent=self._on_reader_boundary_reached,
            on_transition=self.on_reader_transition_online
        )
        
        self.download_manager = DownloadManager(None, self.config_manager.get_library_dir())
        self.download_manager.set_callback(self._on_downloads_updated)
        self._last_completed_count = 0
        self.downloads_popover = None

        self.content_stack.addWidget(self.feed_list_view)
        self.content_stack.addWidget(self.local_library_view)
        self.content_stack.addWidget(self.settings_view)
        self.content_stack.addWidget(self.local_detail_view)
        self.content_stack.addWidget(self.local_reader_view)
        self.content_stack.addWidget(self.feed_detail_view)
        self.content_stack.addWidget(self.feed_reader_view)
        self.content_stack.addWidget(self.search_root_view)
        
        self.feed_browser = FeedBrowser(self.opds_client, self.image_manager, self.config_manager, self.download_manager)
        self.feed_browser.item_clicked.connect(self._on_feed_item_clicked)
        self.feed_browser.navigate_requested.connect(self.on_navigate_to_url)
        self.feed_browser.download_requested.connect(self.on_start_download)
        self.feed_browser.page_loaded.connect(self.update_header)
        self.content_stack.addWidget(self.feed_browser) # Index 8 (Match ViewIndex)

        self.feed_list_view.icon_loaded.connect(self._on_feed_icon_loaded)
        self.settings_view.feed_management.icon_loaded.connect(self._on_feed_icon_loaded)

        # Apply initial theme
        self._apply_theme()

        # Restore last state
        QTimer.singleShot(0, self._restore_last_state)

    def _apply_theme(self):
        theme_name = self.config_manager.get_theme()
        ThemeManager.apply_theme(QApplication.instance(), theme_name)
        
        # We manually call reapply_theme on the root, which updates global shell UI
        self.reapply_theme()
        
        # Note: We NO LONGER manually iterate all stack widgets and call reapply_theme.
        # BaseBrowserView-derived views (Library, Feed Browser, Settings) use a 
        # QTimer.singleShot(0, self.reapply_theme) in their __init__, which handles
        # initial theme application correctly without double-triggering or loops.

    def reapply_theme(self):
        """Standardized theme application for the main shell."""
        theme = ThemeManager.get_current_theme_colors()
        s = UIConstants.scale
        
        # 1. Sidebar
        self.sidebar.setFixedWidth(UIConstants.SIDEBAR_WIDTH)
        self.nav_list.setIconSize(QSize(UIConstants.NAV_ICON_SIZE, UIConstants.NAV_ICON_SIZE))
        
        # Explicitly set the font for the list widget to ensure the text scales in IconMode
        font = self.nav_list.font()
        font.setPixelSize(UIConstants.FONT_SIZE_SIDEBAR)
        self.nav_list.setFont(font)
        
        icon_map = ["feeds", "library", "settings"]
        for i, icon_name in enumerate(icon_map):
            item = self.nav_list.item(i)
            if item:
                item.setIcon(ThemeManager.get_icon(icon_name))
                item.setSizeHint(QSize(UIConstants.SIDEBAR_WIDTH, UIConstants.SIDEBAR_WIDTH))
        
        # 2. Header Buttons & Icons
        self.btn_refresh.setIcon(ThemeManager.get_icon("refresh"))
        self.btn_downloads.setIcon(ThemeManager.get_icon("download"))
        self.btn_back_header.setIcon(ThemeManager.get_icon("back"))
        self.btn_refresh.setFixedSize(UIConstants.HEADER_BUTTON_SIZE, UIConstants.HEADER_BUTTON_SIZE)
        self.btn_refresh.setIconSize(QSize(s(20), s(20)))
        self.btn_downloads.setFixedSize(UIConstants.HEADER_BUTTON_SIZE, UIConstants.HEADER_BUTTON_SIZE)
        self.btn_downloads.setIconSize(QSize(s(20), s(20)))
        self.btn_back_header.setIconSize(QSize(s(20), s(20)))
        
        # Back button specifically needs to handle its hover/disabled states via stylesheet
        # but we can refresh its icon here.
        
        # 3. Debug Bar
        self.history_counter.setStyleSheet(f"font-size: {UIConstants.FONT_SIZE_DEBUG}px; font-weight: bold; color: {theme['text_main']};")
        self.debug_url_text.setStyleSheet(f"font-size: {UIConstants.FONT_SIZE_DEBUG}px; background: transparent; border: none; color: {theme['text_dim']};")

        small_btn_style = f"font-size: {UIConstants.FONT_SIZE_DEBUG}px; background-color: {theme['bg_item_hover']}; color: {theme['text_main']}; border: {max(1, s(1))}px solid {theme['border']}; border-radius: {s(2)}px;"
        self.btn_logs.setStyleSheet(small_btn_style)
        self.btn_logs.setFixedSize(s(55), s(22))
        self.btn_copy.setStyleSheet(small_btn_style)
        self.btn_copy.setFixedSize(s(55), s(22))        
        # 4. Tab Buttons
        self._on_tab_clicked(self.active_tab, navigate=False) # Refreshes tab icons
        
        # 5. Server Identity
        # Use a large, clear font for the server name
        font_size = s(16)
        font = self.server_name_label.font()
        font.setPixelSize(font_size)
        font.setBold(True)
        
        # Calculate height based on actual font metrics instead of magic numbers
        from PyQt6.QtGui import QFontMetrics
        metrics = QFontMetrics(font)
        # Use lineSpacing + double the standard layout margin for a balanced look
        pill_height = metrics.lineSpacing() + (UIConstants.LAYOUT_MARGIN_DEFAULT * 2)
        
        self.server_identity_container.setFixedHeight(pill_height)
        self.server_identity_layout.setContentsMargins(s(16), 0, s(20), 0) # Vertical margins handled by pill_height/alignment
        
        self.server_identity_container.setStyleSheet(f"""
            QFrame#server_identity_pill {{
                background-color: {theme['bg_item_hover']};
                border: {max(1, s(1))}px solid {theme['border']};
                border-radius: {pill_height // 2}px;
            }}
        """)
        self.server_name_label.setStyleSheet(f"font-weight: bold; font-size: {font_size}px; color: {theme['text_main']}; background: transparent; border: none;")
        
        # 6. Notify all active views
        for i in range(self.content_stack.count()):
            widget = self.content_stack.widget(i)
            if hasattr(widget, 'reapply_theme'):
                widget.reapply_theme()

    def _restore_last_state(self):
        vtype = self.config_manager.get_last_view_type()
        if vtype == "library":
            self.nav_list.setCurrentRow(1)
            # setCurrentRow triggers _on_sidebar_changed, but we call it explicitly to be sure
            self._on_sidebar_changed(1)
        elif vtype == "settings":
            self.nav_list.setCurrentRow(2)
            self._on_sidebar_changed(2)
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

    def _on_feed_item_clicked(self, item, context_pubs=None):
        # Helper to bridge from FeedItem to existing navigation/detail logic
        from comiccatcher.models.feed_page import ItemType

        if item.type == ItemType.FOLDER:
            # Navigate to subsection
            if item.raw_link:
                url = urllib.parse.urljoin(self.feed_browser._last_loaded_url, item.raw_link.href)
                self.on_navigate_to_url(url, item.title)
        elif item.raw_pub:
            # We need the self_url
            self_url = None
            for l in (item.raw_pub.links or []):
                if l.rel == "self" or (isinstance(l.rel, list) and "self" in l.rel):
                    self_url = urllib.parse.urljoin(self.feed_browser._last_loaded_url, l.href)
                    break
            self.on_open_detail(item.raw_pub, self_url, context_pubs=context_pubs)
    def _on_feed_icon_loaded(self, feed_id, pixmap):
        if self.api_client and self.api_client.profile.id == feed_id:
            setattr(self.api_client.profile, "_cached_icon", pixmap)
            self.update_header()

    def keyPressEvent(self, event):
        modifiers = event.modifiers()
        key = event.key()
        
        # 1. Scaling Shortcuts (Ctrl + Plus/Minus/Zero)
        if modifiers == Qt.KeyboardModifier.ControlModifier:
            if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                self._change_scale(0.1)
                return
            elif key == Qt.Key.Key_Minus:
                self._change_scale(-0.1)
                return
            elif key == Qt.Key.Key_0:
                self._reset_scale()
                return

        # 2. Debug Outlines (Ctrl + Shift + D)
        if (key == Qt.Key.Key_D
                and modifiers == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)):
            self._toggle_debug_outlines()
            return
            
        # 3. Back Navigation (Escape)
        if key == Qt.Key.Key_Escape:
            # Only trigger back button for non-reader views
            # (Readers handle their own Escape logic)
            idx = self.content_stack.currentIndex()
            if idx not in (ViewIndex.LOCAL_READER, ViewIndex.READER_ONLINE):
                self._on_header_back_clicked()
                return
        super().keyPressEvent(event)

    def _change_scale(self, delta: float):
        from comiccatcher.ui.theme_manager import UIConstants
        new_factor = UIConstants._scale_factor + delta
        UIConstants.set_scale(new_factor)
        self.config_manager.set_ui_scale(UIConstants._scale_factor)
        self._apply_theme()
        logger.info(f"UI Scale changed to {UIConstants._scale_factor:.2f}")

    def _reset_scale(self):
        from comiccatcher.ui.theme_manager import UIConstants
        # 1.0 triggers re-fetch of system DPI in init_scale
        UIConstants._scale_factor = 1.0
        UIConstants.init_scale()
        self.config_manager.set_ui_scale(UIConstants._scale_factor)
        self._apply_theme()
        logger.info("UI Scale reset to system default")

    def _toggle_debug_outlines(self):
        from comiccatcher.ui.theme_manager import UIConstants
        UIConstants.DEBUG_OUTLINES = not UIConstants.DEBUG_OUTLINES

        if UIConstants.DEBUG_OUTLINES:
            from comiccatcher.ui.debug_overlay import DebugOverlay
            self._debug_overlay = DebugOverlay(self)
            self._debug_overlay.show()
            logger.info("Debug outlines ON")
        else:
            overlay = getattr(self, '_debug_overlay', None)
            if overlay:
                overlay._timer.stop()
                overlay.hide()
                overlay.deleteLater()
                self._debug_overlay = None
            logger.info("Debug outlines OFF")

        # Force repaint of all visible viewports so delegate outlines appear/disappear
        for w in self.findChildren(QWidget):
            if hasattr(w, 'viewport'):
                w.viewport().update()

    def _on_header_back_clicked(self):
        current_view_idx = self.content_stack.currentIndex()
        if current_view_idx == ViewIndex.LOCAL_DETAIL:
            self.on_back_to_local_library()
            return
        if current_view_idx == ViewIndex.LIBRARY:
            self.local_library_view.go_up()
            return
        if current_view_idx in (ViewIndex.LOCAL_READER, ViewIndex.READER_ONLINE):
            self.on_exit_reader()
            return

        hist, idx = self.get_current_history()
        if idx > 0:
            self.on_jump_to_history(idx - 1)
        else:
            self.back_to_feed_list()

    def _on_server_pill_clicked(self, event=None):
        """Returns to server root using either 'start' link or history index 0."""
        fid = self.current_feed_id
        if not fid: return

        # 1. If we are on search tab, reset it and switch back to feed browser
        if self.active_tab == "search":
            # Clear search history stack for this feed
            self.search_histories[fid] = []
            self.search_indices[fid] = -1
            # Force switch to feed tab (without trigger navigation because we'll do it below)
            self._on_tab_clicked("feed", navigate=False)

        # 2. Attempt to find 'start' link in current feed metadata (if any)
        start_url = None
        if hasattr(self.feed_browser, '_last_raw_feed') and self.feed_browser._last_raw_feed:
            feed = self.feed_browser._last_raw_feed
            for link in (feed.links or []):
                rel = link.rel
                if (isinstance(rel, str) and rel == "start") or (isinstance(rel, list) and "start" in rel):
                    # Found it. Make it absolute relative to the last loaded URL
                    start_url = urllib.parse.urljoin(self.feed_browser._last_loaded_url, link.href)
                    break
        
        # 3. Get the feed-browser history (always use feed stack for Home comparison)
        hist = self.feed_histories.get(fid, [])
        home_url = hist[0]["url"] if hist and "url" in hist[0] else None
        
        def normalize(u):
            if not u: return None
            return u.rstrip('/')
            
        # 4. Decision: 
        # If start_url found AND it's different from our current home_url, navigate to it.
        # Otherwise, just jump back to history index 0.
        if start_url and normalize(start_url) != normalize(home_url):
            logger.info(f"Pill click: Navigating to server 'start' link: {start_url}")
            self.on_navigate_to_url(start_url, title="Home", force_refresh=True)
        else:
            logger.info("Pill click: Jumping to history index 0 (Home) with reload.")
            self.on_jump_to_history(0, force_refresh=True)

    def get_current_history(self):
        fid = self.current_feed_id
        if not fid:
            return [], -1
            
        if self.active_tab == "search":
            return self.search_histories.get(fid, []), self.search_indices.get(fid, -1)
        return self.feed_histories.get(fid, []), self.feed_indices.get(fid, -1)

    def set_current_history(self, history, index):
        fid = self.current_feed_id
        if not fid:
            return
            
        if self.active_tab == "search":
            self.search_histories[fid] = history
            self.search_indices[fid] = index
        else:
            self.feed_histories[fid] = history
            self.feed_indices[fid] = index

    def _on_sidebar_changed(self, index):
        # Sidebar mapping:
        # 0: Feeds
        # 1: Library
        # 2: Settings
        
        if index == 0:
            self.config_manager.set_last_view_type("feed")
            hist, idx = self.get_current_history()
            if idx < 0:
                 self.content_stack.setCurrentIndex(ViewIndex.FEED_LIST)
            else:
                 self._on_tab_clicked(self.active_tab)
            self.update_header()
            return
            
        if index == 1:
            self.config_manager.set_last_view_type("library")
            target_idx = getattr(self, "last_library_view", ViewIndex.LIBRARY)
            self.content_stack.setCurrentIndex(target_idx)
        elif index == 2:
            self.config_manager.set_last_view_type("settings")
            self.content_stack.setCurrentIndex(ViewIndex.SETTINGS)
            
        self.update_header()

    def _on_tab_clicked(self, tab_name, navigate=True):
        self.active_tab = tab_name
        if self.current_feed_id:
            self.last_active_tabs[self.current_feed_id] = tab_name
            
        self.btn_tab_feed.setChecked(tab_name == "feed")
        self.btn_tab_search.setChecked(tab_name == "search")

        # Colorize icons to match the text (accent if active, text_dim if inactive)
        s = UIConstants.scale
        self.btn_tab_feed.setIcon(ThemeManager.get_icon("home", "accent" if tab_name == "feed" else "text_dim"))
        self.btn_tab_feed.setIconSize(QSize(s(18), s(18)))
        self.btn_tab_search.setIcon(ThemeManager.get_icon("search", "accent" if tab_name == "search" else "text_dim"))
        self.btn_tab_search.setIconSize(QSize(s(18), s(18)))

        if not navigate:
            return

        hist, idx = self.get_current_history()
        if tab_name == "search" and (not hist or hist[idx]["type"] == "search_root"):
            self.content_stack.setCurrentIndex(ViewIndex.SEARCH_ROOT)
            if self.api_client:
                f = self.api_client.profile
                self.search_root_view.update_data(f.search_history, f.pinned_searches)
            self.search_root_view.search_input.setFocus()
        elif idx >= 0:
            entry = hist[idx]
            if entry["type"] == "browser":
                self.content_stack.setCurrentIndex(ViewIndex.FEED_BROWSER)
                asyncio.create_task(self.feed_browser.load_url(entry["url"]))
                self.feed_browser.setFocus()
            elif entry["type"] == "detail":
                self.feed_detail_view.load_publication(entry["pub"], entry["url"], self.api_client, self.opds_client, self.image_manager)
                self.content_stack.setCurrentIndex(ViewIndex.DETAIL)
        else:
            self.content_stack.setCurrentIndex(ViewIndex.FEED_LIST)
                
        self.update_header()

    def update_header(self):
        is_debug_on = os.getenv("DEBUG") == "1"
        current_view_idx = self.content_stack.currentIndex()
        is_reader = current_view_idx in (ViewIndex.LOCAL_READER, ViewIndex.READER_ONLINE)
        
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
        in_feed_context = current_view_idx in (
            ViewIndex.FEED_BROWSER, 
            ViewIndex.DETAIL, 
            ViewIndex.SEARCH_ROOT
        )

        # Determine if we are in a "Back-enabled Context" 
        # (Feed browser, Search browser, Detail views, or Library subfolder)
        in_back_context = (current_view_idx in (
            ViewIndex.FEED_BROWSER, 
            ViewIndex.LOCAL_DETAIL, 
            ViewIndex.DETAIL, 
            ViewIndex.SEARCH_ROOT
        )) or (current_view_idx == ViewIndex.LIBRARY and not self.local_library_view.is_at_root)
        
        # Toggle visibility of header parts
        self.btn_back_header.setVisible(show_header and in_back_context)
        self.btn_back_header.setEnabled(in_back_context)
        self.btn_tab_feed.setVisible(in_feed_context)
        self.btn_tab_search.setVisible(in_feed_context)
        self.server_identity_container.setVisible(in_feed_context)
        self.breadcrumb_container.setVisible(in_feed_context)

        if not in_feed_context:
            return
        
        # Build server identity pill
        if self.api_client:
            feed = self.api_client.profile
            s = UIConstants.scale
            
            display_name = feed.name
            
            # Try to get the active feed title from the browser
            browser_title = ""
            if self.feed_browser._last_page:
                browser_title = self.feed_browser._last_page.title
                if self.feed_browser._last_page.subtitle:
                    browser_title = f"{browser_title} | {self.feed_browser._last_page.subtitle}"
            
            if browser_title and browser_title != feed.name:
                # Use Rich Text to make the appended info lighter
                full_text = f"{feed.name} <span style='font-weight: normal; opacity: 0.7;'> : {browser_title}</span>"
                self.server_name_label.setText(full_text)
            else:
                self.server_name_label.setText(feed.name)
                
            icon_pixmap = getattr(feed, "_cached_icon", None)
            icon_size = s(24)
            if icon_pixmap:
                self.server_icon_label.setPixmap(icon_pixmap.scaled(icon_size, icon_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else:
                self.server_icon_label.setPixmap(ThemeManager.get_icon("feeds").pixmap(icon_size, icon_size))
        
        style = QApplication.instance().style()

        # Build breadcrumbs (only in feed context)
        # 1. Base/Start Indicator (Home or Search)
        icon_name = "home" if self.active_tab == "feed" else "search"
        start_icon = ThemeManager.get_icon(icon_name)
        s = UIConstants.scale
        
        start_widget = QWidget()
        start_layout = QHBoxLayout(start_widget)
        start_layout.setContentsMargins(0, 0, 0, 0)
        start_layout.setSpacing(s(5))

        if idx == 0:
            icon_label = QLabel()
            icon_label.setPixmap(start_icon.pixmap(s(18), s(18)))
            start_layout.addWidget(icon_label)
            label = QLabel("Home" if self.active_tab == "feed" else "Search")
            label.setObjectName("breadcrumb_active")
            start_layout.addWidget(label)
        else:
            btn = QPushButton()
            btn.setIcon(start_icon)
            btn.setIconSize(QSize(s(18), s(18)))
            btn.setFlat(True)
            btn.setFixedSize(s(24), s(24))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, x=0: self.on_jump_to_history(0))
            btn.setToolTip(f"Jump back to Start")
            start_layout.addWidget(btn)
        
        self.breadcrumb_items_layout.addWidget(start_widget)
        if len(hist) > 1:
            sep = QLabel(">")
            sep.setObjectName("breadcrumb_sep")
            self.breadcrumb_items_layout.addWidget(sep)

        # 2. History steps (excluding index 0 which we just handled)
        for i, entry in enumerate(hist):
            if i == 0: continue
            
            title = entry.get("title", "...")
            icon_name = entry.get("icon")
            
            item_widget = QWidget()
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(s(5))
            
            # Prepend icon if available
            if icon_name:
                icon_label = QLabel()
                # Use text_dim for inactive, accent or default for active is handled by button/label style
                icon = ThemeManager.get_icon(icon_name)
                icon_label.setPixmap(icon.pixmap(s(16), s(16)))
                item_layout.addWidget(icon_label)
            
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
        # opds_client and image_manager are kept to maintain in-memory cache
        self.current_feed_id = None
        # Keep download_manager alive if downloads are running
        # feed_histories / search_histories are NOT cleared to maintain runtime session
        self.content_stack.setCurrentIndex(ViewIndex.FEED_LIST)
        self.update_header()

    def on_feed_selected(self, feed):
        self.config_manager.set_last_view_type("feed")
        self.config_manager.set_last_feed_id(feed.id)
        self.current_feed_id = feed.id
        self.active_tab = "feed"
        
        self.api_client = APIClient(feed)
        self.opds_client.api = self.api_client
        self.image_manager.api_client = self.api_client
        
        # Update Download Manager's client
        self.download_manager.api_client = self.api_client
            
        self.feed_browser.current_profile = feed
        self.feed_reader_view.api_client = self.api_client
        
        # Restore last active tab for this server in this session
        self.active_tab = self.last_active_tabs.get(feed.id, "feed")
        # Update tab UI (buttons/icons) without triggering navigation yet
        self._on_tab_clicked(self.active_tab, navigate=False)

        base_url = feed.url
        start_url = base_url if "opds" in base_url.lower() else urljoin(base_url, "/codex/opds/v2.0/")
        
        # Check if we have history for this feed; if not, initialize
        if feed.id not in self.feed_histories:
            self.feed_histories[feed.id] = [{"type": "browser", "title": "Home", "url": start_url, "offset": 0, "feed_id": feed.id}]
            self.feed_indices[feed.id] = 0
            self.search_histories[feed.id] = [{"type": "search_root", "title": "Search", "feed_id": feed.id}]
            self.search_indices[feed.id] = 0
            
            # For a brand new server session, we always start on 'feed' browse view
            self._on_tab_clicked("feed", navigate=False)
            asyncio.create_task(self.feed_browser.load_url(start_url))
            self.content_stack.setCurrentIndex(ViewIndex.FEED_BROWSER)
            self.feed_browser.setFocus()
        else:
            # Resume existing history from the restored tab
            hist, idx = self.get_current_history()
            self.on_jump_to_history(idx)
            
            entry = hist[idx]
            if entry["type"] == "detail":
                self.content_stack.setCurrentIndex(ViewIndex.DETAIL)
            elif entry["type"] == "search_root":
                self.content_stack.setCurrentIndex(ViewIndex.SEARCH_ROOT)
                self.search_root_view.search_input.setFocus()
            else:
                self.content_stack.setCurrentIndex(ViewIndex.FEED_BROWSER)
                self.feed_browser.setFocus()
        
        self.search_root_view.update_data(feed.search_history, feed.pinned_searches)
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

        fid = self.current_feed_id
        feed_hist = self.feed_histories.get(fid, [])
        if not feed_hist: return
        start_url = feed_hist[0]["url"]
        
        self.search_root_view.set_loading(True)
        try:
            # Use the feed browser's search_template property (which is sticky per-feed)
            search_link = self.feed_browser.search_template
            if not search_link:
                QMessageBox.warning(self, "Search", "Search is not supported by this feed.")
                return
                
            safe_query = urllib.parse.quote(query)
            
            if "{?query}" in search_link:
                search_url = search_link.replace("{?query}", f"?query={safe_query}")
            elif "{searchTerms}" in search_link:
                search_url = search_link.replace("{searchTerms}", safe_query)
            else:
                # Basic append if no template placeholders found
                separator = "&" if "?" in search_link else "?"
                search_url = f"{search_link}{separator}query={safe_query}"
                
            self.on_navigate_to_url(search_url, title=f"Search: '{query}'", icon="search")
            
        except Exception as e:
            QMessageBox.warning(self, "Search Error", f"Could not perform search: {e}")
        finally:
            self.search_root_view.set_loading(False)

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

    def on_navigate_to_url(self, url, title="Loading...", replace=False, icon=None, keep_title=False, feed_id=None, force_refresh=False):
        hist, idx = self.get_current_history()
        if replace and idx >= 0:
            hist[idx]["url"] = url
            # Update icon if provided
            if icon:
                hist[idx]["icon"] = icon
            
            if not keep_title:
                hist[idx]["title"] = title
        else:
            if idx < len(hist) - 1:
                hist = hist[:idx + 1]
            hist.append({
                "type": "browser",
                "title": title,
                "url": url,
                "offset": 0,
                "icon": icon
            })
            idx = len(hist) - 1
            
        self.set_current_history(hist, idx)
        
        # Always use Feed Browser for any URL navigation (Browsing or Search Results)
        self.content_stack.setCurrentIndex(ViewIndex.FEED_BROWSER)
        asyncio.create_task(self.feed_browser.load_url(url, is_paging=replace, force_refresh=force_refresh))
        self.feed_browser.setFocus()
        
        self.update_header()

    def update_current_history_title(self, new_title: str):
        """Updates the title of the current history entry and refreshes the breadcrumbs."""
        hist, idx = self.get_current_history()
        if idx >= 0:
            hist[idx]["title"] = new_title
            self.set_current_history(hist, idx)
            self.update_header()

    def on_open_detail(self, pub, self_url, context_pubs=None):
        hist, idx = self.get_current_history()
        if idx < len(hist) - 1:
            hist = hist[:idx + 1]
        hist.append({
            "type": "detail", 
            "title": pub.metadata.title, 
            "url": self_url, 
            "pub": pub,
            "context_pubs": context_pubs
        })
        idx = len(hist) - 1
        self.set_current_history(hist, idx)
        self.content_stack.setCurrentIndex(ViewIndex.DETAIL)
        self.update_header()
        self.feed_detail_view.load_publication(pub, self_url, self.api_client, self.opds_client, self.image_manager, context_pubs=context_pubs)

    def on_jump_to_history(self, index, force_refresh=False):
        if index < 0:
            return
            
        hist, _ = self.get_current_history()
        if not hist or index >= len(hist):
            logger.warning(f"on_jump_to_history: invalid index {index} for history of size {len(hist)}")
            return

        # Truncate forward history
        hist = hist[:index + 1]
        self.set_current_history(hist, index)
        
        entry = hist[index]
        if entry["type"] == "browser":
            self.content_stack.setCurrentIndex(ViewIndex.FEED_BROWSER)
        elif entry["type"] == "search_root":
            self.content_stack.setCurrentIndex(ViewIndex.SEARCH_ROOT)
        else:
            self.content_stack.setCurrentIndex(ViewIndex.DETAIL)
            
        self.update_header()
        
        if entry["type"] == "browser":
            asyncio.create_task(self.feed_browser.load_url(entry["url"], force_refresh=force_refresh))
            self.feed_browser.setFocus()
        elif entry["type"] == "search_root":
            if self.api_client:
                f = self.api_client.profile
                self.search_root_view.update_data(f.search_history, f.pinned_searches)
            self.search_root_view.search_input.setFocus()
        else:
            # Detail view
            self.feed_detail_view.load_publication(
                entry["pub"], 
                entry["url"], 
                self.api_client, 
                self.opds_client, 
                self.image_manager, 
                context_pubs=entry.get("context_pubs")
            )

    def on_manual_refresh(self):
        """Universal refresh handler that routes to the active view's specific reload logic."""
        current_view_idx = self.content_stack.currentIndex()
        
        # 1. Feeds / Search Results
        if current_view_idx == ViewIndex.FEED_BROWSER:
            hist, idx = self.get_current_history()
            if idx >= 0:
                entry = hist[idx]
                asyncio.create_task(self.feed_browser.load_url(entry["url"], force_refresh=True))
            return

        # 2. Feed Detail
        if current_view_idx == ViewIndex.DETAIL:
            hist, idx = self.get_current_history()
            if idx >= 0:
                entry = hist[idx]
                self.feed_detail_view.load_publication(
                    entry["pub"], 
                    entry["url"], 
                    self.api_client, 
                    self.opds_client, 
                    self.image_manager, 
                    force_refresh=True
                )
            return

        # 3. Search Root (History/Pinned)
        if current_view_idx == ViewIndex.SEARCH_ROOT:
            if self.api_client:
                f = self.api_client.profile
                self.search_root_view.update_data(f.search_history, f.pinned_searches)
            return

        # 4. Local Library (Scanner)
        if current_view_idx == ViewIndex.LIBRARY:
            self.local_library_view.refresh_and_scan()
            return
            
        # 5. Local Detail (Progress)
        if current_view_idx == ViewIndex.LOCAL_DETAIL:
            self.local_detail_view.refresh_progress()
            return
            
        # 6. Feed List
        if current_view_idx == ViewIndex.FEED_LIST:
            self.feed_list_view.refresh()
            return

    def _copy_url_to_clipboard(self):
        url = self.debug_url_text.text()
        if url: QApplication.clipboard().setText(url)

    def _show_logs_dialog(self):
        s = UIConstants.scale
        dialog = QDialog(self)
        dialog.setWindowTitle("System Logs")
        dialog.resize(s(800), s(600))
        layout = QVBoxLayout(dialog)
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(f"font-family: monospace; font-size: {s(10)}px; background-color: #1e1e1e; color: #ddd;")
        if os.path.exists("comiccatcher.log"):
            with open("comiccatcher.log", "r") as f:
                text_edit.setPlainText("".join(f.readlines()[-200:]))
        layout.addWidget(text_edit)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(dialog.accept)
        layout.addWidget(btn_close)
        dialog.exec()

    def on_read_book(self, pub, manifest_url, context_pubs=None):
        self.feed_reader_view.load_manifest(pub, manifest_url, self.image_manager, context_pubs=context_pubs)
        self.content_stack.setCurrentIndex(ViewIndex.READER_ONLINE)
        self.sidebar.hide()
        self.top_header.hide()

    def on_start_download(self, pub, url):
        if self.download_manager:
            asyncio.create_task(self.download_manager.start_download(pub.identifier, pub.metadata.title, url))
            # Show popover if not already visible
            if not self.downloads_popover or not self.downloads_popover.isVisible():
                self._toggle_downloads_popover()

    def on_open_local_comic(self, path, context_paths=None):
        self.last_library_view = ViewIndex.LOCAL_DETAIL
        self.local_detail_view.load_path(path, context_paths=context_paths)
        self.content_stack.setCurrentIndex(ViewIndex.LOCAL_DETAIL)
        self.update_header()

    def on_back_to_local_library(self):
        self.last_library_view = ViewIndex.LIBRARY
        self.content_stack.setCurrentIndex(ViewIndex.LIBRARY)
        self.update_header()

    def on_back_to_browser(self):
        hist, idx = self.get_current_history()
        for i in range(idx - 1, -1, -1):
            if hist[i]["type"] == "browser" or hist[i]["type"] == "search_root":
                self.on_jump_to_history(i)
                return
        self.nav_list.setCurrentRow(0)
        self.content_stack.setCurrentIndex(ViewIndex.FEED_LIST)

    def on_read_local_comic(self, path, context_paths=None):
        self.local_reader_view.load_archive(path, context_paths=context_paths)
        self.content_stack.setCurrentIndex(ViewIndex.LOCAL_READER)
        self.sidebar.hide()
        self.top_header.hide()

    async def _on_reader_boundary_reached(self, direction: int):
        """Called by BaseReaderView to get info about the next/prev book in context."""
        
        # 1. Online Context
        if self.content_stack.currentIndex() == ViewIndex.READER_ONLINE:
            hist, idx = self.get_current_history()
            if idx < 0: return None
            entry = hist[idx]
            
            if entry["type"] == "detail" and "pub" in entry:
                pubs = entry.get("context_pubs", [])
                if not pubs: return None
                
                # Find current pub index
                cur_pub = entry["pub"]
                p_idx = -1
                for i, p in enumerate(pubs):
                    # Robust comparison: ID then Title
                    if p.identifier and cur_pub.identifier and p.identifier == cur_pub.identifier:
                        p_idx = i
                        break
                    if p.metadata.title == cur_pub.metadata.title:
                        p_idx = i
                        break
                
                if p_idx == -1: return None
                
                target_idx = p_idx + direction
                if 0 <= target_idx < len(pubs):
                    target_pub = pubs[target_idx]
                    
                    # Get cover from cache
                    pixmap = QPixmap()
                    if target_pub.images:
                        img_url = target_pub.images[0].href
                        # Use last loaded url as base
                        full_img_url = urllib.parse.urljoin(entry["url"], img_url)
                        cache_path = self.image_manager._get_cache_path(full_img_url)
                        if cache_path.exists():
                            pixmap.load(str(cache_path))
                    
                    # Get self_url
                    self_url = next((urllib.parse.urljoin(entry["url"], l.href) for l in target_pub.links if l.rel == "self"), None)
                    if not self_url and target_pub.links:
                        self_url = urllib.parse.urljoin(entry["url"], target_pub.links[0].href)
                    
                    return target_pub.metadata.title, pixmap, (target_pub, self_url)

        # 2. Local Context
        # Check both the content stack and the entry to see if we are in local reader
        if self.content_stack.currentIndex() == ViewIndex.LOCAL_READER:
            paths = self.local_reader_view._context_paths
            if not paths: return None
            
            cur_path = self.local_reader_view._path
            if not cur_path: return None
            
            p_abs = cur_path.absolute()
            p_idx = -1
            for i, p in enumerate(paths):
                if p.absolute() == p_abs:
                    p_idx = i
                    break
            
            if p_idx == -1: return None
            
            target_idx = p_idx + direction
            if 0 <= target_idx < len(paths):
                target_path = paths[target_idx]
                
                # Get cover from cache
                pixmap = QPixmap()
                cover_url = f"local-archive://{target_path.absolute()}/_cover_thumb"
                cache_path = self.image_manager._get_cache_path(cover_url)
                if cache_path.exists():
                    pixmap.load(str(cache_path))
                
                # Use focus-aware label for the title
                display_title = target_path.stem
                if self.local_db:
                    row = self.local_db.get_comic(str(target_path.absolute()))
                    if row:
                        from comiccatcher.ui.local_comicbox import generate_comic_labels
                        row_dict = dict(row)
                        label_focus = self.config_manager.get_library_label_focus()
                        primary, _ = generate_comic_labels(row_dict, label_focus)
                        if row_dict.get("series") or row_dict.get("title"):
                            display_title = primary

                return display_title, pixmap, target_path

        return None

    def on_reader_transition_online(self, book_ref):
        pub, self_url = book_ref
        hist, idx = self.get_current_history()
        
        # Update current history step (the detail step)
        if idx >= 0:
            entry = hist[idx]
            entry["pub"] = pub
            entry["url"] = self_url
            entry["title"] = pub.metadata.title
            
        # Update detail view in background
        self.feed_detail_view.load_publication(pub, self_url, self.api_client, self.opds_client, self.image_manager, context_pubs=entry.get("context_pubs"))
        
        # Reload reader
        self.on_read_book(pub, self_url, context_pubs=entry.get("context_pubs"))

    def on_reader_transition_local(self, path):
        # Local reader transition: update local detail and local reader
        # Capture context first before clearing/reloading
        ctx = getattr(self.local_reader_view, "_context_paths", [])
        self.local_detail_view.load_path(path, context_paths=ctx)
        self.on_read_local_comic(path, context_paths=ctx)

    def on_exit_reader(self):
        self.sidebar.show()
        self.top_header.show()
        if self.content_stack.currentIndex() == ViewIndex.LOCAL_READER:
            self.last_library_view = ViewIndex.LOCAL_DETAIL
            self.content_stack.setCurrentIndex(ViewIndex.LOCAL_DETAIL)
            self.local_detail_view.refresh_progress()
            self.local_library_view.set_dirty() # Refresh library to show updated progress on cards
        else:
            self.content_stack.setCurrentIndex(ViewIndex.DETAIL)
            self.on_manual_refresh()
        self.update_header()

    def closeEvent(self, event):
        """Purge in-memory histories and caches on application quit."""
        logger.info("Application closing. Purging runtime histories and in-memory caches.")
        
        # Clear histories
        self.feed_histories.clear()
        self.feed_indices.clear()
        self.search_histories.clear()
        self.search_indices.clear()
        
        # Clear OPDS Client cache if available
        if self.opds_client:
            self.opds_client.clear_cache()
            
        # Clear Image Manager memory cache if available
        if self.image_manager:
            self.image_manager._memory_cache.clear()
            
        event.accept()
