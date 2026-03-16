import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

import flet as ft

from config import ConfigManager
from logger import get_logger
from api.image_manager import ImageManager
from ui.image_data import TRANSPARENT_DATA_URL
from ui.local_archive import read_first_image
from ui.local_comicbox import flatten_comicbox, read_comicbox_dict, subtitle_from_flat, read_comicbox_cover


logger = get_logger("ui.library")
COLORS = getattr(ft, "colors", ft.Colors)
SURFACE_VARIANT = getattr(COLORS, "SURFACE_VARIANT", getattr(COLORS, "SURFACE_CONTAINER", COLORS.SURFACE))


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

    # Folders first, then files, both alphabetical.
    entries.sort(key=lambda e: (not e.is_dir, e.name.lower()))
    return entries


class LocalLibraryView(ft.Column):
    def __init__(
        self,
        page: ft.Page,
        config_manager: ConfigManager,
        on_open_comic: Callable[[Path], None],
    ):
        super().__init__()
        self._page = page
        self.config_manager = config_manager
        self.on_open_comic = on_open_comic

        self.expand = True
        self.spacing = 0

        self.root_dir = self.config_manager.get_library_dir()
        self.current_dir = self.root_dir
        self._entries: List[LibraryEntry] = []
        self._meta_cache: Dict[str, str] = {}  # path -> subtitle
        self._meta_sem = asyncio.Semaphore(4)
        self.image_manager = ImageManager(None)

        self.spinner = ft.ProgressRing(visible=False)
        self.path_text = ft.Text("", size=14, color=COLORS.GREY_200, overflow=ft.TextOverflow.ELLIPSIS, expand=True)

        self.list_view = ft.ListView(expand=True, spacing=8, padding=10)

        self.controls = [
            ft.Container(
                content=ft.Row(
                    [
                        ft.IconButton(ft.Icons.ARROW_UPWARD, tooltip="Up", on_click=self._go_up),
                        ft.IconButton(ft.Icons.REFRESH, tooltip="Refresh", on_click=lambda e: self.refresh()),
                        self.path_text,
                        self.spinner,
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                bgcolor=SURFACE_VARIANT,
                padding=ft.padding.symmetric(horizontal=12, vertical=10),
            ),
            ft.Divider(height=1),
            ft.Container(content=self.list_view, expand=True),
        ]

        self.refresh()

    def refresh(self):
        # Root can change if the user edited settings.
        self.root_dir = self.config_manager.get_library_dir()
        if not self.current_dir.exists():
            self.current_dir = self.root_dir
        self._page.run_task(self._load_dir, self.current_dir)

    async def _load_dir(self, path: Path):
        self.spinner.visible = True
        self.path_text.value = str(path)
        try:
            if self.page: self.update()
        except Exception:
            pass

        entries = await asyncio.to_thread(_list_dir, path)
        self.current_dir = path
        self._entries = entries

        self.spinner.visible = False
        self._render_entries_incremental()

    def _render_entries_incremental(self):
        self.list_view.controls.clear()

        if not self._entries:
            self.list_view.controls.append(
                ft.Container(
                    content=ft.Text("No comics found in this folder.", color=COLORS.GREY_500),
                    alignment=ft.Alignment.CENTER,
                    padding=40,
                )
            )
            try:
                if self.page: self.update()
            except Exception:
                pass
            return

        # First paint quickly, then append the rest in the background.
        initial = min(80, len(self._entries))
        for entry in self._entries[:initial]:
            self.list_view.controls.append(self._entry_row(entry))

        try:
            if self.page: self.update()
        except Exception:
            pass

        if initial < len(self._entries):
            self._page.run_task(self._append_remaining, self._entries[initial:])

    def _entry_row(self, entry: LibraryEntry) -> ft.Control:
        icon = ft.Icons.FOLDER_OUTLINED if entry.is_dir else ft.Icons.BOOK_OUTLINED
        subtitle_text = ft.Text(
            "Folder" if entry.is_dir else entry.path.suffix.upper().lstrip("."),
            size=12,
            color=COLORS.GREY_500,
        )

        thumb = ft.Image(
            src=TRANSPARENT_DATA_URL,
            width=50,
            height=70,
            fit=ft.BoxFit.COVER,
            border_radius=4,
            visible=not entry.is_dir
        )
        folder_icon = ft.Icon(
            icon, 
            size=30,
            color=COLORS.BLUE_300 if entry.is_dir else COLORS.GREY_300,
            visible=entry.is_dir
        )

        def _on_click(_):
            if entry.is_dir:
                self._page.run_task(self._load_dir, entry.path)
            else:
                self.on_open_comic(entry.path)

        if not entry.is_dir:
            # Lazy metadata enrichment for visible items.
            key = str(entry.path)
            cached = self._meta_cache.get(key)
            if cached:
                subtitle_text.value = cached
            else:
                self._page.run_task(self._enrich_metadata, entry.path, subtitle_text)
            
            # Lazy thumbnail loading
            self._page.run_task(self._load_thumbnail, entry.path, thumb, folder_icon)

        return ft.Container(
            content=ft.Row(
                [
                    ft.Stack([
                        ft.Container(folder_icon, width=50, height=70, alignment=ft.Alignment.CENTER),
                        thumb
                    ]),
                    ft.Column(
                        [
                            ft.Text(entry.name, weight=ft.FontWeight.BOLD, overflow=ft.TextOverflow.ELLIPSIS, max_lines=2),
                            subtitle_text,
                        ],
                        expand=True,
                        spacing=2,
                    ),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, color=COLORS.GREY_700),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=10,
            border=ft.border.all(1, COLORS.OUTLINE_VARIANT),
            border_radius=10,
            bgcolor=SURFACE_VARIANT,
            on_click=_on_click,
        )

    async def _append_remaining(self, entries: List[LibraryEntry]):
        # Append in chunks to avoid a single giant diff/update.
        chunk = 80
        for i in range(0, len(entries), chunk):
            for entry in entries[i : i + chunk]:
                self.list_view.controls.append(self._entry_row(entry))
            try:
                if self.page: self.update()
            except Exception:
                pass
            await asyncio.sleep(0)

    async def _enrich_metadata(self, path: Path, subtitle_text: ft.Text):
        key = str(path)
        # Dedupe: if we already filled it while this task was queued, stop.
        if key in self._meta_cache:
            return
        async with self._meta_sem:
            subtitle = await asyncio.to_thread(self._read_meta_subtitle, path)
        if not subtitle:
            return
        self._meta_cache[key] = subtitle
        try:
            subtitle_text.value = subtitle
            subtitle_text.update()
        except Exception:
            pass

    async def _load_thumbnail(self, path: Path, thumb: ft.Image, folder_icon: ft.Icon):
        if path.suffix.lower() not in (".cbz", ".cbr", ".cb7"):
            # For now only comic archives
            if not path.is_dir():
                try:
                    folder_icon.visible = True
                    folder_icon.update()
                except: pass
            return
        
        url = f"local-cbz://{path.absolute()}/_cover"
        asset_path = await self.image_manager.get_image_asset_path(url)
        
        if not asset_path:
            # Extraction needed
            async with self._meta_sem: # reuse same semaphore for IO limiting
                try:
                    # Try comicbox first
                    data = await asyncio.to_thread(read_comicbox_cover, path)
                    
                    if not data:
                        # Fallback to first image
                        res = await asyncio.to_thread(read_first_image, path)
                        if res:
                            name, data = res
                    
                    if data:
                        cache_path = self.image_manager._get_cache_path(url)
                        with open(cache_path, "wb") as f:
                            f.write(data)
                        asset_path = await self.image_manager.get_image_asset_path(url)
                except Exception as e:
                    logger.debug(f"Failed extracting cover for {path}: {e}")
        
        if asset_path:
            try:
                thumb.src = asset_path
                thumb.visible = True
                folder_icon.visible = False
                thumb.update()
                folder_icon.update()
            except Exception:
                pass

    @staticmethod
    def _read_meta_subtitle(path: Path) -> str:
        flat = flatten_comicbox(read_comicbox_dict(path))
        return subtitle_from_flat(flat)

    def _go_up(self, _):
        try:
            if self.current_dir == self.root_dir:
                return
            parent = self.current_dir.parent
            # Prevent going above the configured library root.
            parent.relative_to(self.root_dir)
            self._page.run_task(self._load_dir, parent)
        except Exception:
            return
