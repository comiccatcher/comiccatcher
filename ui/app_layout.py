import asyncio
import os
import enum
import traceback
import urllib.parse
from pathlib import Path
from urllib.parse import urljoin

from typing import List, Dict, Optional, Set, Any, Union
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, 
    QListWidget, QListWidgetItem, QStackedWidget, QLabel, QPushButton, QFrame,
    QDialog, QTextEdit, QMessageBox, QStyle, QApplication, QLineEdit, QScrollArea,
    QLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize, QTimer, QRect, QPoint
from PyQt6.QtGui import QIcon, QPixmap

from config import ConfigManager, CONFIG_DIR
from ui.flow_layout import FlowLayout
from ui.theme_manager import ThemeManager, UIConstants
from ui.views.feed_list import FeedListView
from ui.views.local_library import LocalLibraryView
from ui.views.local_detail import LocalDetailView
from ui.views.local_reader import LocalReaderView
from ui.views.feed_detail import FeedDetailView
from ui.views.feed_reader import FeedReaderView
from ui.views.settings import SettingsView
from ui.views.downloads import DownloadsView
from ui.views.search_root import SearchRootView
from ui.views.feed_browser import FeedBrowser
from ui.theme_manager import ThemeManager
from api.download_manager import DownloadManager
from api.client import APIClient
from api.local_db import LocalLibraryDB
from api.opds_v2 import OPDS2Client
from api.image_manager import ImageManager

