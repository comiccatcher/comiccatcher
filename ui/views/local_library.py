import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QProgressBar, QComboBox, QStackedWidget,
    QScrollArea, QApplication, QStyledItemDelegate, QStyle,
    QAbstractItemView, QSizePolicy, QFrame, QSpacerItem, QListView
)
from PyQt6.QtCore import Qt, QSize, pyqtSlot, pyqtSignal, QRect, QModelIndex, QPoint, QTimer
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QBrush, QPen, QImage, QPixmapCache, QKeyEvent, QStandardItemModel, QStandardItem

from config import ConfigManager, CONFIG_DIR
from logger import get_logger
from api.image_manager import ImageManager
from ui.local_archive import read_first_image
from ui.local_comicbox import flatten_comicbox, read_comicbox_dict, subtitle_from_flat, read_comicbox_cover, generate_comic_labels
from ui.theme_manager import ThemeManager, UIConstants
from api.local_db import LocalLibraryDB
from api.library_scanner import LibraryScanner
from ui.views.base_browser import BaseBrowserView
from ui.components.library_card_delegate import LibraryCardDelegate
from ui.components.base_ribbon import BaseCardRibbon
from ui.components.mini_detail_popover import MiniDetailPopover

logger = get_logger("ui.local_library")

COMIC_EXTS = {".cbz", ".cbr", ".cb7", ".pdf"}
_COVER_URL_SUFFIX = "_cover_thumb"


def _save_thumbnail(data: bytes, cache_path: Path, thumb_w: int = 240, thumb_h: int = 360) -> bool:
    """Resize cover bytes and save as a small JPEG thumbnail. Thread-safe (uses QImage)."""
    from PyQt6.QtGui import QImage
    from PyQt6.QtCore import Qt as _Qt
    img = QImage()
    if not img.loadFromData(data):
        return False
    scaled = img.scaled(thumb_w, thumb_h, _Qt.AspectRatioMode.KeepAspectRatio, _Qt.TransformationMode.SmoothTransformation)
    return scaled.save(str(cache_path), "JPEG", 85)

@dataclass(frozen=True)
class LibraryEntry:
    path: Path
    is_dir: bool

    @property
    def name(self) -> str:
        return self.path.name

def _list_dir(path: Path, sort_dir: str = "asc") -> List[LibraryEntry]:
    if not path.exists() or not path.is_dir():
        return []
    entries: List[LibraryEntry] = []
    try:
        for p in path.iterdir():
            if p.name.startswith("."):
                continue
            if p.is_dir():
                entries.append(LibraryEntry(p, True))
            else:
                if p.suffix.lower() in COMIC_EXTS:
                    entries.append(LibraryEntry(p, False))
    except Exception:
        return []

    reverse = (sort_dir == "desc")
    # Always sort directories first, but respect sort_dir for the names within those blocks
    entries.sort(key=lambda e: (not e.is_dir if not reverse else e.is_dir, e.name.lower()), reverse=reverse)
    return entries

def format_ranges(nums: List[int]) -> str:
    if not nums: return ""
    nums = sorted(list(set(nums)))
    ranges = []
    
    start = nums[0]
    end = nums[0]
    
    def add_range(s, e):
        if s == e:
            ranges.append(str(s))
        elif e == s + 1:
            ranges.append(f"{s},{e}")
        else:
            ranges.append(f"{s}-{e}")

    for i in range(1, len(nums)):
        if nums[i] == end + 1:
            end = nums[i]
        else:
            add_range(start, end)
            start = nums[i]
            end = nums[i]
    add_range(start, end)
    return ",".join(ranges)

def set_item_data(item, role, value):
    """Helper to handle different setData signatures between QListWidgetItem and QStandardItem."""
    if isinstance(item, QListWidgetItem):
        item.setData(role, value)
    elif isinstance(item, QStandardItem):
        item.setData(value, role)

from ui.components.collapsible_section import CollapsibleSection

