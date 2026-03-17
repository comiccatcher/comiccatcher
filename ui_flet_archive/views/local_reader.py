import asyncio
import os
from pathlib import Path
from typing import List, Optional

import flet as ft

from logger import get_logger
from api.image_manager import ImageManager
from ui.image_data import TRANSPARENT_DATA_URL
from ui.local_archive import LocalPage, list_cbz_pages, read_cbz_entry_bytes
from ui.snack import show_snack


logger = get_logger("ui.local_reader")
COLORS = getattr(ft, "colors", ft.Colors)


class LocalReaderView(ft.Container):
    """
    Minimal local reader for CBZ (zip of images).
    Uses disk-based asset paths to avoid large base64 websocket payloads.
    """

    def __init__(self, page: ft.Page, on_exit):
        super().__init__()
        self._page = page
        self.on_exit = on_exit

        self.expand = True
        self.bgcolor = COLORS.BLACK
        self.visible = False

        self._path: Optional[Path] = None
        self._pages: List[LocalPage] = []
        self._index = 0
        self.image_manager = ImageManager(None)
        self._prefetch_tasks: set[int] = set()
        self._sem = asyncio.Semaphore(2)

        self.image = ft.Image(src=TRANSPARENT_DATA_URL, fit=ft.ImageFit.CONTAIN)

        self.title_text = ft.Text("", color=COLORS.WHITE, weight=ft.FontWeight.BOLD, overflow=ft.TextOverflow.ELLIPSIS)
        self.counter_text = ft.Text("0 / 0", color=COLORS.WHITE)
        self.spinner = ft.ProgressRing(visible=False)

        self.prev_btn = ft.TextButton("Prev", on_click=lambda e: self.prev_page())
        self.next_btn = ft.TextButton("Next", on_click=lambda e: self.next_page())

        self.content = ft.Column(
            [
                ft.Container(
                    content=ft.Row(
                        [
                            ft.TextButton("Back", on_click=lambda e: self.on_exit()),
                            ft.VerticalDivider(width=1, color=COLORS.GREY_800),
                            ft.Container(content=self.title_text, expand=True, padding=ft.padding.only(left=10)),
                            self.counter_text,
                            self.spinner,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    bgcolor=COLORS.with_opacity(0.85, COLORS.BLACK),
                    padding=ft.padding.symmetric(horizontal=10, vertical=6),
                ),
                ft.Container(content=self.image, expand=True, alignment=ft.alignment.center),
                ft.Container(
                    content=ft.Row([self.prev_btn, self.next_btn], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    bgcolor=COLORS.with_opacity(0.85, COLORS.BLACK),
                    padding=ft.padding.symmetric(horizontal=10, vertical=10),
                ),
            ],
            expand=True,
            spacing=0,
        )

    def load_cbz(self, path: Path):
        self.visible = True
        self._path = Path(path)
        self.title_text.value = self._path.stem
        self.image.src = TRANSPARENT_DATA_URL
        self._pages = []
        self._index = 0
        self._prefetch_tasks.clear()
        self.spinner.visible = True
        try:
            if self.page: self.update()
        except Exception:
            pass

        self._page.run_task(self._load_pages)

    async def _load_pages(self):
        assert self._path is not None
        try:
            pages = await asyncio.to_thread(list_cbz_pages, self._path)
            self._pages = pages
            if not pages:
                show_snack(self._page, "No readable images found in this CBZ.", text_color=COLORS.ERROR)
                self.spinner.visible = False
                try:
                    if self.page: self.update()
                except Exception:
                    pass
                return
            self._index = 0
            await self._show_page()
        except Exception as e:
            logger.error(f"Failed loading CBZ pages: {e}")
            show_snack(self._page, f"Failed to open CBZ: {e}", text_color=COLORS.ERROR)
        finally:
            self.spinner.visible = False
            try:
                if self.page: self.update()
            except Exception:
                pass

    def handle_keyboard(self, e: ft.KeyboardEvent):
        if not self.visible:
            return
        if e.key in ("Arrow Right", " "):
            self.next_page()
        elif e.key == "Arrow Left":
            self.prev_page()
        elif e.key == "Escape":
            self.on_exit()

    def next_page(self):
        if self._index < len(self._pages) - 1:
            self._index += 1
            self._page.run_task(self._show_page)

    def prev_page(self):
        if self._index > 0:
            self._index -= 1
            self._page.run_task(self._show_page)

    async def _show_page(self):
        if not self._path or not self._pages:
            return
        idx = self._index
        total = len(self._pages)
        self.counter_text.value = f"{idx + 1} / {total}"
        self.prev_btn.disabled = idx <= 0
        self.next_btn.disabled = idx >= (total - 1)
        self.spinner.visible = True
        try:
            if self.page: self.update()
        except Exception:
            pass

        page = self._pages[idx]
        asset_path = await self._get_page_asset_path(idx, page.name)

        if asset_path and idx == self._index:
            self.image.src = asset_path
            try:
                self.image.update()
            except: pass

        # prefetch next two
        for j in (idx + 1, idx + 2):
            if j < total and j not in self._prefetch_tasks:
                self._prefetch_tasks.add(j)
                self._page.run_task(self._prefetch_page, j, self._pages[j].name)

        self.spinner.visible = False
        try:
            self.spinner.update()
            self.counter_text.update()
            self.prev_btn.update()
            self.next_btn.update()
        except Exception:
            pass

    async def _prefetch_page(self, idx: int, name: str):
        try:
            await self._get_page_asset_path(idx, name)
        finally:
            self._prefetch_tasks.discard(idx)

    async def _get_page_asset_path(self, idx: int, name: str) -> Optional[str]:
        if not self._path:
            return None
        
        # Unique key for CBZ path + entry name
        url = f"local-cbz://{self._path.absolute()}/{name}"
        # Ensure we use relative paths for assets folder
        cache_path = self.image_manager._get_cache_path(url)
        
        if not cache_path.exists():
            async with self._sem:
                try:
                    data = await asyncio.to_thread(read_cbz_entry_bytes, self._path, name)
                    if data:
                        with open(cache_path, "wb") as f:
                            f.write(data)
                except Exception as e:
                    logger.error(f"Failed to extract {name} from {self._path}: {e}")
                    return None
        
        return await self.image_manager.get_image_asset_path(url)