from logger import get_logger
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
        self.setWindowTitle("ComicCatcher")
        self.resize(1200, 800)

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
        self.sidebar.setFixedWidth(UIConstants.scale(85))
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
        self.nav_list.setIconSize(QSize(UIConstants.scale(32), UIConstants.scale(32)))
        
        def add_nav_item(text, icon_name):
            item = QListWidgetItem(text)
            item.setIcon(ThemeManager.get_icon(icon_name))
            item.setSizeHint(QSize(UIConstants.scale(85), UIConstants.scale(85)))
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
        self.debug_bar.setFixedHeight(s(25))
        self.debug_layout = QHBoxLayout(self.debug_bar)
        self.debug_layout.setContentsMargins(s(10), 0, s(10), 0)
        self.debug_layout.setSpacing(s(10))
        
        self.history_counter = QLabel("[0/0]")
        self.history_counter.setStyleSheet(f"font-size: {s(10)}px; font-weight: bold;")
        
        self.debug_url_text = QLineEdit("")
        self.debug_url_text.setReadOnly(True)
        self.debug_url_text.setStyleSheet(f"font-size: {s(10)}px; background: transparent; border: none;")
        
        self.btn_logs = QPushButton("Logs")
        self.btn_logs.setFixedSize(s(40), s(18))
        self.btn_logs.setStyleSheet(f"font-size: {s(9)}px;")
        self.btn_logs.clicked.connect(self._show_logs_dialog)
        
        self.btn_copy = QPushButton("Copy")
        self.btn_copy.setFixedSize(s(40), s(18))
        self.btn_copy.setStyleSheet(f"font-size: {s(9)}px;")
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
        self.feed_info_row = QHBoxLayout()
        self.btn_back_header = QPushButton()
        self.btn_back_header.setIcon(ThemeManager.get_icon("back"))
        s = UIConstants.scale
        self.btn_back_header.setIconSize(QSize(s(20), s(20)))
        self.btn_back_header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back_header.setToolTip("Go back")
        self.btn_back_header.clicked.connect(self._on_header_back_clicked)
        self.btn_back_header.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 4px;
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
        
        s = UIConstants.scale
        self.feed_info_row.addWidget(self.btn_back_header)
        self.feed_info_row.addSpacing(s(10))
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
        self.btn_downloads.setFixedSize(UIConstants.HEADER_BUTTON_SIZE, UIConstants.HEADER_BUTTON_SIZE)
        self.btn_downloads.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_downloads.clicked.connect(self._toggle_downloads_popover)
        
        self.download_badge = QLabel("0", self.btn_downloads)
        self.download_badge.setFixedSize(s(16), s(16))
        self.download_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.download_badge.setObjectName("download_badge")
        self.download_badge.move(s(16), 0)
        self.download_badge.hide()
        
        self.feed_info_row.addWidget(self.btn_downloads)
        
        self.header_layout.addLayout(self.feed_info_row)

        # Row 2: Breadcrumb Row
        self.breadcrumb_container = QFrame()
        self.breadcrumb_row = QHBoxLayout(self.breadcrumb_container)
        self.breadcrumb_row.setContentsMargins(0, 0, 0, 0)
        self.breadcrumb_row.setSpacing(UIConstants.LAYOUT_MARGIN_DEFAULT)
        
        self.breadcrumb_inner = QWidget()
        self.breadcrumb_items_layout = FlowLayout(self.breadcrumb_inner, spacing=UIConstants.SECTION_HEADER_SPACING + UIConstants.scale(3))
        
        self.btn_refresh = QPushButton()
        self.btn_refresh.setProperty("flat", "true")
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
        
        # 1. Sidebar
        icon_map = ["feeds", "library", "settings"]
        for i, icon_name in enumerate(icon_map):
            item = self.nav_list.item(i)
            if item:
                item.setIcon(ThemeManager.get_icon(icon_name))
        
        # 2. Header Buttons & Icons
        self.btn_refresh.setIcon(ThemeManager.get_icon("refresh"))
        self.btn_downloads.setIcon(ThemeManager.get_icon("download"))
        self.btn_back_header.setIcon(ThemeManager.get_icon("back"))
        
        # Back button specifically needs to handle its hover/disabled states via stylesheet
        # but we can refresh its icon here.
        
        # 3. Debug Bar
        self.history_counter.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {theme['text_main']};")
        self.debug_url_text.setStyleSheet(f"font-size: 10px; background: transparent; border: none; color: {theme['text_dim']};")
        
        small_btn_style = f"font-size: 9px; background-color: {theme['bg_item_hover']}; color: {theme['text_main']}; border: 1px solid {theme['border']}; border-radius: 2px;"
        self.btn_logs.setStyleSheet(small_btn_style)
        self.btn_copy.setStyleSheet(small_btn_style)
        
        # 4. Tab Buttons
        self._on_tab_clicked(self.active_tab, navigate=False) # Refreshes tab icons
        
        # 5. Notify all active views
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
        from models.feed_page import ItemType

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
        from ui.theme_manager import UIConstants
        new_factor = UIConstants._scale_factor + delta
        UIConstants.set_scale(new_factor)
        self._apply_theme()
        logger.info(f"UI Scale changed to {UIConstants._scale_factor:.2f}")

    def _reset_scale(self):
        from ui.theme_manager import UIConstants
        # 1.0 triggers re-fetch of system DPI in init_scale
        UIConstants._scale_factor = 1.0
        UIConstants.init_scale()
        self._apply_theme()
        logger.info("UI Scale reset to system default")

    def _toggle_debug_outlines(self):
        from ui.theme_manager import UIConstants
        UIConstants.DEBUG_OUTLINES = not UIConstants.DEBUG_OUTLINES

        if UIConstants.DEBUG_OUTLINES:
            from ui.debug_overlay import DebugOverlay
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
            self.content_stack.setCurrentIndex(ViewIndex.LIBRARY)
        elif index == 2:
            self.config_manager.set_last_view_type("settings")
            self.content_stack.setCurrentIndex(ViewIndex.SETTINGS)
            
        self.update_header()

    def _on_tab_clicked(self, tab_name, navigate=True):
        self.active_tab = tab_name
        self.btn_tab_feed.setChecked(tab_name == "feed")
        self.btn_tab_search.setChecked(tab_name == "search")

        # Colorize icons to match the text (accent if active, text_dim if inactive)
        self.btn_tab_feed.setIcon(ThemeManager.get_icon("home", "accent" if tab_name == "feed" else "text_dim"))
        self.btn_tab_search.setIcon(ThemeManager.get_icon("search", "accent" if tab_name == "search" else "text_dim"))

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
            s = UIConstants.scale
            fb_layout.setSpacing(s(5))
            
            icon_label = QLabel()
            icon_pixmap = getattr(feed, "_cached_icon", None)
            if icon_pixmap:
                icon_label.setPixmap(icon_pixmap.scaled(s(18), s(18), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else:
                icon_label.setPixmap(ThemeManager.get_icon("feeds").pixmap(s(18), s(18)))
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
            
            # Add a separator after the feed name
            sep = QLabel(">")
            sep.setObjectName("breadcrumb_sep")
            self.breadcrumb_items_layout.addWidget(sep)

        # 2. History steps
        for i, entry in enumerate(hist):
            title = entry.get("title", "...")
            item_widget = QWidget()
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(0, 0, 0, 0)
            s = UIConstants.scale
            item_layout.setSpacing(s(5))
            
            if i == 0:
                icon_name = "home" if self.active_tab == "feed" else "search"
                icon = ThemeManager.get_icon(icon_name)
                if i == idx:
                    icon_label = QLabel()
                    icon_label.setPixmap(icon.pixmap(s(18), s(18)))
                    item_layout.addWidget(icon_label)
                else:
                    btn = QPushButton()
                    btn.setIcon(icon)
                    btn.setIconSize(QSize(s(18), s(18)))
                    btn.setFlat(True)
                    btn.setFixedSize(s(24), s(24))
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
        
        self.api_client = APIClient(feed)
        self.opds_client.api = self.api_client
        self.image_manager.api_client = self.api_client
        
        # Update Download Manager's client
        self.download_manager.api_client = self.api_client
            
        self.feed_browser.current_profile = feed
        self.feed_reader_view.api_client = self.api_client
        
        base_url = feed.url
        start_url = base_url if "opds" in base_url.lower() else urljoin(base_url, "/codex/opds/v2.0/")
        
        # Check if we have history for this feed; if not, initialize
        if feed.id not in self.feed_histories:
            self.feed_histories[feed.id] = [{"type": "browser", "title": "Home", "url": start_url, "offset": 0, "feed_id": feed.id}]
            self.feed_indices[feed.id] = 0
            self.search_histories[feed.id] = [{"type": "search_root", "title": "Search", "feed_id": feed.id}]
            self.search_indices[feed.id] = 0
            
            # Initial load for a new feed session
            asyncio.create_task(self.feed_browser.load_url(start_url))
            self.content_stack.setCurrentIndex(ViewIndex.FEED_BROWSER)
            self.feed_browser.setFocus()
        else:
            # Resume existing history
            hist = self.feed_histories[feed.id]
            idx = self.feed_indices[feed.id]
            self.on_jump_to_history(idx)
            
            entry = hist[idx]
            if entry["type"] == "detail":
                self.content_stack.setCurrentIndex(ViewIndex.DETAIL)
            else:
                self.content_stack.setCurrentIndex(ViewIndex.FEED_BROWSER)
                self.feed_browser.setFocus()
        
        self.active_tab = "feed"
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
        
        # Always use Feed Browser for any URL navigation (Browsing or Search Results)
        self.content_stack.setCurrentIndex(ViewIndex.FEED_BROWSER)
        asyncio.create_task(self.feed_browser.load_url(url))
        self.feed_browser.setFocus()
        
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

    def on_jump_to_history(self, index):
        hist, _ = self.get_current_history()
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
            asyncio.create_task(self.feed_browser.load_url(entry["url"]))
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
        hist, idx = self.get_current_history()
        if idx >= 0:
            entry = hist[idx]
            if entry["type"] == "browser":
                asyncio.create_task(self.feed_browser.load_url(entry["url"], force_refresh=True))

        elif entry["type"] == "search_root":
            if self.api_client:
                f = self.api_client.profile
                self.search_root_view.update_data(f.search_history, f.pinned_searches)
        else:
            self.feed_detail_view.load_publication(entry["pub"], entry["url"], self.api_client, self.opds_client, self.image_manager, force_refresh=True)

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
        self.local_detail_view.load_path(path, context_paths=context_paths)
        self.content_stack.setCurrentIndex(ViewIndex.LOCAL_DETAIL)
        self.update_header()

    def on_back_to_local_library(self):
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
        self.local_reader_view.load_cbz(path, context_paths=context_paths)
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
                cover_url = f"local-cbz://{target_path.absolute()}/_cover_thumb"
                cache_path = self.image_manager._get_cache_path(cover_url)
                if cache_path.exists():
                    pixmap.load(str(cache_path))
                
                return target_path.stem, pixmap, target_path

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
            self.content_stack.setCurrentIndex(ViewIndex.LOCAL_DETAIL)
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