class LibrarySection(CollapsibleSection):
    def __init__(self, title: str, rows: List[Any], on_item_clicked: Callable, is_grid: bool = False, image_manager=None, meta_sem=None, show_labels=True, label_focus="series", is_folder_mode=False, config_manager=None, on_context_menu: Optional[Callable] = None):
        super().__init__(title=title, content_widget=None, is_collapsed=False, on_context_menu=on_context_menu)
        self.rows = rows
        self.on_item_clicked = on_item_clicked
        self.image_manager = image_manager
        self._meta_sem = meta_sem
        self.show_labels = show_labels
        self.is_grid = is_grid
        self.label_focus = label_focus
        self.is_folder_mode = is_folder_mode
        self.config_manager = config_manager
        
        # 1. List Content
        s = UIConstants.scale
        if is_grid:
            self.list_widget = QListWidget()
            self.list_widget.setFrameShape(QFrame.Shape.NoFrame)
            self.list_widget.setMouseTracking(True)
            self.delegate = LibraryCardDelegate(self.list_widget, show_labels=self.show_labels, image_manager=self.image_manager)
            self.list_widget.setItemDelegate(self.delegate)
            self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
            self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
            self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            self.list_widget.viewport().installEventFilter(self)
            self.list_widget.setMovement(QListWidget.Movement.Static)
            self.list_widget.setFlow(QListWidget.Flow.LeftToRight)
            self.list_widget.setWrapping(True)
            self.list_widget.setSpacing(UIConstants.GRID_SPACING)
            self.list_widget.setIconSize(QSize(s(120), s(180)))
            self.list_widget.itemClicked.connect(self.on_item_clicked)
        else:
            self.list_widget = BaseCardRibbon(show_labels=self.show_labels)
            self.model = QStandardItemModel()
            self.list_widget.setModel(self.model)
            self.delegate = LibraryCardDelegate(self.list_widget, show_labels=self.show_labels, image_manager=self.image_manager)
            self.list_widget.setItemDelegate(self.delegate)
            self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            self.list_widget.clicked.connect(self.on_item_clicked)

        self.set_content_widget(self.list_widget)
        self.setObjectName("series_section")
            
        # Ensure rows are sorted based on context
        sorted_rows = rows
        sort_dir = self.config_manager.get_library_sort_direction()
        reverse = (sort_dir == "desc")
        
        if self.is_folder_mode:
            sorted_rows = sorted(rows, key=lambda r: Path(r["file_path"]).name.lower(), reverse=reverse)
        # For non-folder modes, we trust the DB (which handles smart Series sorting) 
        # or the caller (_load_grouped manual sorting for one-offs)
        
        for row in sorted_rows:
            r = dict(row)
            primary, secondary = generate_comic_labels(r, self.label_focus)
            
            # In Folder mode, we always use filename for display
            display_text = Path(r["file_path"]).name if self.is_folder_mode else primary
            
            # Label data (primary, secondary) for the card delegate
            card_primary = display_text if self.is_folder_mode else primary
            
            if is_grid:
                item = QListWidgetItem(display_text)
                item.setData(Qt.ItemDataRole.UserRole, Path(r["file_path"]))
                item.setData(Qt.ItemDataRole.UserRole + 1, (r.get("current_page") or 0, r.get("page_count") or 0))
                item.setData(Qt.ItemDataRole.UserRole + 2, (card_primary, secondary))
                item.setIcon(ThemeManager.get_icon("book"))
                item.setToolTip(display_text)
                self.list_widget.addItem(item)
                try:
                    asyncio.create_task(self._load_thumb(Path(r["file_path"]), item))
                except RuntimeError:
                    pass
            else:
                item = QStandardItem(display_text)
                item.setData(Path(r["file_path"]), Qt.ItemDataRole.UserRole)
                item.setData((r.get("current_page") or 0, r.get("page_count") or 0), Qt.ItemDataRole.UserRole + 1)
                item.setData((card_primary, secondary), Qt.ItemDataRole.UserRole + 2)
                item.setIcon(ThemeManager.get_icon("book"))
                item.setToolTip(display_text)
                self.model.appendRow(item)
                try:
                    asyncio.create_task(self._load_thumb(Path(r["file_path"]), item))
                except RuntimeError:
                    pass

        self.toggled.connect(self._on_toggled)
        
        # Initial height calculation after layout settle
        if is_grid:
            QTimer.singleShot(100, self._update_grid_height)
        else:
            QTimer.singleShot(100, self.list_widget.update_ribbon_height)

    def _on_toggled(self, is_collapsed: bool):
        if not is_collapsed:
            if self.is_grid:
                self._update_grid_height()
            else:
                self.list_widget.update_ribbon_height()

    def set_expanded(self, expanded: bool):
        logger.debug(f"LibrarySection '{self.header_label.text()}' set_expanded: {expanded}")
        self.set_collapsed(not expanded)

    def reapply_theme(self):
        """Theme-aware update for section header and delegate."""
        self._update_ui_state() # Will update chevron color and ensure everything uses current theme
        self.delegate.show_labels = self.show_labels
        self.list_widget.viewport().update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'is_grid') and self.is_grid and not self.is_collapsed:
            self._update_grid_height()

    def eventFilter(self, source, event):
        """Dynamic cursor change when hovering over items."""
        if hasattr(self, 'list_widget') and source is self.list_widget.viewport() and event.type() == event.Type.MouseMove:
            index = self.list_widget.indexAt(event.pos())
            if index.isValid():
                self.list_widget.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.list_widget.setCursor(Qt.CursorShape.ArrowCursor)
        return super().eventFilter(source, event)

    def _update_grid_height(self):
        count = self.list_widget.count()
        if count == 0:
            return
            
        s = UIConstants.scale
        available_width = self.list_widget.viewport().width()
        item_w = UIConstants.CARD_WIDTH + UIConstants.GRID_SPACING
        
        cols = max(1, available_width // item_w)
        rows_count = (count + cols - 1) // cols
        
        item_h = UIConstants.CARD_HEIGHT if self.show_labels else (UIConstants.CARD_COVER_HEIGHT + UIConstants.GRID_SPACING)
        self.list_widget.setFixedHeight(rows_count * (item_h + UIConstants.GRID_SPACING) + UIConstants.GRID_SPACING)

    async def _load_thumb(self, path: Path, item: QListWidgetItem):
        if path.suffix.lower() in (".cbz", ".cbr", ".cb7"):
            url = f"local-cbz://{path.absolute()}/{_COVER_URL_SUFFIX}"
            cache_path = self.image_manager._get_cache_path(url)

            pixmap = QPixmapCache.find(str(cache_path))
            if pixmap:
                set_item_data(item, Qt.ItemDataRole.DecorationRole, pixmap)
                return

            if not cache_path.exists():
                async with self._meta_sem:
                    try:
                        data = await asyncio.to_thread(read_comicbox_cover, path)
                        if not data:
                            res = await asyncio.to_thread(read_first_image, path)
                            if res: _, data = res
                        if data:
                            await asyncio.to_thread(_save_thumbnail, data, cache_path)
                    except: pass

            if cache_path.exists():
                try:
                    # Decoding bytes to QImage is thread-safe and offloads the CPU work
                    img = await asyncio.to_thread(lambda: QImage(str(cache_path)))
                    if not img.isNull():
                        # QPixmap conversion must happen on UI thread, but it's very fast
                        pixmap = QPixmap.fromImage(img)
                        QPixmapCache.insert(str(cache_path), pixmap)
                        set_item_data(item, Qt.ItemDataRole.DecorationRole, pixmap)
                except Exception:
                    pass

class LocalLibraryView(BaseBrowserView):
    scan_progress_signal = pyqtSignal(int, int, str)
    scan_finished_signal = pyqtSignal(bool)
    nav_changed = pyqtSignal()

    def __init__(
        self,
        config_manager: ConfigManager,
        on_open_comic: Callable[[Path, Optional[List[Path]]], None],
        image_manager: ImageManager,
        local_db: Optional[LocalLibraryDB] = None,
    ):
        self.config_manager = config_manager
        super().__init__()
        self.on_open_comic = on_open_comic
        self.db = local_db or LocalLibraryDB(CONFIG_DIR / "library.db")

        self.root_dir = self.config_manager.get_library_dir()
        self.current_dir = self.root_dir
        self.image_manager = image_manager
        self._meta_sem = asyncio.Semaphore(4)
        self._is_dirty = True
        
        self._show_labels = self.config_manager.get_show_labels()
        initial_view_mode = self.config_manager.get_library_view_mode()
        
        # Reset to root each startup (per user request)
        self.current_dir = self.root_dir
        
        # Init Scanner
        self.scanner = LibraryScanner(self.db, self.root_dir, on_cover=self._save_cover_to_cache)
        self.scanner.on_progress = lambda c, t, m: self.scan_progress_signal.emit(c, t, m)
        self.scanner.on_finished = lambda changed: self.scan_finished_signal.emit(changed)
        
        self.scan_progress_signal.connect(self._on_scan_progress_ui)
        self.scan_finished_signal.connect(self._on_scan_finished_ui)

        # Header Configuration (using base class helper)
        self.btn_up = self.create_header_button("back", "Go up one folder")
        self.btn_up.clicked.connect(self._go_up)
        self.btn_up.setVisible(False)
        
        self.btn_refresh = self.create_header_button("refresh", "Scan for changes")
        self.btn_refresh.clicked.connect(self.refresh_and_scan)
        
        # View Modes
        from PyQt6.QtWidgets import QButtonGroup
        from PyQt6.QtGui import QActionGroup
        self.view_mode_group = QButtonGroup(self)
        self.view_mode_group.setExclusive(True)
        
        self.btn_view_file = self.create_header_button("view_file", "File Mode", checkable=True)
        self.btn_view_grid = self.create_header_button("view_grid", "Grid Mode", checkable=True)
        self.btn_view_group = self.create_header_button("view_group", "Groups Mode", checkable=True)
        
        self.view_mode_group.addButton(self.btn_view_file)
        self.view_mode_group.addButton(self.btn_view_grid)
        self.view_mode_group.addButton(self.btn_view_group)
        
        self.btn_view_file.clicked.connect(lambda: self._on_display_mode_changed("file"))
        self.btn_view_grid.clicked.connect(lambda: self._on_display_mode_changed("grid"))
        self.btn_view_group.clicked.connect(lambda: self._on_display_mode_changed("grouped"))

        # Label View Toggle
        self.btn_labels = self.create_header_button("label", "Toggle Labels", checkable=True)
        self.btn_labels.setChecked(self._show_labels)
        self.btn_labels.clicked.connect(self.toggle_labels)

        # Label Focus
        self.focus_group = QButtonGroup(self)
        self.focus_group.setExclusive(True)
        self.btn_focus_series = self.create_header_button("focus_series", "Series Focus", checkable=True)
        self.btn_focus_title = self.create_header_button("focus_title", "Title Focus", checkable=True)
        self.focus_group.addButton(self.btn_focus_series)
        self.focus_group.addButton(self.btn_focus_title)
        
        self.btn_focus_series.clicked.connect(lambda: self._on_label_focus_changed("series"))
        self.btn_focus_title.clicked.connect(lambda: self._on_label_focus_changed("title"))

        # Sort Direction
        self.sort_dir_group = QButtonGroup(self)
        self.sort_dir_group.setExclusive(True)
        self.btn_sort_asc = self.create_header_button("sort_asc", "Sort Ascending", checkable=True)
        self.btn_sort_desc = self.create_header_button("sort_desc", "Sort Descending", checkable=True)
        self.sort_dir_group.addButton(self.btn_sort_asc)
        self.sort_dir_group.addButton(self.btn_sort_desc)
        
        self.btn_sort_asc.clicked.connect(lambda: self._on_sort_dir_changed("asc"))
        self.btn_sort_desc.clicked.connect(lambda: self._on_sort_dir_changed("desc"))

        # Sort By
        self.sort_by_group = QButtonGroup(self)
        self.sort_by_group.setExclusive(True)
        self.btn_sort_alpha = self.create_header_button("sort_alpha", "Sort A-Z", checkable=True)
        self.btn_sort_date = self.create_header_button("sort_date", "Sort by Pub Date", checkable=True)
        self.btn_sort_added = self.create_header_button("sort_added", "Sort by Date Added", checkable=True)
        self.sort_by_group.addButton(self.btn_sort_alpha)
        self.sort_by_group.addButton(self.btn_sort_date)
        self.sort_by_group.addButton(self.btn_sort_added)
        
        self.btn_sort_alpha.clicked.connect(lambda: self._on_sort_order_changed("alpha"))
        self.btn_sort_date.clicked.connect(lambda: self._on_sort_order_changed("pub_date"))
        self.btn_sort_added.clicked.connect(lambda: self._on_sort_order_changed("added_date"))

        # Misc Grouping
        self.btn_group_misc = self.create_header_button("group_misc", "Toggle Misc. Grouping", checkable=True)
        self.btn_group_misc.setChecked(self.config_manager.get_library_group_misc())
        self.btn_group_misc.clicked.connect(self._on_misc_group_changed)

        # Group By Dropdown
        from PyQt6.QtWidgets import QMenu
        self.btn_group_by = self.create_header_button("group_by", "Group By Options")
        self.group_by_menu = QMenu(self)
        self.btn_group_by.setMenu(self.group_by_menu)
        self._build_group_by_menu()

        self.path_breadcrumb = QWidget()
        self.path_layout = QHBoxLayout(self.path_breadcrumb)
        self.path_layout.setContentsMargins(0, 0, 0, 0)
        s = UIConstants.scale
        self.path_layout.setSpacing(s(5))
        
        self.lib_icon_label = QLabel()
        self.lib_icon_label.setPixmap(ThemeManager.get_icon("library").pixmap(s(18), s(18)))
        self.path_layout.addWidget(self.lib_icon_label)
        
        self.path_label = QLabel("")
        self.path_label.setObjectName("path_label")
        self.path_layout.addWidget(self.path_label, 1)
        
        self.btn_select = self.create_header_button("select", "Select Mode", checkable=True)
        self.btn_select.clicked.connect(self.toggle_selection_mode)
        
        self.header_layout.addWidget(self.btn_up)
        self.header_layout.addWidget(self.path_breadcrumb, 1)
        
        # Standard spacing between distinct elements
        GROUP_GAP = s(12)
        
        # 1. Mode Selection (3 buttons)
        view_mode_layout = QHBoxLayout()
        view_mode_layout.setSpacing(0)
        view_mode_layout.setContentsMargins(0, 0, 0, 0)
        view_mode_layout.addWidget(self.btn_view_file)
        view_mode_layout.addWidget(self.btn_view_grid)
        view_mode_layout.addWidget(self.btn_view_group)
        self.header_layout.addLayout(view_mode_layout)
        
        self.header_layout.addSpacing(GROUP_GAP)
        
        # 2. Group Selection (Solo Dropdown)
        self.header_layout.addWidget(self.btn_group_by)
        
        self.header_layout.addSpacing(GROUP_GAP)
        
        # 3. Misc Group Toggle (Solo)
        self.header_layout.addWidget(self.btn_group_misc)
        
        self.header_layout.addSpacing(GROUP_GAP)
        
        # 4. Sort By (3 buttons)
        sort_by_layout = QHBoxLayout()
        sort_by_layout.setSpacing(0)
        sort_by_layout.setContentsMargins(0, 0, 0, 0)
        sort_by_layout.addWidget(self.btn_sort_alpha)
        sort_by_layout.addWidget(self.btn_sort_date)
        sort_by_layout.addWidget(self.btn_sort_added)
        self.header_layout.addLayout(sort_by_layout)
        
        self.header_layout.addSpacing(GROUP_GAP)
        
        # 5. Sort Order (2 buttons)
        sort_dir_layout = QHBoxLayout()
        sort_dir_layout.setSpacing(0)
        sort_dir_layout.setContentsMargins(0, 0, 0, 0)
        sort_dir_layout.addWidget(self.btn_sort_asc)
        sort_dir_layout.addWidget(self.btn_sort_desc)
        self.header_layout.addLayout(sort_dir_layout)
        
        self.header_layout.addSpacing(GROUP_GAP)
        
        # 6. Label Toggle (Solo)
        self.header_layout.addWidget(self.btn_labels)
        
        self.header_layout.addSpacing(GROUP_GAP)
        
        # 7. Focus (2 buttons)
        label_focus_layout = QHBoxLayout()
        label_focus_layout.setSpacing(0)
        label_focus_layout.setContentsMargins(0, 0, 0, 0)
        label_focus_layout.addWidget(self.btn_focus_series)
        label_focus_layout.addWidget(self.btn_focus_title)
        self.header_layout.addLayout(label_focus_layout)
        
        self.header_layout.addSpacing(GROUP_GAP)
        
        self.header_layout.addWidget(self.btn_select)
        self.header_layout.addWidget(self.btn_refresh)
        
        self._refresh_toolbar_states()

        # Status & Progress (using base class members)
        self.scan_label = self.status_label
        self.progress = self.progress_bar
        
        # Stacked Content Area
        self.stack = QStackedWidget()
        
        # 0: Folders View
        self.list_widget = QListWidget()
        self.folders_delegate = LibraryCardDelegate(self.list_widget, show_labels=True, image_manager=self.image_manager)
        self.list_widget.setItemDelegate(self.folders_delegate)

        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        s = UIConstants.scale
        self.list_widget.setSpacing(s(10))
        icon_w = UIConstants.CARD_WIDTH - s(20)
        icon_h = UIConstants.CARD_HEIGHT - s(50)
        self.list_widget.setIconSize(QSize(icon_w, icon_h))
        self.list_widget.itemClicked.connect(self._on_folder_item_clicked)
        self.list_widget.itemSelectionChanged.connect(self._update_selection_ui)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(lambda pos: self._on_item_context_menu(pos, self.list_widget))
        self.stack.addWidget(self.list_widget)
        
        # 1: Grouped View (Series)
        self.grouped_scroll = QScrollArea()
        self.grouped_scroll.setWidgetResizable(True)
        self.grouped_container = QWidget()
        self.grouped_layout = QVBoxLayout(self.grouped_container)
        self.grouped_layout.setContentsMargins(0, 0, 0, 0)
        self.grouped_layout.setSpacing(2)
        self.grouped_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Add a permanent widget-based spacer at the bottom to ensure items always stick to the top
        self._grouped_spacer = QWidget()
        self._grouped_spacer.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        self.grouped_layout.addWidget(self._grouped_spacer)

        self.grouped_layout.setStretch(self.grouped_layout.count() - 1, 100) # Give spacer huge stretch
        
        self.grouped_scroll.setWidget(self.grouped_container)
        self.stack.addWidget(self.grouped_scroll)
        
        # 2: Alphabetical View
        self.alpha_list = QListWidget()
        self.alpha_delegate = LibraryCardDelegate(self.alpha_list, show_labels=True, image_manager=self.image_manager)
        self.alpha_list.setItemDelegate(self.alpha_delegate)
        s = UIConstants.scale
        self.alpha_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.alpha_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.alpha_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.alpha_list.setSpacing(s(10))
        self.alpha_list.setIconSize(QSize(icon_w, icon_h))
        self.alpha_list.setWordWrap(True)
        self.alpha_list.itemClicked.connect(self._on_db_item_clicked)
        self.alpha_list.itemSelectionChanged.connect(self._update_selection_ui)
        self.alpha_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.alpha_list.customContextMenuRequested.connect(lambda pos: self._on_item_context_menu(pos, self.alpha_list))
        self.stack.addWidget(self.alpha_list)

        # Selection Action Bar Configuration (using base class layout)
        self.btn_sel_cancel.clicked.connect(lambda: self.toggle_selection_mode(False))

        self.btn_sel_mark_read = QPushButton("Mark Read")
        self.btn_sel_mark_read.setIcon(ThemeManager.get_icon("action_read", "text_dim"))
        self.btn_sel_mark_read.clicked.connect(self._on_bulk_mark_read)
        self.btn_sel_mark_read.setEnabled(False)

        self.btn_sel_mark_unread = QPushButton("Mark Unread")
        self.btn_sel_mark_unread.setIcon(ThemeManager.get_icon("action_unread", "text_dim"))
        self.btn_sel_mark_unread.clicked.connect(self._on_bulk_mark_unread)
        self.btn_sel_mark_unread.setEnabled(False)

        self.btn_sel_delete = QPushButton("Delete Selected")
        self.btn_sel_delete.setIcon(ThemeManager.get_icon("action_delete", "text_dim"))
        self.btn_sel_delete.clicked.connect(self._on_bulk_delete)
        self.btn_sel_delete.setEnabled(False)
        
        self.selection_layout.addWidget(self.btn_sel_mark_read)
        self.selection_layout.addWidget(self.btn_sel_mark_unread)
        self.selection_layout.addStretch()
        self.selection_layout.addWidget(self.btn_sel_delete)
        
        self.add_content_widget(self.stack)
        
        self._selection_mode = False
        self._is_dirty = True # Flag for initial load in showEvent

    def toggle_selection_mode(self, enabled: Optional[bool] = None):
        if enabled is None:
            enabled = not self._selection_mode
            
        super().toggle_selection_mode(enabled)
        self._selection_mode = enabled
        
        mode = QAbstractItemView.SelectionMode.MultiSelection if enabled else QAbstractItemView.SelectionMode.NoSelection
        self.list_widget.setSelectionMode(mode)
        self.alpha_list.setSelectionMode(mode)
        
        # Also update all SeriesSections in grouped view
        for i in range(self.grouped_layout.count()):
            item = self.grouped_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), LibrarySection):
                item.widget().list_widget.setSelectionMode(mode)
                if not enabled:
                    item.widget().list_widget.clearSelection()
        
        if not enabled:
            self.list_widget.clearSelection()
            self.alpha_list.clearSelection()
            self._update_selection_ui()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape and self._selection_mode:
            self.toggle_selection_mode(False)
        else:
            super().keyPressEvent(event)

    def _get_all_selected_items(self):
        selected_items = []
        
        def get_selections(view):
            if isinstance(view, QListWidget):
                return view.selectedItems()
            elif isinstance(view, QListView):
                # We use BaseCardRibbon which has QStandardItemModel
                indices = view.selectionModel().selectedIndexes()
                items = []
                model = view.model()
                for idx in indices:
                    if hasattr(model, "itemFromIndex"):
                        items.append(model.itemFromIndex(idx))
                return items
            return []

        if self.stack.currentIndex() == 0:
            selected_items.extend(get_selections(self.list_widget))
        elif self.stack.currentIndex() == 2:
            selected_items.extend(get_selections(self.alpha_list))
        elif self.stack.currentIndex() == 1:
            for i in range(self.grouped_layout.count()):
                item = self.grouped_layout.itemAt(i)
                if item and item.widget() and isinstance(item.widget(), LibrarySection):
                    selected_items.extend(get_selections(item.widget().list_widget))
        return selected_items

    def _update_selection_ui(self):
        if not self._selection_mode: return
        
        selected_items = self._get_all_selected_items()
        
        # Filter out directories
        valid_selections = []
        for item in selected_items:
            path_or_db = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(path_or_db, Path):
                if not path_or_db.is_dir():
                    valid_selections.append(item)
            elif isinstance(path_or_db, dict) or isinstance(path_or_db, str): 
                valid_selections.append(item)

        count = len(valid_selections)
        self.label_sel_count.setText(f"{count} item{'s' if count != 1 else ''} selected")
        self.btn_sel_delete.setEnabled(count > 0)
        self.btn_sel_delete.setText(f"Delete {count} Item{'s' if count != 1 else ''}")
        self.btn_sel_mark_read.setEnabled(count > 0)
        self.btn_sel_mark_unread.setEnabled(count > 0)

    def _on_bulk_delete(self):
        from PyQt6.QtWidgets import QMessageBox
        
        selected_items = self._get_all_selected_items()
        
        paths_to_delete = []
        for item in selected_items:
            data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, Path) and not data.is_dir():
                paths_to_delete.append(data)
            elif isinstance(data, dict):
                paths_to_delete.append(Path(data["file_path"]))
            elif isinstance(data, str) and Path(data).exists():
                paths_to_delete.append(Path(data))
                
        if not paths_to_delete: return
        
        reply = QMessageBox.question(
            self, "Confirm Bulk Delete",
            f"Are you sure you want to permanently delete {len(paths_to_delete)} comic{'s' if len(paths_to_delete) != 1 else ''}?\nThis action cannot be undone and will delete the files from your disk.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.toggle_selection_mode(False)
            import os
            deleted_count = 0
            for p in paths_to_delete:
                try:
                    if p.exists():
                        os.remove(p)
                    self.db.remove_comic(str(p))
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"Failed to delete {p}: {e}")
            
            logger.info(f"Bulk deleted {deleted_count} files.")
            self.refresh_and_scan()

    def _on_bulk_mark_read(self):
        selected_items = self._get_all_selected_items()
        paths = []
        for item in selected_items:
            data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, Path) and not data.is_dir():
                paths.append(str(data))
            elif isinstance(data, dict):
                paths.append(data.get("file_path"))
            elif isinstance(data, str):
                paths.append(data)
                
        if not paths: return
        
        for p in paths:
            if p: self.db.mark_as_read(p)
            
        self.toggle_selection_mode(False)
        self._reload_current_view()

    def _on_bulk_mark_unread(self):
        selected_items = self._get_all_selected_items()
        paths = []
        for item in selected_items:
            data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, Path) and not data.is_dir():
                paths.append(str(data))
            elif isinstance(data, dict):
                paths.append(data.get("file_path"))
            elif isinstance(data, str):
                paths.append(data)
                
        if not paths: return
        
        for p in paths:
            if p: self.db.mark_as_unread(p)
            
        self.toggle_selection_mode(False)
        self._reload_current_view()

    def _save_cover_to_cache(self, path: Path, cover_bytes: bytes) -> None:
        """Called from scanner worker thread to save a resized thumbnail to disk cache."""
        url = f"local-cbz://{path.absolute()}/{_COVER_URL_SUFFIX}"
        cache_path = self.image_manager._get_cache_path(url)
        if not cache_path.exists():
            _save_thumbnail(cover_bytes, cache_path)

    def toggle_labels(self, enabled: bool):
        """Toggle label visibility for cards."""
        self.btn_labels.setChecked(enabled)
        self._on_show_labels_changed(enabled)

    def _on_show_labels_changed(self, checked):
        self._show_labels = checked
        self.config_manager.set_show_labels(self._show_labels)
        self.alpha_delegate.show_labels = self._show_labels
        self.folders_delegate.show_labels = self._show_labels
        self._reload_current_view()
    def _on_scan_progress_ui(self, curr, total, msg):
        self.status_area.setVisible(True)
        self.scan_label.setText(msg)
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(curr)
        else:
            self.progress.setRange(0, 0)

    def _on_scan_finished_ui(self, changed):
        self.status_area.setVisible(False)
        if changed:
            self._reload_current_view()

    def reapply_theme(self):
        """Standardized theme application for Library view."""
        super().reapply_theme()
        theme = ThemeManager.get_current_theme_colors()

        # 1. Header Elements
        if hasattr(self, "lib_icon_label"):
            self.lib_icon_label.setPixmap(ThemeManager.get_icon("library").pixmap(UIConstants.scale(18), UIConstants.scale(18)))
        if hasattr(self, "path_label"):
            self.path_label.setStyleSheet(f"font-size: {UIConstants.FONT_SIZE_SECTION_HEADER}px; font-weight: bold; color: {theme['text_main']};")

        # Update all toolbar icons
        if hasattr(self, "btn_up"): self.btn_up.setIcon(ThemeManager.get_icon("back", "text_dim"))
        if hasattr(self, "btn_refresh"): self.btn_refresh.setIcon(ThemeManager.get_icon("refresh", "text_dim"))
        if hasattr(self, "btn_select"): self.btn_select.setIcon(ThemeManager.get_icon("select", "text_dim"))
        
        # Apply Segmented Styling to groups
        if hasattr(self, "btn_view_file"):
            self.btn_view_file.setIcon(ThemeManager.get_icon("view_file", "text_dim"))
            self.btn_view_grid.setIcon(ThemeManager.get_icon("view_grid", "text_dim"))
            self.btn_view_group.setIcon(ThemeManager.get_icon("view_group", "text_dim"))
            self._style_segmented_group([self.btn_view_file, self.btn_view_grid, self.btn_view_group])
            
        if hasattr(self, "btn_labels"):
            self.btn_labels.setIcon(ThemeManager.get_icon("label", "text_dim"))
            self._style_segmented_group([self.btn_labels])
            
        if hasattr(self, "btn_focus_series"):
            self.btn_focus_series.setIcon(ThemeManager.get_icon("focus_series", "text_dim"))
            self.btn_focus_title.setIcon(ThemeManager.get_icon("focus_title", "text_dim"))
            self._style_segmented_group([self.btn_focus_series, self.btn_focus_title])
            
        if hasattr(self, "btn_sort_asc") and hasattr(self, "btn_sort_desc"):
            self.btn_sort_asc.setIcon(ThemeManager.get_icon("sort_asc", "text_dim"))
            self.btn_sort_desc.setIcon(ThemeManager.get_icon("sort_desc", "text_dim"))
            self._style_segmented_group([self.btn_sort_asc, self.btn_sort_desc])
            
        if hasattr(self, "btn_sort_alpha"):
            self.btn_sort_alpha.setIcon(ThemeManager.get_icon("sort_alpha", "text_dim"))
            self.btn_sort_date.setIcon(ThemeManager.get_icon("sort_date", "text_dim"))
            self.btn_sort_added.setIcon(ThemeManager.get_icon("sort_added", "text_dim"))
            self._style_segmented_group([self.btn_sort_alpha, self.btn_sort_date, self.btn_sort_added])
            
        if hasattr(self, "btn_group_misc"):
            self.btn_group_misc.setIcon(ThemeManager.get_icon("group_misc", "text_dim"))
            self._style_segmented_group([self.btn_group_misc])

        if hasattr(self, "btn_group_by"):
            self.btn_group_by.setIcon(ThemeManager.get_icon("group_by", "text_dim"))
            self._style_segmented_group([self.btn_group_by])
        
        self._refresh_toolbar_states()

        # 2. Selection Bar Elements
        btn_style = f"padding: 4px 8px; font-size: 11px; background-color: {theme['bg_sidebar']}; color: {theme['text_main']}; border: 1px solid {theme['border']};"
        delete_style = f"padding: 4px 10px; font-size: 11px; font-weight: bold; background-color: {theme['accent']}; color: {theme['bg_main']}; border: none;"
        
        if hasattr(self, "btn_sel_mark_read"):
            self.btn_sel_mark_read.setStyleSheet(btn_style)
            self.btn_sel_mark_read.setIcon(ThemeManager.get_icon("action_read", "text_dim"))
        if hasattr(self, "btn_sel_mark_unread"):
            self.btn_sel_mark_unread.setStyleSheet(btn_style)
            self.btn_sel_mark_unread.setIcon(ThemeManager.get_icon("action_unread", "text_dim"))
        if hasattr(self, "btn_sel_delete"):
            self.btn_sel_delete.setStyleSheet(delete_style)
            self.btn_sel_delete.setIcon(ThemeManager.get_icon("action_delete", "white"))
        
        # Ensure grouped view container doesn't have a white background
        if hasattr(self, "grouped_scroll"):
            self.grouped_scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        if hasattr(self, "grouped_container"):
            self.grouped_container.setStyleSheet(f"background-color: {theme['bg_main']};")

        # 3. Refresh active view if it contains dynamic headers (like LibrarySection)
        if hasattr(self, "stack") and self.stack.currentIndex() == 1:
            for i in range(self.grouped_layout.count()):
                item = self.grouped_layout.itemAt(i)
                if item and item.widget() and isinstance(item.widget(), LibrarySection):
                    item.widget().reapply_theme()

    def _build_group_by_menu(self):
        from PyQt6.QtGui import QAction, QActionGroup
        self.group_by_menu.clear()
        
        group_by = self.config_manager.get_library_group_by()
        group_group = QActionGroup(self)
        for val, label in [("series", "Series"), ("publisher", "Publisher"), ("writer", "Writer"), ("artist", "Artist")]:
            action = QAction(label, self, checkable=True)
            action.setChecked(group_by == val)
            action.triggered.connect(lambda checked, v=val: self._on_group_by_changed(v))
            self.group_by_menu.addAction(action)
            group_group.addAction(action)

    def _refresh_toolbar_states(self):
        if not hasattr(self, "btn_view_file"): return
        
        # View Modes
        mode = self.config_manager.get_library_display_mode()
        self.btn_view_file.setChecked(mode == "file")
        self.btn_view_grid.setChecked(mode == "grid")
        self.btn_view_group.setChecked(mode == "grouped")
        
        # Labels
        self.btn_labels.setChecked(self._show_labels)
        
        # Label Focus
        focus = self.config_manager.get_library_label_focus()
        self.btn_focus_series.setChecked(focus == "series")
        self.btn_focus_title.setChecked(focus == "title")
        
        # Sort Direction
        sort_dir = self.config_manager.get_library_sort_direction()
        self.btn_sort_asc.setChecked(sort_dir == "asc")
        self.btn_sort_desc.setChecked(sort_dir == "desc")
        
        # Sort Order
        order = self.config_manager.get_library_sort_order()
        self.btn_sort_alpha.setChecked(order == "alpha")
        self.btn_sort_date.setChecked(order == "pub_date")
        self.btn_sort_added.setChecked(order == "added_date")
        
        # Misc Grouping
        self.btn_group_misc.setEnabled(mode == "grouped")
        self.btn_group_misc.setChecked(self.config_manager.get_library_group_misc())
        
        # Group By
        self.btn_group_by.setEnabled(mode == "grouped")
        self._build_group_by_menu()

    def _on_label_focus_changed(self, focus: str):
        if self.config_manager.get_library_label_focus() == focus: return
        self.config_manager.set_library_label_focus(focus)
        self._refresh_toolbar_states()
        self._reload_current_view()

    def _on_display_mode_changed(self, mode: str):
        if self.config_manager.get_library_display_mode() == mode: return
        self.config_manager.set_library_display_mode(mode)
        self._refresh_toolbar_states()
        
        if mode == "file":
            self.stack.setCurrentIndex(0)
        elif mode == "grouped":
            self.stack.setCurrentIndex(1)
        elif mode == "grid":
            self.stack.setCurrentIndex(2)
            
        self.btn_up.setVisible(False)
        self.nav_changed.emit()
        self._reload_current_view()
        
    def _on_group_by_changed(self, group_by: str):
        if self.config_manager.get_library_group_by() == group_by: return
        self.config_manager.set_library_group_by(group_by)
        self._refresh_toolbar_states()
        self._reload_current_view()
        
    def _on_misc_group_changed(self, checked: bool):
        if self.config_manager.get_library_group_misc() == checked: return
        self.config_manager.set_library_group_misc(checked)
        self._refresh_toolbar_states()
        self._reload_current_view()
        
    def _on_sort_order_changed(self, sort_order: str):
        if self.config_manager.get_library_sort_order() == sort_order: return
        self.config_manager.set_library_sort_order(sort_order)
        self._refresh_toolbar_states()
        self._reload_current_view()
        
    def _on_sort_dir_changed(self, sort_dir: str):
        if self.config_manager.get_library_sort_direction() == sort_dir: return
        self.config_manager.set_library_sort_direction(sort_dir)
        self._refresh_toolbar_states()
        self._reload_current_view()

    @pyqtSlot()
    def _reload_current_view(self):
        mode = self.config_manager.get_library_display_mode()
        
        self.stack.setUpdatesEnabled(False)
        try:
            # Ensure correct stack index is shown
            if mode == "file":
                self.stack.setCurrentIndex(0)
                asyncio.create_task(self._load_dir(self.current_dir))
            elif mode == "grouped":
                self.stack.setCurrentIndex(1)
                asyncio.create_task(self._load_grouped())
            elif mode == "grid":
                self.stack.setCurrentIndex(2)
                asyncio.create_task(self._load_grid())
        finally:
            self.stack.setUpdatesEnabled(True)


    def refresh_and_scan(self):
        self.root_dir = self.config_manager.get_library_dir()
        self.scanner.library_dir = self.root_dir
        # 1. Load from DB immediately
        self._reload_current_view()
        # 2. Start scan in background
        if not self.scanner.is_scanning:
            asyncio.create_task(self.scanner.scan())

    def refresh_icons(self):
        theme = ThemeManager.get_current_theme_colors()
        self.btn_up.setIcon(ThemeManager.get_icon("back"))
        self.btn_refresh.setIcon(ThemeManager.get_icon("refresh"))
        self.btn_select.setIcon(ThemeManager.get_icon("select"))
        self.btn_view_options.setIcon(ThemeManager.get_icon("settings"))
        s = UIConstants.scale
        self.lib_icon_label.setPixmap(ThemeManager.get_icon("library").pixmap(s(18), s(18)))
        
        # Refresh path label style
        self.path_label.setStyleSheet(f"font-size: {UIConstants.FONT_SIZE_SECTION_HEADER}px; font-weight: bold;")
        
        # Trigger update of existing sections
        for i in range(self.stack.count()):
            widget = self.stack.widget(i)
            if hasattr(widget, "update"):
                widget.update()

    def set_dirty(self):
        self._is_dirty = True
        if self.isVisible():
            self.refresh_and_scan()

    def showEvent(self, event):
        super().showEvent(event)
        if self._is_dirty:
            self._is_dirty = False
            self.refresh_and_scan()

    def refresh(self):
        self.toggle_selection_mode(False)
        self.root_dir = self.config_manager.get_library_dir()
        if not self.current_dir or not self.current_dir.exists() or not str(self.current_dir).startswith(str(self.root_dir)):
            self.current_dir = self.root_dir
        
        # Ensure we are on the right stack index
        index = self.config_manager.get_library_view_mode()
        stack_map = {0: 0, 1: 1, 2: 2, 3: 1, 4: 1, 5: 1}
        self.stack.setCurrentIndex(stack_map.get(index, 0))
        self.btn_up.setVisible(False)

        self._reload_current_view()

    async def _load_dir(self, path: Path):
        self.current_dir = path
        self.nav_changed.emit()
        self.path_label.setText(f"> {path}")

        # Fetch data FIRST
        sort_dir = self.config_manager.get_library_sort_direction()
        sort_order = self.config_manager.get_library_sort_order()
        reverse = (sort_dir == "desc")
        
        entries = await asyncio.to_thread(_list_dir, path, sort_dir)
        # Single query for all comics under this directory
        dir_rows = await asyncio.to_thread(self.db.get_comics_in_dir, str(path.absolute()))

        if sort_order != "alpha":
            def entry_sort_key(e):
                # Directories always first (or last if reversed)
                if e.is_dir:
                    return (0 if not reverse else 1, e.name.lower())
                
                row = dir_rows.get(str(e.path.absolute()))
                if not row:
                    return (1 if not reverse else 0, e.name.lower())
                
                r = dict(row)
                if sort_order == "pub_date":
                    # (block, year, name)
                    return (1 if not reverse else 0, str(r.get("year") or ""), e.name.lower())
                if sort_order == "added_date":
                    # (block, mtime, name)
                    return (1 if not reverse else 0, r.get("file_mtime") or 0, e.name.lower())
                return (1 if not reverse else 0, e.name.lower())
            
            entries.sort(key=entry_sort_key, reverse=reverse)

        self.list_widget.setUpdatesEnabled(False)
        try:
            self.list_widget.clear()
            self.config_manager.set_last_folder_path(str(path.absolute()))
            self.current_dir = path

            label_focus = self.config_manager.get_library_label_focus()
            for entry in entries:
                if entry.is_dir:
                    item = QListWidgetItem(entry.name)
                    item.setData(Qt.ItemDataRole.UserRole, entry.path)
                    item.setIcon(ThemeManager.get_icon("folder"))
                else:
                    row = dir_rows.get(str(entry.path.absolute()))
                    
                    # In File mode, we always use filename for display
                    display_text = entry.name
                    
                    if row:
                        r = dict(row)
                        primary, secondary = generate_comic_labels(r, label_focus)
                    else:
                        primary, secondary = entry.name, ""

                    # Label data (primary, secondary) for the card delegate
                    card_primary = display_text # In _load_dir we are ALWAYS in file mode
                    
                    item = QListWidgetItem(display_text)
                    item.setData(Qt.ItemDataRole.UserRole, entry.path)
                    if row:
                        item.setData(Qt.ItemDataRole.UserRole + 1, (r.get("current_page") or 0, r.get("page_count") or 0))
                        item.setData(Qt.ItemDataRole.UserRole + 2, (card_primary, secondary))

                    item.setIcon(ThemeManager.get_icon("book"))
                    item.setToolTip(display_text)
                    try:
                        asyncio.create_task(self._load_thumb_for_item(entry.path, item))
                    except RuntimeError:
                        pass

                self.list_widget.addItem(item)
        finally:
            self.list_widget.setUpdatesEnabled(True)

    async def _load_grouped(self):
        group_by = self.config_manager.get_library_group_by()
        sort_order = self.config_manager.get_library_sort_order()
        sort_dir = self.config_manager.get_library_sort_direction()
        misc_toggle = self.config_manager.get_library_group_misc()

        self.path_label.setText(f"> Grouped by {group_by.replace('_', ' ').capitalize()}")

        # 0. Capture expansion states before clearing
        expansion_states = {}
        for i in range(self.grouped_layout.count()):
            item = self.grouped_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), LibrarySection):
                s = item.widget()
                expansion_states[s.header_label.text()] = s.list_widget.isVisible()

        # 1. Fetch data from DB FIRST
        grouped = await asyncio.to_thread(self.db.get_comics_grouped, group_by, sort_order, sort_dir)
        label_focus = self.config_manager.get_library_label_focus()

        # 2. Suspend updates and clear ONLY right before rebuilding
        self.setUpdatesEnabled(False)
        try:
            # Clear all widgets except the permanent spacer
            while self.grouped_layout.count() > 1:
                item = self.grouped_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
                else:
                    self.grouped_layout.removeItem(item)

            group_items = []
            one_offs = []

            for name, rows in grouped.items():
                dict_rows = [dict(r) for r in rows]
                if misc_toggle and (not name or name.strip() == "" or name.startswith("Unknown") or len(rows) == 1):
                    one_offs.extend(dict_rows)
                else:
                    group_items.append((name, dict_rows))

            group_items.sort(key=lambda x: x[0].lower(), reverse=(sort_dir == "desc"))

            for group_name, rows in group_items:
                range_str = ""
                if group_by == "series":
                    issues = []
                    for r in rows:
                        issue_val = r.get("issue")
                        if issue_val and str(issue_val).isdigit():
                            issues.append(int(issue_val))
                    if issues:
                        range_str = f" {format_ranges(issues)}"

                title = f"{group_name}{range_str}"

                is_file_mode = (self.config_manager.get_library_display_mode() == "file")
                section = LibrarySection(title, rows, self._on_db_item_clicked, is_grid=False, image_manager=self.image_manager, meta_sem=self._meta_sem, show_labels=self._show_labels, label_focus=label_focus, is_folder_mode=is_file_mode, config_manager=self.config_manager, on_context_menu=lambda pos: self._on_group_context_menu(pos, section))

                # Restore expansion state
                if title in expansion_states:
                    section.set_expanded(expansion_states[title])

                if section.is_grid:
                    section.list_widget.itemSelectionChanged.connect(self._update_selection_ui)
                else:
                    section.list_widget.selectionModel().selectionChanged.connect(self._update_selection_ui)

                if self._selection_mode:
                    section.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)

                section.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                section.list_widget.customContextMenuRequested.connect(lambda pos, w=section.list_widget: self._on_item_context_menu(pos, w))

                # Insert before the spacer
                self.grouped_layout.insertWidget(self.grouped_layout.count() - 1, section)

            if one_offs:
                title = f"{len(one_offs)} Miscellaneous"

                reverse = (sort_dir == "desc")
                if sort_order == "pub_date":
                    one_offs.sort(key=lambda x: (str(x.get("year") or ""), (x.get("title") or "").lower()), reverse=reverse)
                elif sort_order == "added_date":
                    one_offs.sort(key=lambda x: (x.get("file_mtime") or 0, (x.get("title") or "").lower()), reverse=reverse)
                else:
                    one_offs.sort(key=lambda r: generate_comic_labels(dict(r), label_focus)[0].lower(), reverse=reverse)

                section = LibrarySection(title, one_offs, self._on_db_item_clicked, is_grid=True, image_manager=self.image_manager, meta_sem=self._meta_sem, show_labels=self._show_labels, label_focus=label_focus, is_folder_mode=is_file_mode, config_manager=self.config_manager, on_context_menu=lambda pos: self._on_group_context_menu(pos, section))

                # Restore expansion state
                if title in expansion_states:
                    section.set_expanded(expansion_states[title])

                if section.is_grid:
                    section.list_widget.itemSelectionChanged.connect(self._update_selection_ui)
                else:
                    section.list_widget.selectionModel().selectionChanged.connect(self._update_selection_ui)

                if self._selection_mode:
                    section.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)

                section.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                section.list_widget.customContextMenuRequested.connect(lambda pos, w=section.list_widget: self._on_item_context_menu(pos, w))

                # Insert before the spacer
                self.grouped_layout.insertWidget(self.grouped_layout.count() - 1, section)

        finally:
            self.setUpdatesEnabled(True)

    async def _load_grid(self):
        self.path_label.setText("> Grid")

        sort_order = self.config_manager.get_library_sort_order()
        sort_dir = self.config_manager.get_library_sort_direction()
        is_file_mode = (self.config_manager.get_library_display_mode() == "file")

        # 1. Fetch data FIRST
        rows = await asyncio.to_thread(self.db.get_comics_grid, sort_order, sort_dir)
        
        if is_file_mode and sort_order == "alpha":
            reverse = (sort_dir == "desc")
            rows = sorted(rows, key=lambda r: Path(r["file_path"]).name.lower(), reverse=reverse)

        # 2. Rebuild UI efficiently
        self.alpha_list.setUpdatesEnabled(False)
        try:
            self.alpha_list.clear()
            label_focus = self.config_manager.get_library_label_focus()

            for row in rows:
                r = dict(row)
                primary, secondary = generate_comic_labels(r, label_focus)
                
                # In File mode, we always use filename for display
                display_text = Path(r["file_path"]).name if is_file_mode else primary

                item = QListWidgetItem(display_text)
                item.setData(Qt.ItemDataRole.UserRole, Path(r["file_path"]))
                item.setData(Qt.ItemDataRole.UserRole + 1, (r.get("current_page") or 0, r.get("page_count") or 0))
                
                # Label data (primary, secondary) for the card delegate
                card_primary = display_text if is_file_mode else primary
                item.setData(Qt.ItemDataRole.UserRole + 2, (card_primary, secondary))

                item.setIcon(ThemeManager.get_icon("book"))
                item.setToolTip(display_text)
                self.alpha_list.addItem(item)
                try:
                    asyncio.create_task(self._load_thumb_for_item(Path(r["file_path"]), item))
                except RuntimeError:
                    pass
        finally:
            self.alpha_list.setUpdatesEnabled(True)
    async def _load_thumb_for_item(self, path: Path, item: QListWidgetItem):
        if path.suffix.lower() in (".cbz", ".cbr", ".cb7"):
            url = f"local-cbz://{path.absolute()}/{_COVER_URL_SUFFIX}"
            cache_path = self.image_manager._get_cache_path(url)

            pixmap = QPixmapCache.find(str(cache_path))
            if pixmap:
                set_item_data(item, Qt.ItemDataRole.DecorationRole, pixmap)
                return

            if not cache_path.exists():
                async with self._meta_sem:
                    try:
                        data = await asyncio.to_thread(read_comicbox_cover, path)
                        if not data:
                            res = await asyncio.to_thread(read_first_image, path)
                            if res: _, data = res
                        if data:
                            await asyncio.to_thread(_save_thumbnail, data, cache_path)
                    except: pass

            if cache_path.exists():
                try:
                    # Decoding bytes to QImage is thread-safe and offloads the CPU work
                    img = await asyncio.to_thread(lambda: QImage(str(cache_path)))
                    if not img.isNull():
                        # QPixmap conversion must happen on UI thread, but it's very fast
                        pixmap = QPixmap.fromImage(img)
                        QPixmapCache.insert(str(cache_path), pixmap)
                        set_item_data(item, Qt.ItemDataRole.DecorationRole, pixmap)
                except Exception:
                    pass

    def _on_folder_item_clicked(self, item):
        if self._selection_mode:
            return

        # Handle both QListWidgetItem (Folders) and QModelIndex (List View)
        path = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(path, QModelIndex): # Extra safety
            path = path.data(Qt.ItemDataRole.UserRole)

        if isinstance(path, Path) and path.is_dir():
            asyncio.create_task(self._load_dir(path))
        else:
            # Handle QListWidgetItem vs QModelIndex for context gathering
            context = []
            if hasattr(item, "listWidget"): # QListWidgetItem
                lw = item.listWidget()
                if lw:
                    for i in range(lw.count()):
                        p = lw.item(i).data(Qt.ItemDataRole.UserRole)
                        if isinstance(p, Path) and not p.is_dir():
                            context.append(p)
            elif isinstance(item, QModelIndex): # QModelIndex (from clicked signal)
                model = item.model()
                if model:
                    for i in range(model.rowCount()):
                        p = model.index(i, 0).data(Qt.ItemDataRole.UserRole)
                        if isinstance(p, Path) and not p.is_dir():
                            context.append(p)
            
            self.on_open_comic(path, context)

    def _on_db_item_clicked(self, item):
        if self._selection_mode:
            return

        # Handle both QListWidgetItem (Grid) and QModelIndex (Ribbon)
        path = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(path, QModelIndex):
            path = path.data(Qt.ItemDataRole.UserRole)
            
        if isinstance(path, Path) and path.exists():
            context = []
            if hasattr(item, "listWidget"): # QListWidgetItem
                lw = item.listWidget()
                if lw:
                    for i in range(lw.count()):
                        p = lw.item(i).data(Qt.ItemDataRole.UserRole)
                        if isinstance(p, Path) and not p.is_dir():
                            context.append(p)
            elif isinstance(item, QModelIndex): # QModelIndex
                model = item.model()
                if model:
                    for i in range(model.rowCount()):
                        p = model.index(i, 0).data(Qt.ItemDataRole.UserRole)
                        if isinstance(p, Path) and not p.is_dir():
                            context.append(p)

            self.on_open_comic(path, context)

    @property
    def is_at_root(self):
        try:
            # If we're not in the Folder view (index 0), we're in a global view (Series/Alpha)
            # which are inherently "root" views.
            if self.stack.currentIndex() != 0:
                return True
            
            if not self.current_dir or not self.root_dir: return True
            self.current_dir.relative_to(self.root_dir)
            return self.current_dir == self.root_dir
        except Exception:
            return True

    def go_up(self):
        try:
            if self.is_at_root: return
            parent = self.current_dir.parent
            asyncio.create_task(self._load_dir(parent))
        except Exception:
            pass

    def _go_up(self):
        self.go_up()

    def _on_item_context_menu(self, pos, list_widget):
        logger.info(f"--- Entering _on_item_context_menu ---")
        logger.info(f"  Pos: {pos}, Widget: {list_widget.objectName()}")
        if isinstance(list_widget, QListWidget):
            item = list_widget.itemAt(pos)
        else:
            idx = list_widget.indexAt(pos)
            if not idx.isValid(): return
            model = list_widget.model()
            item = model.itemFromIndex(idx) if hasattr(model, "itemFromIndex") else None
            
        if not item: return
        
        path_or_data = item.data(Qt.ItemDataRole.UserRole)
        # If it's a folder, ignore for now
        if isinstance(path_or_data, Path) and path_or_data.is_dir():
            return
            
        file_path = None
        if isinstance(path_or_data, Path):
            file_path = str(path_or_data)
        elif isinstance(path_or_data, dict):
            file_path = str(path_or_data.get("file_path"))
        elif isinstance(path_or_data, str):
            file_path = path_or_data
            
        if not file_path: return

        # Load metadata from DB for popover
        row = self.db.get_comic(file_path)
        if not row: return
        meta = dict(row)

        # Create/Update Popover
        if not hasattr(self, "detail_popover"):
            self.detail_popover = MiniDetailPopover(self, self.config_manager.get_theme())
        
        self.detail_popover.set_show_cover(False)
        self.detail_popover.clear_actions()
        
        # Add Actions
        self.detail_popover.add_action("action_read", "Mark Read", lambda: [self.db.mark_as_read(file_path), self._reload_current_view()])
        self.detail_popover.add_action("action_unread", "Mark Unread", lambda: [self.db.mark_as_unread(file_path), self._reload_current_view()])
        
        def do_delete():
            from PyQt6.QtWidgets import QMessageBox
            import os
            reply = QMessageBox.question(
                self, "Confirm Delete",
                f"Are you sure you want to delete this comic?\nThis action cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    p = Path(file_path)
                    if p.exists(): os.remove(p)
                    self.db.remove_comic(file_path)
                    self.refresh_and_scan()
                except Exception as e:
                    logger.error(f"Failed to delete {file_path}: {e}")

        self.detail_popover.add_action("action_delete", "Delete", do_delete) 

        # Populate and Show
        # Build data dict
        creds = []
        for role in ["writer", "penciller", "inker", "colorist", "letterer", "editor"]:
            val = meta.get(role)
            if val: creds.append(f"{role.capitalize()}: {val}")
        
        # Build published string with month and year
        pub_month = meta.get("month")
        pub_year = meta.get("year")
        date_parts = []
        if pub_month:
            import calendar
            try:
                m_val = int(pub_month)
                if 1 <= m_val <= 12:
                    date_parts.append(calendar.month_name[m_val])
            except: pass
        if pub_year:
            date_parts.append(str(pub_year))

        data = {
            "credits": "\n".join(creds),
            "publisher": meta.get("publisher"),
            "published": " ".join(date_parts) if date_parts else None,
            "summary": meta.get("summary") or meta.get("description")
        }
        
        label_focus = self.config_manager.get_library_label_focus()
        primary, secondary = generate_comic_labels(meta, label_focus)
        
        self.detail_popover.populate(data=data, title=primary, subtitle=secondary)
        
        # Smart Positioning: Try to show to the right of the item
        # Get item global rect
        if isinstance(list_widget, QListWidget):
            item_rect = list_widget.visualItemRect(item)
        else:
            item_rect = list_widget.visualRect(idx)
            
        global_item_topleft = list_widget.viewport().mapToGlobal(item_rect.topLeft())
        
        # Default: To the right of the card
        pop_x = global_item_topleft.x() + item_rect.width() + UIConstants.POPOVER_OFFSET
        pop_y = global_item_topleft.y()
        
        # Screen boundary check
        screen = QApplication.primaryScreen().availableGeometry()
        if pop_x + self.detail_popover.width() > screen.right():
            # Show to the left instead
            pop_x = global_item_topleft.x() - self.detail_popover.width() - UIConstants.POPOVER_OFFSET
            
        if pop_y + self.detail_popover.height() > screen.bottom():
            # Shift up to stay on screen
            pop_y = screen.bottom() - self.detail_popover.height() - UIConstants.POPOVER_OFFSET
            
        self.detail_popover.show_at(QPoint(max(screen.left(), pop_x), max(screen.top(), pop_y)))

    def _on_group_context_menu(self, pos, section):
        from PyQt6.QtWidgets import QMenu, QMessageBox
        import os
        
        menu = QMenu(self)
        action_read = menu.addAction("Mark Group as Read")
        action_unread = menu.addAction("Mark Group as Unread")
        menu.addSeparator()
        action_expand_all = menu.addAction("Expand All")
        action_collapse_all = menu.addAction("Collapse All")
        menu.addSeparator()
        action_delete = menu.addAction("Delete Group")
        
        # Map from sender (which could be the label, the toggle button, or the header widget)
        sender = self.sender()
        if not sender: sender = section.btn_toggle
        action = menu.exec(sender.mapToGlobal(pos))
        if not action: return
        
        if action == action_expand_all or action == action_collapse_all:
            self.set_all_sections_collapsed(action == action_collapse_all)
            return

        paths = []
        for row in section.rows:
            r = dict(row)
            if r.get("file_path"): paths.append(r["file_path"])
            
        if not paths: return

        if action == action_read:
            for p in paths:
                self.db.mark_as_read(p)
            self._reload_current_view()
        elif action == action_unread:
            for p in paths:
                self.db.mark_as_unread(p)
            self._reload_current_view()
        elif action == action_delete:
            reply = QMessageBox.question(
                self, "Confirm Group Delete",
                f"Are you sure you want to delete all {len(paths)} comics in this group?\nThis action cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                deleted = 0
                for p_str in paths:
                    try:
                        p = Path(p_str)
                        if p.exists(): os.remove(p)
                        self.db.remove_comic(p_str)
                        deleted += 1
                    except Exception as e:
                        logger.error(f"Failed to delete {p_str}: {e}")
                logger.info(f"Group deleted {deleted} items.")
                self.refresh_and_scan()
