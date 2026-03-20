import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QProgressBar, QComboBox, QStackedWidget,
    QScrollArea, QApplication, QStyledItemDelegate, QStyle,
    QAbstractItemView
)
from PyQt6.QtCore import Qt, QSize, pyqtSlot, pyqtSignal, QRect
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QBrush, QPen, QImage, QPixmapCache, QKeyEvent

from config import ConfigManager, CONFIG_DIR
from logger import get_logger
from api.image_manager import ImageManager
from ui.local_archive import read_first_image
from ui.local_comicbox import flatten_comicbox, read_comicbox_dict, subtitle_from_flat, read_comicbox_cover
from ui.theme_manager import ThemeManager
from api.local_db import LocalLibraryDB
from api.library_scanner import LibraryScanner

logger = get_logger("ui.library")

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

class ComicDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, show_labels=True):
        super().__init__(parent)
        self.show_labels = show_labels

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Get data
        file_path = index.data(Qt.ItemDataRole.UserRole)
        pixmap = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(pixmap, QIcon):
            pixmap = pixmap.pixmap(option.decorationSize)
            
        progress_data = index.data(Qt.ItemDataRole.UserRole + 1) # (current, total)
        # Ensure progress_data is a tuple of ints
        curr_page, total_pages = 0, 0
        if isinstance(progress_data, (list, tuple)) and len(progress_data) >= 2:
            curr_page = progress_data[0] or 0
            total_pages = progress_data[1] or 0
        
        rect = option.rect
        
        # Draw background if selected
        if option.state & QStyle.StateFlag.State_Selected:
            # We can use the accent color from the palette
            painter.fillRect(rect, option.palette.highlight().color().lighter(160))

        # Icon rect
        icon_rect = QRect(rect.left() + (rect.width() - option.decorationSize.width()) // 2,
                          rect.top() + 5,
                          option.decorationSize.width(),
                          option.decorationSize.height())

        if pixmap and not pixmap.isNull():
            # If read to the end, reduce color (desaturate or dim)
            if total_pages > 0 and curr_page >= total_pages - 1:
                # Dim it
                painter.setOpacity(0.5)
                painter.drawPixmap(icon_rect, pixmap)
                painter.setOpacity(1.0)
            else:
                painter.drawPixmap(icon_rect, pixmap)
            
            # Progress bar just BELOW the cover
            if total_pages > 0 and curr_page > 0:
                prog_pct = curr_page / total_pages
                bar_h = 3
                bar_rect = QRect(icon_rect.left() + 2, icon_rect.bottom() + 2, icon_rect.width() - 4, bar_h)
                
                # Background
                painter.fillRect(bar_rect, QColor(0, 0, 0, 50))
                # Progress
                painter.fillRect(QRect(bar_rect.left(), bar_rect.top(), int(bar_rect.width() * prog_pct), bar_h), option.palette.highlight().color())

        # Label
        if self.show_labels:
            text = index.data(Qt.ItemDataRole.DisplayRole)
            if text:
                # Move text slightly lower to accommodate progress bar
                text_rect = QRect(rect.left(), icon_rect.bottom() + 8, rect.width(), rect.bottom() - icon_rect.bottom() - 8)
                painter.setPen(option.palette.text().color())
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)

        painter.restore()

    def sizeHint(self, option, index):
        base_size = option.decorationSize
        if self.show_labels:
            return QSize(base_size.width() + 20, base_size.height() + 45)
        return QSize(base_size.width() + 10, base_size.height() + 20)

@dataclass(frozen=True)
class LibraryEntry:
    path: Path
    is_dir: bool

    @property
    def name(self) -> str:
        return self.path.name

def _list_dir(path: Path) -> List[LibraryEntry]:
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

    entries.sort(key=lambda e: (not e.is_dir, e.name.lower()))
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

