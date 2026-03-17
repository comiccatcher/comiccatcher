import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QProgressBar
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QPixmap

from config import ConfigManager
from logger import get_logger
from api.image_manager import ImageManager
from ui.local_archive import read_first_image
from ui.local_comicbox import flatten_comicbox, read_comicbox_dict, subtitle_from_flat, read_comicbox_cover

logger = get_logger("ui.library")

COMIC_EXTS = {".cbz", ".cbr", ".cb7", ".pdf"}

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

class LocalLibraryView(QWidget):
    def __init__(
        self,
        config_manager: ConfigManager,
        on_open_comic: Callable[[Path], None],
    ):
        super().__init__()
        self.config_manager = config_manager
        self.on_open_comic = on_open_comic

        self.root_dir = self.config_manager.get_library_dir()
        self.current_dir = self.root_dir
        self.image_manager = ImageManager(None)
        self._meta_sem = asyncio.Semaphore(4)

        self.layout = QVBoxLayout(self)

        # Header
        self.header_layout = QHBoxLayout()
        self.btn_up = QPushButton("Up")
        self.btn_up.clicked.connect(self._go_up)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh)
        self.path_label = QLabel("")
        self.path_label.setStyleSheet("color: gray;")
        
        self.header_layout.addWidget(self.btn_up)
        self.header_layout.addWidget(self.btn_refresh)
        self.header_layout.addWidget(self.path_label, 1)
        self.layout.addLayout(self.header_layout)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setRange(0, 0) # Indeterminate
        self.layout.addWidget(self.progress)

        # List
        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(50, 70))
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.layout.addWidget(self.list_widget)

        self.refresh()

    def refresh(self):
        self.root_dir = self.config_manager.get_library_dir()
        if not self.current_dir or not self.current_dir.exists():
            self.current_dir = self.root_dir
        
        # Use qasync to run the async load
        asyncio.create_task(self._load_dir(self.current_dir))

    async def _load_dir(self, path: Path):
        self.progress.setVisible(True)
        self.path_label.setText(str(path))
        self.list_widget.clear()

        entries = await asyncio.to_thread(_list_dir, path)
        self.current_dir = path
        
        for entry in entries:
            item = QListWidgetItem(entry.name)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            
            if entry.is_dir:
                item.setIcon(QIcon.fromTheme("folder"))
            else:
                item.setIcon(QIcon.fromTheme("book"))
                # Trigger lazy metadata/thumb load
                asyncio.create_task(self._load_entry_data(entry, item))
                
            self.list_widget.addItem(item)

        self.progress.setVisible(False)

    async def _load_entry_data(self, entry: LibraryEntry, item: QListWidgetItem):
        # Extract/Load Thumbnail
        if entry.path.suffix.lower() in (".cbz", ".cbr", ".cb7"):
            url = f"local-cbz://{entry.path.absolute()}/_cover"
            cache_path = self.image_manager._get_cache_path(url)
            
            if not cache_path.exists():
                async with self._meta_sem:
                    try:
                        data = await asyncio.to_thread(read_comicbox_cover, entry.path)
                        if not data:
                            res = await asyncio.to_thread(read_first_image, entry.path)
                            if res: _, data = res
                        
                        if data:
                            with open(cache_path, "wb") as f:
                                f.write(data)
                    except Exception:
                        pass
            
            if cache_path.exists():
                pixmap = QPixmap(str(cache_path))
                if not pixmap.isNull():
                    item.setIcon(QIcon(pixmap))

        # Metadata subtitle (Enrich name)
        async with self._meta_sem:
            try:
                subtitle = await asyncio.to_thread(self._read_meta_subtitle, entry.path)
                if subtitle:
                    item.setText(f"{entry.name}\n{subtitle}")
            except Exception:
                pass

    @staticmethod
    def _read_meta_subtitle(path: Path) -> str:
        flat = flatten_comicbox(read_comicbox_dict(path))
        return subtitle_from_flat(flat)

    def _on_item_double_clicked(self, item):
        entry = item.data(Qt.ItemDataRole.UserRole)
        if entry.is_dir:
            asyncio.create_task(self._load_dir(entry.path))
        else:
            self.on_open_comic(entry.path)

    def _go_up(self):
        try:
            if self.current_dir == self.root_dir:
                return
            parent = self.current_dir.parent
            parent.relative_to(self.root_dir)
            asyncio.create_task(self._load_dir(parent))
        except Exception:
            pass
