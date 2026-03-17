import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import flet as ft

from logger import get_logger
from ui.snack import show_snack
from api.image_manager import ImageManager
from ui.image_data import TRANSPARENT_DATA_URL
from ui.local_archive import read_first_image
from ui.local_comicbox import flatten_comicbox, read_comicbox_dict, read_comicbox_cover


logger = get_logger("ui.library_detail")
COLORS = getattr(ft, "colors", ft.Colors)
SURFACE_VARIANT = getattr(COLORS, "SURFACE_VARIANT", getattr(COLORS, "SURFACE_CONTAINER", COLORS.SURFACE))


@dataclass
class LocalComicInfo:
    path: Path
    meta: Dict[str, Any]

    @property
    def title(self) -> str:
        return (
            str(self.meta.get("title") or "")
            or self.path.stem
        )


def _read_comicbox_meta(path: Path) -> Dict[str, Any]:
    """
    Returns metadata via comicbox if available; otherwise returns minimal metadata.
    """
    raw = read_comicbox_dict(path)
    return flatten_comicbox(raw)


class LocalComicDetailView(ft.Column):
    def __init__(self, page: ft.Page, on_back, on_read_local=None):
        super().__init__()
        self._page = page
        self.on_back = on_back
        self.on_read_local = on_read_local

        self.expand = True
        self.spacing = 10

        self._path: Optional[Path] = None
        self.image_manager = ImageManager(None)

        self.spinner = ft.ProgressRing(visible=False)
        self.title_text = ft.Text("", size=22, weight=ft.FontWeight.BOLD)
        self.path_text = ft.Text("", size=12, color=COLORS.GREY_500)
        self.read_btn = ft.FilledButton("Read", icon=ft.Icons.MENU_BOOK, disabled=True, on_click=self._on_read)

        self.cover_img = ft.Image(
            src=TRANSPARENT_DATA_URL,
            width=200,
            height=300,
            fit=ft.ImageFit.CONTAIN,
            border_radius=8
        )

        self.kv = ft.Column(spacing=6, expand=True)

        self.controls = [
            ft.Container(
                content=ft.Row(
                    [
                        ft.TextButton("Back", on_click=lambda e: self.on_back()),
                        ft.VerticalDivider(width=1, color=COLORS.GREY_800),
                        ft.Container(content=self.title_text, expand=True),
                        self.read_btn,
                        self.spinner,
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                bgcolor=SURFACE_VARIANT,
                padding=ft.padding.symmetric(horizontal=12, vertical=10),
            ),
            ft.Container(content=self.path_text, padding=ft.padding.only(left=12, right=12)),
            ft.Divider(height=1),
            ft.Container(
                content=ft.Row(
                    [
                        ft.Container(content=self.cover_img, width=200, alignment=ft.alignment.top_center),
                        ft.VerticalDivider(width=20, color=COLORS.TRANSPARENT),
                        self.kv
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    expand=True
                ),
                expand=True,
                padding=ft.padding.symmetric(horizontal=12, vertical=6)
            ),
        ]

    def load_path(self, path: Path):
        self._path = path
        self.title_text.value = path.stem
        self.path_text.value = str(path)
        is_cbz = Path(path).suffix.lower() == ".cbz"
        self.read_btn.disabled = (not bool(self.on_read_local)) or (not is_cbz)
        
        self.cover_img.src = TRANSPARENT_DATA_URL
        self.kv.controls.clear()
        self.spinner.visible = True
        try:
            if self.page: self.update()
        except Exception:
            pass
        
        self._page.run_task(self._load_meta, path)
        if is_cbz:
            self._page.run_task(self._load_cover, path)

    def _on_read(self, e):
        if self.on_read_local and self._path:
            self.on_read_local(self._path)

    async def _load_meta(self, path: Path):
        try:
            meta = await asyncio.to_thread(_read_comicbox_meta, path)
            if path != self._path:
                return
            self._render_meta(meta)
        except Exception as e:
            logger.error(f"Failed reading local comic metadata: {e}")
            show_snack(self._page, f"Failed reading metadata: {e}", text_color=COLORS.ERROR)
        finally:
            self.spinner.visible = False
            try:
                if self.page: self.update()
            except Exception:
                pass

    async def _load_cover(self, path: Path):
        url = f"local-cbz://{path.absolute()}/_cover"
        asset_path = await self.image_manager.get_image_asset_path(url)
        
        if not asset_path:
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
            except Exception:
                pass
        
        if asset_path and path == self._path:
            try:
                self.cover_img.src = asset_path
                self.cover_img.update()
            except:
                pass

    def _render_meta(self, meta: Dict[str, Any]):
        self.kv.controls.clear()

        def add(label: str, value: Any):
            if value is None:
                return
            s = str(value).strip()
            if not s:
                return
            self.kv.controls.append(
                ft.Row(
                    [
                        ft.Text(label, width=140, color=COLORS.GREY_500),
                        ft.Text(s, expand=True, selectable=True),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.START,
                )
            )

        add("Title", meta.get("title"))
        add("Series", meta.get("series"))
        add("Issue", meta.get("issue"))
        add("Volume", meta.get("volume"))
        add("Year", meta.get("year") or meta.get("published"))
        add("Writer", meta.get("writer"))
        add("Penciller", meta.get("penciller"))
        add("Inker", meta.get("inker"))
        add("Colorist", meta.get("colorist"))
        add("Letterer", meta.get("letterer"))
        add("Editor", meta.get("editor"))
        add("Cover artist", meta.get("cover_artist"))
        add("Publisher", meta.get("publisher"))
        add("Page count", meta.get("page_count"))
        add("Summary", meta.get("summary") or meta.get("description"))

        if not self.kv.controls:
            status = (meta or {}).get("_comicbox_status")
            err = (meta or {}).get("_comicbox_error")
            if status == "missing":
                msg = "comicbox is not installed in this venv. Install it to extract ComicInfo metadata."
            elif status == "error":
                msg = f"comicbox couldn't read metadata for this file: {err or 'unknown error'}"
            else:
                msg = "No metadata found in this file."
            self.kv.controls.append(
                ft.Container(
                    content=ft.Text(
                        msg,
                        color=COLORS.GREY_500,
                    ),
                    padding=20,
                )
            )
        
        try:
            if self.page: self.update()
        except:
            pass
