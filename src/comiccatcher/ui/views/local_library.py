# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QProgressBar, QComboBox, QStackedWidget,
    QScrollArea, QApplication, QStyledItemDelegate, QStyle,
    QAbstractItemView, QSizePolicy, QFrame, QSpacerItem, QListView,
    QButtonGroup
)
from PyQt6.QtCore import Qt, QSize, pyqtSlot, pyqtSignal, QRect, QModelIndex, QPoint, QTimer, QItemSelectionModel, QEvent
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QBrush, QPen, QImage, QPixmapCache, QKeyEvent, QStandardItemModel, QStandardItem

from comiccatcher.config import ConfigManager, CONFIG_DIR
from comiccatcher.logger import get_logger
from comiccatcher.api.image_manager import ImageManager
from comiccatcher.ui.local_archive import read_archive_first_image
from comiccatcher.ui.local_comicbox import flatten_comicbox, read_comicbox_dict, subtitle_from_flat, read_comicbox_cover, generate_comic_labels
from comiccatcher.ui.theme_manager import ThemeManager, UIConstants
from comiccatcher.api.local_db import LocalLibraryDB
from comiccatcher.api.library_scanner import LibraryScanner
from comiccatcher.ui.views.base_browser import BaseBrowserView
from comiccatcher.ui.components.library_card_delegate import LibraryCardDelegate
from comiccatcher.ui.components.base_ribbon import BaseCardRibbon
from comiccatcher.ui.components.mini_detail_popover import MiniDetailPopover

logger = get_logger("ui.local_library")

COMIC_EXTS = {".cbz", ".cbr", ".cb7", ".cbt", ".pdf"}
_COVER_URL_SUFFIX = "_cover_thumb"


def _save_thumbnail(data: bytes, cache_path: Path, thumb_w: int = 240, thumb_h: int = 360) -> bool:
    """Resize cover bytes and save as a small JPEG thumbnail. Uses image_utils for high-quality scaling."""
    from comiccatcher.ui.image_utils import scale_image_to_file
    return scale_image_to_file(data, cache_path, thumb_w, thumb_h, quality=85)

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

class ItemRoles:
    PATH = Qt.ItemDataRole.UserRole
    PROGRESS = Qt.ItemDataRole.UserRole + 1
    LABELS = Qt.ItemDataRole.UserRole + 2

def populate_item_from_row(item, row_dict, label_focus, is_folder_mode, image_manager):
    """Shared logic to initialize a list/ribbon item from a database row."""
    primary, secondary = generate_comic_labels(row_dict, label_focus)
    
    file_path = Path(row_dict["file_path"])
    display_text = file_path.name if is_folder_mode else primary
    
    # Label data (primary, secondary) for the card delegate
    card_primary = display_text if is_folder_mode else primary
    
    # 1. Set text/identities
    if isinstance(item, QListWidgetItem):
        item.setText(display_text)
    else:
        item.setText(display_text)

    set_item_data(item, ItemRoles.PATH, file_path)
    set_item_data(item, ItemRoles.PROGRESS, (row_dict.get("current_page") or 0, row_dict.get("page_count") or 0))
    set_item_data(item, ItemRoles.LABELS, (card_primary, secondary))
    set_item_data(item, Qt.ItemDataRole.ToolTipRole, card_primary)

    # 2. Try synchronous cache check to prevent pop-in
    url = f"local-archive://{file_path.absolute()}/{_COVER_URL_SUFFIX}"
    cache_path = image_manager._get_cache_path(url)
    cached = QPixmapCache.find(str(cache_path))
    if cached:
        set_item_data(item, Qt.ItemDataRole.DecorationRole, cached)
    else:
        item.setIcon(ThemeManager.get_icon("book"))
    
    return cached is not None

async def load_item_thumbnail(path: Path, item, image_manager, meta_sem):
    """Shared async logic to extract, save, and load a comic thumbnail."""
    if path.suffix.lower() not in COMIC_EXTS:
        return

    url = f"local-archive://{path.absolute()}/{_COVER_URL_SUFFIX}"
    cache_path = image_manager._get_cache_path(url)

    # Secondary check in case it was cached while we were waiting for semaphore
    if QPixmapCache.find(str(cache_path)):
        return

    if not cache_path.exists():
        async with meta_sem:
            try:
                data = await asyncio.to_thread(read_comicbox_cover, path)
                if not data:
                    res = await asyncio.to_thread(read_archive_first_image, path)
                    if res: _, data = res
                if data:
                    await asyncio.to_thread(_save_thumbnail, data, cache_path)
            except: pass

    if cache_path.exists():
        try:
            img = await asyncio.to_thread(lambda: QImage(str(cache_path)))
            if not img.isNull():
                pixmap = QPixmap.fromImage(img)
                QPixmapCache.insert(str(cache_path), pixmap)
                set_item_data(item, Qt.ItemDataRole.DecorationRole, pixmap)
        except Exception:
            pass

from comiccatcher.ui.components.collapsible_section import CollapsibleSection