class SeriesSection(QWidget):
    def __init__(self, title: str, rows: List[Any], on_item_clicked: Callable, is_grid: bool = False, image_manager=None, meta_sem=None, show_labels=True):
        super().__init__()
        self.rows = rows
        self.on_item_clicked = on_item_clicked
        self.image_manager = image_manager
        self._meta_sem = meta_sem
        self.show_labels = show_labels
        self.is_grid = is_grid
        
        self.setObjectName("series_section")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 10) # Less margin
        layout.setSpacing(0)

        self.btn_toggle = QPushButton(f"▼ {title.upper()}")
        self.btn_toggle.setFlat(True)
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.setObjectName("section_toggle")
        
        layout.addWidget(self.btn_toggle)
        
        self.list_widget = QListWidget()
        self.list_widget.setMouseTracking(True)
        self.delegate = ComicDelegate(self.list_widget, show_labels=self.show_labels)
        self.list_widget.setItemDelegate(self.delegate)
        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.itemDoubleClicked.connect(self.on_item_clicked)
        
        icon_w, icon_h = 120, 180
        self.list_widget.setIconSize(QSize(icon_w, icon_h))
        
        if is_grid:
            self.list_widget.setMovement(QListWidget.Movement.Static)
            self.list_widget.setFlow(QListWidget.Flow.LeftToRight)
            self.list_widget.setWrapping(True)
            self.list_widget.setSpacing(10)
        else:
            self.list_widget.setFlow(QListWidget.Flow.LeftToRight)
            self.list_widget.setWrapping(False)
            h = icon_h + (45 if self.show_labels else 20)
            self.list_widget.setFixedHeight(h + 15)
            self.list_widget.setSpacing(10)
            self.list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            
        for row in rows:
            r = dict(row)
            title_text = r.get("title") or Path(r["file_path"]).name
            item = QListWidgetItem(title_text if self.show_labels else "")
            item.setData(Qt.ItemDataRole.UserRole, Path(r["file_path"]))
            # Store progress
            item.setData(Qt.ItemDataRole.UserRole + 1, (r.get("current_page") or 0, r.get("page_count") or 0))
            
            item.setIcon(ThemeManager.get_icon("book"))
            item.setToolTip(f"{r.get('series') or 'Other'} - {title_text}")
            self.list_widget.addItem(item)
            try:
                asyncio.create_task(self._load_thumb(Path(r["file_path"]), item))
            except RuntimeError:
                pass
            
        layout.addWidget(self.list_widget)
        self.btn_toggle.clicked.connect(self.toggle)

    def toggle(self):
        visible = not self.list_widget.isVisible()
        self.list_widget.setVisible(visible)
        text = self.btn_toggle.text()
        if visible:
            self.btn_toggle.setText(text.replace("▶", "▼"))
        else:
            self.btn_toggle.setText(text.replace("▼", "▶"))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'is_grid') and self.is_grid:
            self._update_grid_height()

    def _update_grid_height(self):
        count = self.list_widget.count()
        if count == 0:
            return
            
        available_width = self.list_widget.viewport().width()
        item_w = 120 + (20 if self.show_labels else 10) + 10 # Width + spacing
        
        cols = max(1, available_width // item_w)
        rows_count = (count + cols - 1) // cols
        
        item_h = 180 + (45 if self.show_labels else 20)
        self.list_widget.setFixedHeight(rows_count * (item_h + 10) + 20)

    async def _load_thumb(self, path: Path, item: QListWidgetItem):
        if path.suffix.lower() in (".cbz", ".cbr", ".cb7"):
            url = f"local-cbz://{path.absolute()}/{_COVER_URL_SUFFIX}"
            cache_path = self.image_manager._get_cache_path(url)

            pixmap = QPixmapCache.find(str(cache_path))
            if pixmap:
                item.setData(Qt.ItemDataRole.DecorationRole, pixmap)
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
                        item.setData(Qt.ItemDataRole.DecorationRole, pixmap)
                except Exception:
                    pass

class LocalLibraryView(QWidget):
    scan_progress_signal = pyqtSignal(int, int, str)
    scan_finished_signal = pyqtSignal(bool)

    def __init__(
        self,
        config_manager: ConfigManager,
        on_open_comic: Callable[[Path], None],
        local_db: Optional[LocalLibraryDB] = None,
    ):
        super().__init__()
        self.config_manager = config_manager
        self.on_open_comic = on_open_comic
        self.db = local_db or LocalLibraryDB(CONFIG_DIR / "library.db")

        self.root_dir = self.config_manager.get_library_dir()
        self.current_dir = self.root_dir
        self.image_manager = ImageManager(None)
        self._meta_sem = asyncio.Semaphore(4)
        self._is_dirty = False
        
        # Restore preferences
        self._show_labels = self.config_manager.get_show_labels()
        initial_view_mode = self.config_manager.get_library_view_mode()
        
        last_folder = self.config_manager.get_last_folder_path()
        if last_folder and Path(last_folder).exists() and str(last_folder).startswith(str(self.root_dir)):
            self.current_dir = Path(last_folder)
        else:
            self.current_dir = self.root_dir
        
        # Init Scanner
        self.scanner = LibraryScanner(self.db, self.root_dir, on_cover=self._save_cover_to_cache)
        self.scanner.on_progress = lambda c, t, m: self.scan_progress_signal.emit(c, t, m)
        self.scanner.on_finished = lambda changed: self.scan_finished_signal.emit(changed)
        
        self.scan_progress_signal.connect(self._on_scan_progress_ui)
        self.scan_finished_signal.connect(self._on_scan_finished_ui)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)

        # Header
        self.header_layout = QHBoxLayout()
        
        self.btn_up = QPushButton()
        self.btn_up.setProperty("flat", "true")
        self.btn_up.setIcon(ThemeManager.get_icon("back"))
        self.btn_up.setFixedSize(32, 32)
        self.btn_up.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_up.clicked.connect(self._go_up)
        self.btn_up.setToolTip("Go up one folder")
        
        self.btn_refresh = QPushButton()
        self.btn_refresh.setProperty("flat", "true")
        self.btn_refresh.setIcon(ThemeManager.get_icon("refresh"))
        self.btn_refresh.setFixedSize(32, 32)
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.refresh_and_scan)
        self.btn_refresh.setToolTip("Scan for changes")
        
        # View Options Menu Button
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction, QActionGroup
        
        self.btn_view_options = QPushButton()
        self.btn_view_options.setProperty("flat", "true")
        self.btn_view_options.setIcon(ThemeManager.get_icon("settings")) # Using settings icon for view options
        self.btn_view_options.setFixedSize(32, 32)
        self.btn_view_options.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_view_options.setToolTip("View options")
        
        self.view_menu = QMenu(self)
        
        # View Mode Group
        mode_group = QActionGroup(self)
        modes = ["Folders", "Grouped (Series)", "Alphabetical", "Publisher", "Writer", "Creator"]
        for i, mode_name in enumerate(modes):
            action = QAction(mode_name, self, checkable=True)
            action.setChecked(i == initial_view_mode)
            action.setData(i)
            action.triggered.connect(lambda _, idx=i: self._on_view_mode_changed(idx))
            self.view_menu.addAction(action)
            mode_group.addAction(action)
        
        self.view_menu.addSeparator()
        
        # Label Toggle
        self.action_show_labels = QAction("Show Labels", self, checkable=True)
        self.action_show_labels.setChecked(self._show_labels)
        self.action_show_labels.triggered.connect(self._on_show_labels_changed)
        self.view_menu.addAction(self.action_show_labels)
        
        self.btn_view_options.setMenu(self.view_menu)

        self.path_label = QLabel("")
        self.path_label.setObjectName("path_label")
        
        self.btn_select = QPushButton("Select")
        self.btn_select.setCheckable(True)
        self.btn_select.clicked.connect(self.toggle_selection_mode)
        
        self.header_layout.addWidget(self.btn_up)
        self.header_layout.addWidget(self.path_label, 1)
        self.header_layout.addWidget(self.btn_select)
        self.header_layout.addWidget(self.btn_refresh)
        self.header_layout.addWidget(self.btn_view_options)
        self.layout.addLayout(self.header_layout)

        # Progress bar & Scan label
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(4)
        self.layout.addWidget(self.progress)
        
        self.scan_label = QLabel("")
        self.scan_label.setObjectName("scan_label")
        self.scan_label.setVisible(False)
        self.layout.addWidget(self.scan_label)

        # Stacked Widget for Views
        self.stack = QStackedWidget()
        self.layout.addWidget(self.stack)
        
        # 0: Folders View
        self.list_widget = QListWidget()
        self.folders_delegate = ComicDelegate(self.list_widget, show_labels=True)
        self.list_widget.setItemDelegate(self.folders_delegate)
        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.setSpacing(10)
        self.list_widget.setIconSize(QSize(120, 180))
        self.list_widget.itemDoubleClicked.connect(self._on_folder_item_double_clicked)
        self.list_widget.itemClicked.connect(self._on_item_clicked_override)
        self.list_widget.itemSelectionChanged.connect(self._update_selection_ui)
        self.stack.addWidget(self.list_widget)
        
        # 1: Grouped View (Series)
        self.grouped_scroll = QScrollArea()
        self.grouped_scroll.setWidgetResizable(True)
        self.grouped_container = QWidget()
        self.grouped_layout = QVBoxLayout(self.grouped_container)
        self.grouped_layout.setContentsMargins(0, 0, 0, 0)
        self.grouped_layout.setSpacing(5)
        self.grouped_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.grouped_scroll.setWidget(self.grouped_container)
        self.stack.addWidget(self.grouped_scroll)
        
        # 2: Alphabetical View
        self.alpha_list = QListWidget()
        self.alpha_delegate = ComicDelegate(self.alpha_list, show_labels=True)
        self.alpha_list.setItemDelegate(self.alpha_delegate)
        self.alpha_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.alpha_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.alpha_list.setSpacing(10)
        self.alpha_list.setIconSize(QSize(120, 180))
        self.alpha_list.setWordWrap(True)
        self.alpha_list.itemDoubleClicked.connect(self._on_db_item_double_clicked)
        self.alpha_list.itemClicked.connect(self._on_item_clicked_override)
        self.alpha_list.itemSelectionChanged.connect(self._update_selection_ui)
        self.stack.addWidget(self.alpha_list)

        # Selection Action Bar
        self.selection_bar = QWidget()
        self.selection_bar.setObjectName("top_header")
        self.selection_bar.setFixedHeight(50)
        sel_layout = QHBoxLayout(self.selection_bar)
        
        self.btn_sel_cancel = QPushButton("Cancel")
        self.btn_sel_cancel.clicked.connect(lambda: self.toggle_selection_mode(False))
        self.label_sel_count = QLabel("0 items selected")
        self.label_sel_count.setStyleSheet("font-weight: bold;")
        self.btn_sel_action = QPushButton("Delete Selected")
        self.btn_sel_action.setObjectName("primary_button")
        self.btn_sel_action.setStyleSheet("background-color: #d32f2f; color: white; border-color: #b71c1c;") # Make it red for delete
        self.btn_sel_action.clicked.connect(self._on_bulk_delete)
        self.btn_sel_action.setEnabled(False)
        
        sel_layout.addWidget(self.btn_sel_cancel)
        sel_layout.addStretch()
        sel_layout.addWidget(self.label_sel_count)
        sel_layout.addStretch()
        sel_layout.addWidget(self.btn_sel_action)
        
        self.selection_bar.setVisible(False)
        self.layout.addWidget(self.selection_bar)
        
        self._selection_mode = False

        self.refresh()
        # Initial scan is triggered by refresh_and_scan() logic if needed
        # self.refresh() above calls _reload_current_view() which loads from DB immediately.
        # We also want to trigger a scan on startup to pick up new files.
        if not self.scanner.is_scanning:
            asyncio.create_task(self.scanner.scan())

    def toggle_selection_mode(self, enabled: Optional[bool] = None):
        if enabled is None:
            enabled = not self._selection_mode
            
        self._selection_mode = enabled
        self.btn_select.setChecked(enabled)
        self.btn_select.setText("Done" if enabled else "Select")
        self.selection_bar.setVisible(enabled)
        
        mode = QAbstractItemView.SelectionMode.MultiSelection if enabled else QAbstractItemView.SelectionMode.SingleSelection
        self.list_widget.setSelectionMode(mode)
        self.alpha_list.setSelectionMode(mode)
        
        # Also update all SeriesSections in grouped view
        for i in range(self.grouped_layout.count()):
            item = self.grouped_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), SeriesSection):
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

    def _on_item_clicked_override(self, item):
        pass

    def _get_all_selected_items(self):
        selected_items = []
        if self.stack.currentIndex() == 0:
            selected_items.extend(self.list_widget.selectedItems())
        elif self.stack.currentIndex() == 2:
            selected_items.extend(self.alpha_list.selectedItems())
        elif self.stack.currentIndex() == 1:
            for i in range(self.grouped_layout.count()):
                item = self.grouped_layout.itemAt(i)
                if item and item.widget() and isinstance(item.widget(), SeriesSection):
                    selected_items.extend(item.widget().list_widget.selectedItems())
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
        self.btn_sel_action.setEnabled(count > 0)
        self.btn_sel_action.setText(f"Delete {count} Item{'s' if count != 1 else ''}")

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

    def _save_cover_to_cache(self, path: Path, cover_bytes: bytes) -> None:
        """Called from scanner worker thread to save a resized thumbnail to disk cache."""
        url = f"local-cbz://{path.absolute()}/{_COVER_URL_SUFFIX}"
        cache_path = self.image_manager._get_cache_path(url)
        if not cache_path.exists():
            _save_thumbnail(cover_bytes, cache_path)

    def _on_show_labels_changed(self, checked):
        self._show_labels = checked
        self.config_manager.set_show_labels(self._show_labels)
        self.alpha_delegate.show_labels = self._show_labels
        self.folders_delegate.show_labels = self._show_labels
        self._reload_current_view()

    def _on_scan_progress_ui(self, curr, total, msg):
        self.scan_label.setText(msg)
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(curr)
        else:
            self.progress.setRange(0, 0)

        if not self.progress.isVisible():
            self.progress.setVisible(True)
            self.scan_label.setVisible(True)

    def _on_scan_finished_ui(self, has_changes=False):
        self.progress.setVisible(False)
        self.scan_label.setVisible(False)
        # ONLY reload if something actually changed in the DB.
        # This prevents flickering on every startup when the quick scan confirms no changes.
        if has_changes:
            self._reload_current_view()

    def _on_view_mode_changed(self, index):
        # Stack indices: 0: Folders, 1: Grouped, 2: Alpha
        self.config_manager.set_library_view_mode(index)
        stack_map = {
            0: 0, # Folders
            1: 1, # Series (Grouped)
            2: 2, # Alpha
            3: 1, # Publisher (Grouped)
            4: 1, # Writer (Grouped)
            5: 1, # Creator (Grouped)
        }
        stack_idx = stack_map.get(index, 0)
        self.stack.setCurrentIndex(stack_idx)
        self.btn_up.setVisible(stack_idx == 0) # Only show 'Up' in Folder mode
        self._reload_current_view()

    @pyqtSlot()
    def _reload_current_view(self):
        combo_idx = self.config_manager.get_library_view_mode()
        if combo_idx == 0:
            asyncio.create_task(self._load_dir(self.current_dir))
        elif combo_idx == 1:
            asyncio.create_task(self._load_grouped("series"))
        elif combo_idx == 2:
            asyncio.create_task(self._load_alphabetical())
        elif combo_idx == 3:
            asyncio.create_task(self._load_grouped("publisher"))
        elif combo_idx == 4:
            asyncio.create_task(self._load_grouped("writer"))
        elif combo_idx == 5:
            asyncio.create_task(self._load_grouped("penciller"))

    def refresh_and_scan(self):
        self.root_dir = self.config_manager.get_library_dir()
        self.scanner.library_dir = self.root_dir
        # 1. Load from DB immediately
        self._reload_current_view()
        # 2. Start scan in background
        if not self.scanner.is_scanning:
            asyncio.create_task(self.scanner.scan())

    def refresh_icons(self):
        from ui.theme_manager import ThemeManager
        self.btn_up.setIcon(ThemeManager.get_icon("back"))
        self.btn_refresh.setIcon(ThemeManager.get_icon("refresh"))
        self.btn_view_options.setIcon(ThemeManager.get_icon("settings"))

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
        self.btn_up.setVisible(self.stack.currentIndex() == 0)

        self._reload_current_view()

    async def _load_dir(self, path: Path):
        self.path_label.setText(f"Folder: {path}")

        # Fetch data FIRST
        entries = await asyncio.to_thread(_list_dir, path)
        # Single query for all comics under this directory
        dir_rows = await asyncio.to_thread(self.db.get_comics_in_dir, str(path.absolute()))

        self.list_widget.setUpdatesEnabled(False)
        try:
            self.list_widget.clear()
            self.config_manager.set_last_folder_path(str(path.absolute()))
            self.current_dir = path

            for entry in entries:
                item = QListWidgetItem(entry.name)
                item.setData(Qt.ItemDataRole.UserRole, entry.path)

                if entry.is_dir:
                    item.setIcon(ThemeManager.get_icon("folder"))
                else:
                    row = dir_rows.get(str(entry.path.absolute()))
                    if row:
                        r = dict(row)
                        item.setData(Qt.ItemDataRole.UserRole + 1, (r.get("current_page") or 0, r.get("page_count") or 0))

                    item.setIcon(ThemeManager.get_icon("book"))
                    try:
                        asyncio.create_task(self._load_thumb_for_item(entry.path, item))
                    except RuntimeError:
                        pass

                self.list_widget.addItem(item)
        finally:
            self.list_widget.setUpdatesEnabled(True)

    async def _load_grouped(self, field="series"):
        self.path_label.setText(f"Library > Grouped by {field.replace('_', ' ').capitalize()}")
        
        # 1. Fetch data from DB FIRST (this might take a few ms)
        # We do this before clearing or suspending updates to avoid a blank screen.
        if field == "series":
            grouped = await asyncio.to_thread(self.db.get_comics_grouped_by_series)
        else:
            grouped = await asyncio.to_thread(self.db.get_comics_grouped_by_field, field)
            
        # 2. Suspend updates and clear ONLY right before rebuilding
        self.setUpdatesEnabled(False)
        try:
            while self.grouped_layout.count():
                item = self.grouped_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
                    
            group_items = []
            one_offs = []
            
            for name, rows in grouped.items():
                dict_rows = [dict(r) for r in rows]
                if not name or name.strip() == "" or name.startswith("Unknown") or len(rows) == 1:
                    one_offs.extend(dict_rows)
                else:
                    group_items.append((name, dict_rows))
            
            group_items.sort(key=lambda x: x[0].lower())
            
            for group_name, rows in group_items:
                range_str = ""
                if field == "series":
                    issues = []
                    for r in rows:
                        issue_val = r.get("issue")
                        if issue_val and str(issue_val).isdigit():
                            issues.append(int(issue_val))
                    if issues:
                        range_str = f" {format_ranges(issues)}"
                
                title = f"{group_name}{range_str}".upper()
                
                section = SeriesSection(title, rows, self._on_db_item_double_clicked, is_grid=False, image_manager=self.image_manager, meta_sem=self._meta_sem, show_labels=self._show_labels)
                section.list_widget.itemSelectionChanged.connect(self._update_selection_ui)
                if self._selection_mode:
                    section.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
                self.grouped_layout.addWidget(section)
                
            if one_offs:
                title = f"{len(one_offs)} MISCELLANEOUS"
                one_offs.sort(key=lambda x: ( (x.get("series") or "").lower(), (x.get("title") or "").lower() ))
                section = SeriesSection(title, one_offs, self._on_db_item_double_clicked, is_grid=True, image_manager=self.image_manager, meta_sem=self._meta_sem, show_labels=self._show_labels)
                section.list_widget.itemSelectionChanged.connect(self._update_selection_ui)
                if self._selection_mode:
                    section.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
                
                count = len(one_offs)
                cols = 6 
                rows_count = (count + cols - 1) // cols
                item_h = 180 + (45 if self._show_labels else 20)
                section.list_widget.setFixedHeight(rows_count * item_h + 20)
                self.grouped_layout.addWidget(section)
                
            self.grouped_layout.addStretch()
        finally:
            self.setUpdatesEnabled(True)

    async def _load_alphabetical(self):
        self.path_label.setText("Library > Alphabetical")
        
        # 1. Fetch data FIRST
        rows = await asyncio.to_thread(self.db.get_all_comics_alphabetical)
        
        # 2. Rebuild UI efficiently
        self.alpha_list.setUpdatesEnabled(False)
        try:
            self.alpha_list.clear()

            for row in rows:
                r = dict(row)
                title = r["title"] or Path(r["file_path"]).name
                
                item = QListWidgetItem(title)
                item.setData(Qt.ItemDataRole.UserRole, Path(r["file_path"]))
                item.setData(Qt.ItemDataRole.UserRole + 1, (r.get("current_page") or 0, r.get("page_count") or 0))
                
                item.setIcon(ThemeManager.get_icon("book"))
                item.setToolTip(str(Path(r["file_path"]).name))
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
                item.setData(Qt.ItemDataRole.DecorationRole, pixmap)
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
                        item.setData(Qt.ItemDataRole.DecorationRole, pixmap)
                except Exception:
                    pass

    def _on_folder_item_double_clicked(self, item):
        if self._selection_mode:
            return

        path = item.data(Qt.ItemDataRole.UserRole)
        if path.is_dir():
            asyncio.create_task(self._load_dir(path))
        else:
            self.on_open_comic(path)

    def _on_db_item_double_clicked(self, item):
        if self._selection_mode:
            return

        path = item.data(Qt.ItemDataRole.UserRole)
        if path.exists():
            self.on_open_comic(path)

    def _go_up(self):
        try:
            if self.current_dir == self.root_dir:
                return
            parent = self.current_dir.parent
            parent.relative_to(self.root_dir)
            asyncio.create_task(self._load_dir(parent))
        except Exception:
            pass