class LibrarySection(CollapsibleSection):
    def __init__(self, title: str, rows: List[Any], on_item_clicked: Callable, is_grid: bool = False, image_manager=None, meta_sem=None, show_labels=True, label_focus="series", is_folder_mode=False, config_manager=None, on_context_menu: Optional[Callable] = None, card_size="medium"):
        super().__init__(title=title, content_widget=None, is_collapsed=False, on_context_menu=on_context_menu)
        self.rows = rows
        self.on_item_clicked = on_item_clicked
        self.image_manager = image_manager
        self._meta_sem = meta_sem
        self.show_labels = show_labels
        self.card_size = card_size
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
            self.delegate = LibraryCardDelegate(self.list_widget, show_labels=self.show_labels, image_manager=self.image_manager, card_size=self.card_size)
            self.list_widget.setItemDelegate(self.delegate)
            self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
            self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
            self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            self.list_widget.viewport().installEventFilter(self)
            self.list_widget.setMovement(QListWidget.Movement.Static)
            self.list_widget.setFlow(QListWidget.Flow.LeftToRight)
            self.list_widget.setWrapping(True)
            self.list_widget.setSpacing(UIConstants.GRID_SPACING)
            self.list_widget.setIconSize(QSize(UIConstants.get_card_width(card_size), UIConstants.get_card_height(show_labels, card_size=card_size)))
            self.list_widget.itemClicked.connect(self.on_item_clicked)
        else:
            self.list_widget = BaseCardRibbon(show_labels=self.show_labels, card_size=self.card_size)
            self.model = QStandardItemModel()
            self.list_widget.setModel(self.model)
            self.delegate = LibraryCardDelegate(self.list_widget, show_labels=self.show_labels, image_manager=self.image_manager, card_size=self.card_size)
            self.list_widget.setItemDelegate(self.delegate)
            self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            self.list_widget.clicked.connect(self.on_item_clicked)

        self.list_widget.installEventFilter(self)
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
            if is_grid:
                item = QListWidgetItem()
                cached = populate_item_from_row(item, r, self.label_focus, self.is_folder_mode, self.image_manager)
                self.list_widget.addItem(item)
            else:
                item = QStandardItem()
                cached = populate_item_from_row(item, r, self.label_focus, self.is_folder_mode, self.image_manager)
                self.model.appendRow(item)

            if not cached:
                try:
                    asyncio.create_task(load_item_thumbnail(Path(r["file_path"]), item, self.image_manager, self._meta_sem))
                except RuntimeError:
                    pass

        self.toggled.connect(self._on_toggled)
        
        # Initial height calculation
        if is_grid:
            self._update_grid_height()
            # Still keep a backup timer in case width was 0 during init
            QTimer.singleShot(100, self._update_grid_height)
        else:
            self.list_widget.update_ribbon_height()

    def _on_toggled(self, is_collapsed: bool):
        if not is_collapsed:
            if self.is_grid:
                self._update_grid_height()
            else:
                self.list_widget.update_ribbon_height()

    @property
    def on_context_menu(self):
        return self.header.on_context_menu

    @on_context_menu.setter
    def on_context_menu(self, callback: Optional[Callable]):
        self.header.on_context_menu = callback

    def set_expanded(self, expanded: bool):
        logger.debug(f"LibrarySection '{self.header.header_label.text()}' set_expanded: {expanded}")
        self.set_collapsed(not expanded)



    def set_show_labels(self, enabled: bool):
        """Update label visibility and force layout/height recalculation."""
        self.show_labels = enabled
        
        # 1. Sync list_widget (Ribbon or Grid)
        if hasattr(self.list_widget, 'show_labels'):
            self.list_widget.show_labels = enabled
            
        # 2. Sync delegate
        if hasattr(self.delegate, 'show_labels'):
            self.delegate.show_labels = enabled
            
        # 3. Force re-layout of items
        self.list_widget.doItemsLayout()
        
        # 4. Recalculate heights
        if self.is_grid:
            if not self._is_collapsed:
                self._update_grid_height()
        else:
            # Ribbon height is already handled by its setter, 
            # but we force a refresh of our own container height
            if not self._is_collapsed:
                if hasattr(self.list_widget, 'update_ribbon_height'):
                    self.list_widget.update_ribbon_height()
        
        self.list_widget.viewport().update()

    def set_card_size(self, size: str):
        """Update card size for this section."""
        self.card_size = size
        
        if hasattr(self.list_widget, 'card_size'):
            self.list_widget.card_size = size

        if hasattr(self.delegate, 'card_size'):
            self.delegate.card_size = size

        if self.is_grid:
            self.list_widget.setIconSize(QSize(UIConstants.get_card_width(size), UIConstants.get_card_height(self.show_labels, card_size=size)))
            if not self._is_collapsed:
                self._update_grid_height()
            
        self.list_widget.viewport().update()
        self.list_widget.doItemsLayout()

    def reapply_theme(self):
        """Theme-aware update for section header and delegate."""
        super().reapply_theme()
        self.delegate.show_labels = self.show_labels
        self.list_widget.viewport().update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'is_grid') and self.is_grid and not self._is_collapsed:
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
        # Optimization: Use parent width if viewport width is not yet valid (0)
        # This prevents the 'cols=1' fallback which makes sections huge on initial load
        available_width = self.list_widget.viewport().width()
        if available_width <= 0:
            available_width = self.width()
        if available_width <= 0 and self.parentWidget():
            available_width = self.parentWidget().width()
            
        # If still 0, we'll have to wait for a real resize event
        if available_width <= 0:
            return

        item_w = UIConstants.get_card_width(self.card_size) + UIConstants.GRID_SPACING
        
        cols = max(1, available_width // item_w)
        rows_count = (count + cols - 1) // cols
        
        item_h = UIConstants.get_card_height(self.show_labels, card_size=self.card_size)

        target_h = rows_count * (item_h + UIConstants.GRID_SPACING) + UIConstants.GRID_SPACING
        
        if self.list_widget.height() != target_h:
            self.list_widget.setFixedHeight(target_h)

class LocalLibraryView(BaseBrowserView):
    scan_progress_signal = pyqtSignal(int, int, str)
    scan_finished_signal = pyqtSignal(bool)
    nav_changed = pyqtSignal()
    card_size_changed = pyqtSignal(str)
    show_labels_changed = pyqtSignal(bool)

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
        self._card_size = self.config_manager.get_card_size()
        
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

        # Card Sizing
        self.card_size_group = QButtonGroup(self)
        self.card_size_group.setExclusive(True)
        self.btn_card_small = self.create_header_button("card_small", "Small Cards", checkable=True)
        self.btn_card_medium = self.create_header_button("card_medium", "Medium Cards", checkable=True)
        self.btn_card_large = self.create_header_button("card_large", "Large Cards", checkable=True)
        self.card_size_group.addButton(self.btn_card_small)
        self.card_size_group.addButton(self.btn_card_medium)
        self.card_size_group.addButton(self.btn_card_large)
        
        self.btn_card_small.clicked.connect(lambda: self._on_card_size_changed("small"))
        self.btn_card_medium.clicked.connect(lambda: self._on_card_size_changed("medium"))
        self.btn_card_large.clicked.connect(lambda: self._on_card_size_changed("large"))
        
        # View Modes
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
        self.btn_group_by = self.create_header_button("group_by", "Group-by Options")
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
        self.btn_select.clicked.connect(self.toggle_bulk_selection)
        
        # Populate Left
        self.left_layout.insertWidget(0, self.btn_up)
        self.left_layout.addWidget(self.path_breadcrumb, 1) # Expanding breadcrumb on left
        
        # Populate Center (Not used in Library, center is kept empty but centered)
        
        # Standard spacing between distinct elements
        GROUP_GAP = s(12)
        
        # Populate Right
        # 1. Mode Selection (3 buttons)
        view_mode_layout = QHBoxLayout()
        view_mode_layout.setSpacing(0)
        view_mode_layout.setContentsMargins(0, 0, 0, 0)
        view_mode_layout.addWidget(self.btn_view_file)
        view_mode_layout.addWidget(self.btn_view_grid)
        view_mode_layout.addWidget(self.btn_view_group)
        self.right_layout.addLayout(view_mode_layout)
        
        self.right_layout.addSpacing(GROUP_GAP)
        
        # 2. Group Selection (Solo Dropdown)
        self.right_layout.addWidget(self.btn_group_by)
        
        self.right_layout.addSpacing(GROUP_GAP)
        
        # 3. Misc Group Toggle (Solo)
        self.right_layout.addWidget(self.btn_group_misc)
        
        self.right_layout.addSpacing(GROUP_GAP)
        
        # 4. Sort By (3 buttons)
        sort_by_layout = QHBoxLayout()
        sort_by_layout.setSpacing(0)
        sort_by_layout.setContentsMargins(0, 0, 0, 0)
        sort_by_layout.addWidget(self.btn_sort_alpha)
        sort_by_layout.addWidget(self.btn_sort_date)
        sort_by_layout.addWidget(self.btn_sort_added)
        self.right_layout.addLayout(sort_by_layout)
        
        self.right_layout.addSpacing(GROUP_GAP)
        
        # 5. Sort Order (2 buttons)
        sort_dir_layout = QHBoxLayout()
        sort_dir_layout.setSpacing(0)
        sort_dir_layout.setContentsMargins(0, 0, 0, 0)
        sort_dir_layout.addWidget(self.btn_sort_asc)
        sort_dir_layout.addWidget(self.btn_sort_desc)
        self.right_layout.addLayout(sort_dir_layout)
        
        self.right_layout.addSpacing(GROUP_GAP)
        
        # 6. Card Sizing (3 buttons)
        card_size_layout = QHBoxLayout()
        card_size_layout.setSpacing(0)
        card_size_layout.setContentsMargins(0, 0, 0, 0)
        card_size_layout.addWidget(self.btn_card_small)
        card_size_layout.addWidget(self.btn_card_medium)
        card_size_layout.addWidget(self.btn_card_large)
        self.right_layout.addLayout(card_size_layout)
        
        self.right_layout.addSpacing(GROUP_GAP)
        
        # 7. Label Toggle (Solo)
        self.right_layout.addWidget(self.btn_labels)
        
        self.right_layout.addSpacing(GROUP_GAP)
        
        # 7. Focus (2 buttons)
        label_focus_layout = QHBoxLayout()
        label_focus_layout.setSpacing(0)
        label_focus_layout.setContentsMargins(0, 0, 0, 0)
        label_focus_layout.addWidget(self.btn_focus_series)
        label_focus_layout.addWidget(self.btn_focus_title)
        self.right_layout.addLayout(label_focus_layout)
        
        self.right_layout.addSpacing(GROUP_GAP)
        
        self.right_layout.addWidget(self.btn_select)
        self.right_layout.addWidget(self.btn_refresh)
        
        self._refresh_toolbar_states()

        # Status & Progress (using base class members)
        self.scan_label = self.status_label
        self.progress = self.progress_bar
        
        # Stacked Content Area
        self.stack = QStackedWidget()
        
        # 0: Folders View
        self.list_widget = QListWidget()
        self.folders_delegate = LibraryCardDelegate(self.list_widget, show_labels=True, image_manager=self.image_manager, card_size=self._card_size)
        self.list_widget.setItemDelegate(self.folders_delegate)

        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        s = UIConstants.scale
        self.list_widget.setSpacing(s(10))
        # iconSize determines the gridding stride in IconMode. 
        # Using full card dimensions ensures proper spacing for labels and progress bars.
        self.list_widget.setIconSize(QSize(UIConstants.get_card_width(self._card_size), UIConstants.get_card_height(self._show_labels, card_size=self._card_size)))
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
        self.grouped_layout.setSpacing(UIConstants.SECTION_SPACING)
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
        self.alpha_delegate = LibraryCardDelegate(self.alpha_list, show_labels=True, image_manager=self.image_manager, card_size=self._card_size)
        self.alpha_list.setItemDelegate(self.alpha_delegate)
        s = UIConstants.scale
        self.alpha_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.alpha_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.alpha_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.alpha_list.setSpacing(s(10))
        self.alpha_list.setIconSize(QSize(UIConstants.get_card_width(self._card_size), UIConstants.get_card_height(self._show_labels, card_size=self._card_size)))
        self.alpha_list.setWordWrap(True)
        self.alpha_list.itemClicked.connect(self._on_db_item_clicked)
        self.alpha_list.itemSelectionChanged.connect(self._update_selection_ui)
        self.alpha_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.alpha_list.customContextMenuRequested.connect(lambda pos: self._on_item_context_menu(pos, self.alpha_list))
        self.stack.addWidget(self.alpha_list)

        # Selection Action Bar Configuration (using base class layout)
        
        self.btn_sel_mark_read = self.create_bulk_selection_button("Mark Read", "action_read", self._on_bulk_mark_read)
        self.btn_sel_mark_read.setEnabled(False)

        self.btn_sel_mark_unread = self.create_bulk_selection_button("Mark Unread", "action_unread", self._on_bulk_mark_unread)
        self.btn_sel_mark_unread.setEnabled(False)

        self.btn_sel_delete = self.create_bulk_selection_button("Delete Selected", "action_delete", self._on_bulk_delete)
        self.btn_sel_delete.setEnabled(False)
        
        self.selection_layout.addWidget(self.btn_sel_mark_read)
        self.selection_layout.addWidget(self.btn_sel_mark_unread)
        self.selection_layout.addWidget(self.btn_sel_delete)

        self.add_content_widget(self.stack)

        self.list_widget.installEventFilter(self)
        self.alpha_list.installEventFilter(self)

        self._is_dirty = True # Flag for initial load in showEvent

        self.refresh_keyboard_navigation()

    def toggle_bulk_selection(self, enabled: Optional[bool] = None):
        if enabled is None:
            enabled = not self._bulk_selection_mode
            
        super().toggle_bulk_selection(enabled)
        
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
        self.refresh_keyboard_navigation()

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
        if not self._bulk_selection_mode: return
        
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
        self.label_sel_count.setText(f"{count} item{'s' if count != 1 else ''}")
        self.btn_sel_delete.setEnabled(count > 0)
        self.btn_sel_delete.setText("Delete")
        self.btn_sel_mark_read.setEnabled(count > 0)
        self.btn_sel_mark_unread.setEnabled(count > 0)

        # Refresh icon colors for visual feedback
        for btn in [self.btn_sel_delete, self.btn_sel_mark_read, self.btn_sel_mark_unread]:
            icon_name = self._bulk_selection_buttons.get(btn)
            if icon_name:
                btn.setIcon(ThemeManager.get_icon(icon_name, "accent" if count > 0 else "text_dim"))

    def keyboard_trigger_bulk_action(self):
        """Perform bulk delete for selection mode."""
        self._on_bulk_delete()

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
            self.toggle_bulk_selection(False)
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
            
        self.toggle_bulk_selection(False)
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
            
        self.toggle_bulk_selection(False)
        self._reload_current_view()

    def _save_cover_to_cache(self, path: Path, cover_bytes: bytes) -> None:
        """Called from scanner worker thread to save a resized thumbnail to disk cache."""
        url = f"local-archive://{path.absolute()}/{_COVER_URL_SUFFIX}"
        cache_path = self.image_manager._get_cache_path(url)
        if not cache_path.exists():
            _save_thumbnail(cover_bytes, cache_path)

    def cycle_display_mode(self):
        """Cycle through display modes: Folders -> Grouped -> Grid."""
        modes = ["file", "grouped", "grid"]
        current_mode = self.config_manager.get_library_display_mode()
        try:
            curr_idx = modes.index(current_mode)
            next_mode = modes[(curr_idx + 1) % len(modes)]
            self._on_display_mode_changed(next_mode)
        except ValueError:
            self._on_display_mode_changed("file")

    def get_help_popover_title(self):
        return "Library Controls"

    def get_help_popover_sections(self):
        sections = super().get_help_popover_sections()
        
        # Customize descriptions for Library
        for title, rows in sections:
            if title == "VIEW CONTROLS":
                # Update P description for library modes
                for i, (key, desc) in enumerate(rows):
                    if key == "P":
                        rows[i] = ("P", "Cycle layout (Folders, Grouped, Grid)")
                
                # Add grouping shortcut
                rows.append(("G", "Cycle grouping mode (Series, Year, etc.)"))
                break
                
        return sections

    def toggle_labels(self, enabled: bool):
        """Toggle label visibility for cards."""
        self.btn_labels.setChecked(enabled)
        self._on_show_labels_changed(enabled)

    def _on_show_labels_changed(self, checked):
        if self._show_labels == checked: return
        self._show_labels = checked
        self.config_manager.set_show_labels(self._show_labels)
        
        # 1. Update delegates for non-grouped views and force layout
        self.alpha_delegate.show_labels = self._show_labels
        self.folders_delegate.show_labels = self._show_labels
        
        self.alpha_list.doItemsLayout()
        self.list_widget.doItemsLayout()
        
        # 2. Update all active grouped sections
        for i in range(self.grouped_layout.count()):
            item = self.grouped_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), LibrarySection):
                section = item.widget()
                section.set_show_labels(checked)
        
        # 3. Trigger immediate repaint across all viewports
        self.show_labels_changed.emit(checked)
        self.reapply_theme()
        self.list_widget.viewport().update()
        self.alpha_list.viewport().update()
        self.grouped_scroll.viewport().update()
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

        # 2. Style Segmented Groups (structural styling)
        if hasattr(self, "btn_view_file"):
            self._style_segmented_group([self.btn_view_file, self.btn_view_grid, self.btn_view_group])

        if hasattr(self, "btn_card_medium"):
            self._style_segmented_group([self.btn_card_medium, self.btn_card_large])

        if hasattr(self, "btn_labels"):
            self._style_segmented_group([self.btn_labels])
            
        if hasattr(self, "btn_focus_series"):
            self._style_segmented_group([self.btn_focus_series, self.btn_focus_title])
            
        if hasattr(self, "btn_sort_asc") and hasattr(self, "btn_sort_desc"):
            self._style_segmented_group([self.btn_sort_asc, self.btn_sort_desc])
            
        if hasattr(self, "btn_sort_alpha"):
            self._style_segmented_group([self.btn_sort_alpha, self.btn_sort_date, self.btn_sort_added])
            
        if hasattr(self, "btn_group_misc"):
            self._style_segmented_group([self.btn_group_misc])

        if hasattr(self, "btn_group_by"):
            self._style_segmented_group([self.btn_group_by])

        # 3. Sync State (Final icons and checked states)
        self._refresh_toolbar_states()

        # 4. Content Area Styling
        list_style = "QListView::item:selected { background: transparent; border: none; }"
        if hasattr(self, "alpha_list"): self.alpha_list.setStyleSheet(list_style)
        if hasattr(self, "list_widget"): self.list_widget.setStyleSheet(list_style)
        
        if hasattr(self, "grouped_scroll"):
            self.grouped_scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        if hasattr(self, "grouped_container"):
            self.grouped_container.setStyleSheet(f"background-color: {theme['bg_main']};")

        # 5. Propagate to sub-sections
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

    def _on_card_size_changed(self, size: str):
        if self._card_size == size: return
        self._card_size = size
        self.config_manager.set_card_size(size)

        # 1. Update own delegates
        if hasattr(self, 'folders_delegate'):
            self.folders_delegate.card_size = size
        if hasattr(self, 'alpha_delegate'):
            self.alpha_delegate.card_size = size

        # 2. Update child sections in grouped view
        if hasattr(self, "grouped_layout"):
            for i in range(self.grouped_layout.count()):
                item = self.grouped_layout.itemAt(i)
                if item and item.widget() and hasattr(item.widget(), 'set_card_size'):
                    item.widget().set_card_size(size)

        # 3. Sync icon sizes for top-level list widgets
        icon_size = QSize(UIConstants.get_card_width(size), UIConstants.get_card_height(self._show_labels, card_size=size))
        if hasattr(self, 'list_widget'):
            self.list_widget.setIconSize(icon_size)
        if hasattr(self, 'alpha_list'):
            self.alpha_list.setIconSize(icon_size)

        # 4. Refresh display
        self.card_size_changed.emit(size)
        self._refresh_toolbar_states()
        
        # Trigger layout rebuild for currently visible mode
        self._reload_current_view()

    def _refresh_toolbar_states(self):
        if not hasattr(self, "btn_view_file"): return

        # 1. Navigation & Actions
        self.btn_up.setIcon(ThemeManager.get_icon("back", "text_dim"))
        self.btn_refresh.setIcon(ThemeManager.get_icon("refresh", "text_dim"))

        # 2. View Modes
        mode = self.config_manager.get_library_display_mode()
        self.btn_view_file.setChecked(mode == "file")
        self.btn_view_grid.setChecked(mode == "grid")
        self.btn_view_group.setChecked(mode == "grouped")
        
        self.btn_view_file.setIcon(ThemeManager.get_icon("view_file", "accent" if mode == "file" else "text_dim"))
        self.btn_view_grid.setIcon(ThemeManager.get_icon("view_grid", "accent" if mode == "grid" else "text_dim"))
        self.btn_view_group.setIcon(ThemeManager.get_icon("view_group", "accent" if mode == "grouped" else "text_dim"))

        # 3. Card Size
        small = self._card_size == "small"
        medium = self._card_size == "medium"
        large = self._card_size == "large"
        
        self.btn_card_small.setChecked(small)
        self.btn_card_medium.setChecked(medium)
        self.btn_card_large.setChecked(large)
        
        self.btn_card_small.setIcon(ThemeManager.get_icon("card_small", "accent" if small else "text_dim"))
        self.btn_card_medium.setIcon(ThemeManager.get_icon("card_medium", "accent" if medium else "text_dim"))
        self.btn_card_large.setIcon(ThemeManager.get_icon("card_large", "accent" if large else "text_dim"))

        # 4. Labels
        self.btn_labels.setChecked(self._show_labels)        
        self.btn_labels.setIcon(ThemeManager.get_icon("label", "accent" if self._show_labels else "text_dim"))
        
        # 5. Label Focus
        focus = self.config_manager.get_library_label_focus()
        self.btn_focus_series.setChecked(focus == "series")
        self.btn_focus_title.setChecked(focus == "title")
        self.btn_focus_series.setIcon(ThemeManager.get_icon("focus_series", "accent" if focus == "series" else "text_dim"))
        self.btn_focus_title.setIcon(ThemeManager.get_icon("focus_title", "accent" if focus == "title" else "text_dim"))
        
        # 6. Sort Direction
        sort_dir = self.config_manager.get_library_sort_direction()
        self.btn_sort_asc.setChecked(sort_dir == "asc")
        self.btn_sort_desc.setChecked(sort_dir == "desc")
        self.btn_sort_asc.setIcon(ThemeManager.get_icon("sort_asc", "accent" if sort_dir == "asc" else "text_dim"))
        self.btn_sort_desc.setIcon(ThemeManager.get_icon("sort_desc", "accent" if sort_dir == "desc" else "text_dim"))
        
        # 7. Sort Order
        order = self.config_manager.get_library_sort_order()
        self.btn_sort_alpha.setChecked(order == "alpha")
        self.btn_sort_date.setChecked(order == "pub_date")
        self.btn_sort_added.setChecked(order == "added_date")
        self.btn_sort_alpha.setIcon(ThemeManager.get_icon("sort_alpha", "accent" if order == "alpha" else "text_dim"))
        self.btn_sort_date.setIcon(ThemeManager.get_icon("sort_date", "accent" if order == "pub_date" else "text_dim"))
        self.btn_sort_added.setIcon(ThemeManager.get_icon("sort_added", "accent" if order == "added_date" else "text_dim"))
        
        # 8. Grouping
        self.btn_group_misc.setEnabled(mode == "grouped")
        group_misc = self.config_manager.get_library_group_misc()
        self.btn_group_misc.setChecked(group_misc)
        self.btn_group_misc.setIcon(ThemeManager.get_icon("group_misc", "accent" if group_misc else "text_dim"))
        
        self.btn_group_by.setEnabled(mode == "grouped")
        self.btn_group_by.setIcon(ThemeManager.get_icon("group_by", "accent" if mode == "grouped" else "text_dim"))
        self._build_group_by_menu()

        # 9. Selection mode
        if hasattr(self, "btn_select"):
            self.btn_select.setChecked(self._bulk_selection_mode)
            self.btn_select.setIcon(ThemeManager.get_icon("select", "accent" if self._bulk_selection_mode else "text_dim"))

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

    def cycle_group_by(self):
        """Cycle through group-by options: Series -> Publisher -> Writer -> Artist."""
        modes = ["series", "publisher", "writer", "artist"]
        current = self.config_manager.get_library_group_by()
        try:
            idx = modes.index(current)
            next_mode = modes[(idx + 1) % len(modes)]
            self._on_group_by_changed(next_mode)
        except ValueError:
            self._on_group_by_changed("series")
        
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
        self.clear_keyboard_cursor()
        
        self.setUpdatesEnabled(False)
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
            self.setUpdatesEnabled(True)
            self.refresh_keyboard_navigation()
            self.setFocus()


    def refresh_and_scan(self):
        old_root = getattr(self, "root_dir", None)
        self.root_dir = self.config_manager.get_library_dir()
        
        # Ensure current_dir is updated to the new root if the library path changed
        if old_root and old_root != self.root_dir:
            self.current_dir = self.root_dir
        elif not self.current_dir or not self.current_dir.exists() or not str(self.current_dir).startswith(str(self.root_dir)):
            self.current_dir = self.root_dir

        self.scanner.library_dir = self.root_dir
        # 1. Load from DB immediately
        self._reload_current_view()
        # 2. Start scan in background
        if not self.scanner.is_scanning:
            asyncio.create_task(self.scanner.scan())

    def set_dirty(self):
        self._is_dirty = True
        if self.isVisible():
            self.refresh_and_scan()

    def recalculate_heights(self):
        """Forces all child library sections to update their grid heights."""
        # Calculate scrollbar width for header margins
        sb = self.grouped_scroll.verticalScrollBar()
        sb_width = sb.width() if sb.isVisible() else 0
        header_margin = sb_width + UIConstants.scale(10)

        for i in range(self.grouped_layout.count()):
            item = self.grouped_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), LibrarySection):
                section = item.widget()
                section.set_right_margin(header_margin)
                if section.is_grid and not section._is_collapsed:
                    section._update_grid_height()

    def showEvent(self, event):
        super().showEvent(event)
        # Always recalculate heights on show to fix viewport width mismatch issues
        self.recalculate_heights()
        
        if self._is_dirty:
            self._is_dirty = False
            self.refresh_and_scan()

    def refresh(self):
        self.toggle_bulk_selection(False)
        old_root = getattr(self, "root_dir", None)
        self.root_dir = self.config_manager.get_library_dir()
        
        # If the root itself changed, we reset navigation to the new root
        if old_root and old_root != self.root_dir:
            self.current_dir = self.root_dir
        elif not self.current_dir or not self.current_dir.exists() or not str(self.current_dir).startswith(str(self.root_dir)):
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
                    self.list_widget.addItem(item)
                else:
                    row = dir_rows.get(str(entry.path.absolute()))
                    if row:
                        r = dict(row)
                    else:
                        r = {"file_path": str(entry.path), "title": entry.path.stem}
                    
                    item = QListWidgetItem()
                    cached = populate_item_from_row(item, r, label_focus, True, self.image_manager)
                    self.list_widget.addItem(item)
                    
                    if not cached:
                        try:
                            asyncio.create_task(load_item_thumbnail(entry.path, item, self.image_manager, self._meta_sem))
                        except RuntimeError:
                            pass

        finally:
            self.list_widget.setUpdatesEnabled(True)
            self.refresh_keyboard_navigation()

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
                expansion_states[s.header.header_label.text()] = s.list_widget.isVisible()

        # 1. Fetch data from DB FIRST
        grouped = await asyncio.to_thread(self.db.get_comics_grouped, group_by, sort_order, sort_dir)
        label_focus = self.config_manager.get_library_label_focus()

        # 2. Suspend updates and clear ONLY right before rebuilding
        self.setUpdatesEnabled(False)
        try:
            # Clear all widgets except the permanent spacer
            while self.grouped_layout.count() > 1:
                item = self.grouped_layout.takeAt(0)
                if item and item.widget():
                    w = item.widget()
                    w.hide() # Hide immediately to reduce visual artifacts
                    w.deleteLater()

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
                section = LibrarySection(title, rows, self._on_db_item_clicked, is_grid=False, image_manager=self.image_manager, meta_sem=self._meta_sem, show_labels=self._show_labels, label_focus=label_focus, is_folder_mode=is_file_mode, config_manager=self.config_manager, card_size=self._card_size)
                section.on_context_menu = lambda pos, s=section: self._on_group_context_menu(pos, s)

                # Restore expansion state
                if title in expansion_states:
                    section.set_expanded(expansion_states[title])

                if section.is_grid:
                    section.list_widget.itemSelectionChanged.connect(self._update_selection_ui)
                else:
                    section.list_widget.selectionModel().selectionChanged.connect(self._update_selection_ui)

                if self._bulk_selection_mode:
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

                section = LibrarySection(title, one_offs, self._on_db_item_clicked, is_grid=True, image_manager=self.image_manager, meta_sem=self._meta_sem, show_labels=self._show_labels, label_focus=label_focus, is_folder_mode=is_file_mode, config_manager=self.config_manager, card_size=self._card_size)
                section.on_context_menu = lambda pos, s=section: self._on_group_context_menu(pos, s)

                # Restore expansion state
                if title in expansion_states:
                    section.set_expanded(expansion_states[title])

                if section.is_grid:
                    section.list_widget.itemSelectionChanged.connect(self._update_selection_ui)
                else:
                    section.list_widget.selectionModel().selectionChanged.connect(self._update_selection_ui)

                if self._bulk_selection_mode:
                    section.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)

                section.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                section.list_widget.customContextMenuRequested.connect(lambda pos, w=section.list_widget: self._on_item_context_menu(pos, w))

                # Insert before the spacer
                self.grouped_layout.insertWidget(self.grouped_layout.count() - 1, section)

        finally:
            self.setUpdatesEnabled(True)
            self.refresh_keyboard_navigation()

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
                item = QListWidgetItem()
                cached = populate_item_from_row(item, r, label_focus, is_file_mode, self.image_manager)
                self.alpha_list.addItem(item)
                
                if not cached:
                    try:
                        asyncio.create_task(load_item_thumbnail(Path(r["file_path"]), item, self.image_manager, self._meta_sem))
                    except RuntimeError:
                        pass
        finally:
            self.alpha_list.setUpdatesEnabled(True)
            self.refresh_keyboard_navigation()

    def _on_folder_item_clicked(self, item):
        if self._bulk_selection_mode:
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
        if self._bulk_selection_mode:
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

    def get_keyboard_nav_views(self):
        if not hasattr(self, "stack"):
            return []
        current = self.stack.currentIndex()
        if current == 0:
            return [self.list_widget]
        if current == 2:
            return [self.alpha_list]
        if current == 1:
            views = []
            for i in range(self.grouped_layout.count()):
                item = self.grouped_layout.itemAt(i)
                if item and item.widget() and isinstance(item.widget(), LibrarySection):
                    section = item.widget()
                    # Always include the list_widget so the Navigator can install filters,
                    # even if it's currently hidden (it will be visible soon).
                    views.append(section.list_widget)
            return views
        return []

    def get_keyboard_nav_focus_objects(self):
        objs = []
        if hasattr(self, "stack"):
            objs.append(self.stack)
        if hasattr(self, "grouped_scroll"):
            objs.extend([
                self.grouped_scroll,
                self.grouped_scroll.viewport(),
                self.grouped_container,
            ])
        return objs

    def get_keyboard_nav_scrollbar(self):
        current = self.stack.currentIndex() if hasattr(self, "stack") else 0
        if current == 1:
            return self.grouped_scroll.verticalScrollBar()
        if current == 2:
            return self.alpha_list.verticalScrollBar()
        return self.list_widget.verticalScrollBar()

    def keyboard_activate_index(self, view, index):
        if isinstance(view, QListWidget):
            item = view.item(index.row())
            if item:
                if view is self.list_widget:
                    self._on_folder_item_clicked(item)
                else:
                    self._on_db_item_clicked(item)
        else:
            self._on_db_item_clicked(index)

    def keyboard_context_menu_for_index(self, view, index):
        rect = view.visualRect(index)
        if not rect.isValid():
            return
        self._on_item_context_menu(rect.center(), view, allow_in_selection=True)

    def _on_item_context_menu(self, pos, list_widget, allow_in_selection: bool = False):
        if self._bulk_selection_mode and not allow_in_selection:
            return
        
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
        
        # Gather context paths for navigation
        context_paths = []
        if isinstance(list_widget, QListWidget):
            for i in range(list_widget.count()):
                p = list_widget.item(i).data(Qt.ItemDataRole.UserRole)
                if isinstance(p, Path) and not p.is_dir():
                    context_paths.append(p)
        else:
            model = list_widget.model()
            if model:
                for i in range(model.rowCount()):
                    p = model.index(i, 0).data(Qt.ItemDataRole.UserRole)
                    if isinstance(p, Path) and not p.is_dir():
                        context_paths.append(p)

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
        # 1. Details Action
        if file_path:
            p = Path(file_path)
            self.detail_popover.add_action("eye", "Details", lambda: self.on_open_comic(p, context_paths))

        # 2. Select Action
        def do_select():
            # Find index of this item in current list
            if isinstance(list_widget, QListWidget):
                list_widget.setCurrentItem(item)
            else:
                list_widget.setCurrentIndex(idx)
            
            # This logic should mimic single item selection in current view
            # If not in selection mode, enter it and select this one
            if not self._bulk_selection_mode:
                self.toggle_bulk_selection(True)
            
            # Selection might need to be explicit if toggle_bulk_selection clears it
            if isinstance(list_widget, QListWidget):
                item.setSelected(True)
            else:
                list_widget.selectionModel().select(idx, QItemSelectionModel.SelectionFlag.Select)

        self.detail_popover.add_action("select", "Select", do_select)

        if file_path:
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
            "summary": meta.get("summary") or meta.get("description"),
            "web": meta.get("web"),
            "manga": meta.get("manga"),
            "notes": meta.get("notes"),
            "imprint": meta.get("imprint"),
            "genre": meta.get("genre")
        }
        
        label_focus = self.config_manager.get_library_label_focus()
        primary, secondary = generate_comic_labels(meta, label_focus)
        
        self.detail_popover.populate(data=data, title=primary, subtitle=secondary)
        
        # Standardized Positioning
        arg = item if isinstance(list_widget, QListWidget) else idx
        from comiccatcher.ui.view_helpers import ViewportHelper
        ViewportHelper.position_popover(self.detail_popover, list_widget, arg)

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
