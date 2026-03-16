import flet as ft
from models.opds import Publication
from urllib.parse import urljoin
from api.client import APIClient
from api.image_manager import ImageManager
from api.progression import ProgressionSync
from logger import get_logger
from ui.snack import show_snack
from ui.image_data import TRANSPARENT_DATA_URL

logger = get_logger("ui.reader")

COLORS = getattr(ft, "colors", ft.Colors)

class ReaderView(ft.Container):
    def __init__(self, page: ft.Page, api_client: APIClient, on_exit):
        super().__init__()
        # Store a reference; do not assign to Control.page.
        self._page = page
        self.api_client = api_client
        self.image_manager = None
        self.on_exit = on_exit
        self.expand = True
        self.bgcolor = COLORS.BLACK
        self.visible = False
        
        self.current_index = 0
        self.reading_order = []
        self.base_url = api_client.profile.get_base_url() if api_client and api_client.profile else ""
        
        self.progression_url = None
        self.progression_sync = None
        self.prefetch_set = set()
        
        # Some Flet desktop builds have been flaky with complex reader UIs.
        # Build a single, minimal control tree to avoid any duplicated-control parent issues.
        self.safe_mode = True

        # Prefer data: URL strings over raw bytes to avoid desktop client crashes during src updates.
        self.image = ft.Image(src=TRANSPARENT_DATA_URL, fit=ft.BoxFit.CONTAIN)

        # Safe UI controls (do not reuse these in any other tree).
        self.safe_title_text = ft.Text(
            "Comic Reader",
            color=COLORS.WHITE,
            weight=ft.FontWeight.BOLD,
            overflow=ft.TextOverflow.ELLIPSIS,
        )
        self.safe_page_counter = ft.Text("0 / 0", color=COLORS.WHITE)
        self.prev_btn = ft.TextButton("Prev", on_click=lambda e: self.prev_page())
        self.next_btn = ft.TextButton("Next", on_click=lambda e: self.next_page())

        self.safe_top = ft.Container(
            content=ft.Row(
                [
                    ft.TextButton("Back", on_click=lambda e: self.on_exit()),
                    ft.VerticalDivider(width=1, color=COLORS.GREY_800),
                    ft.Container(content=self.safe_title_text, expand=True, padding=ft.padding.only(left=10)),
                    self.safe_page_counter,
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=COLORS.with_opacity(0.85, COLORS.BLACK),
            padding=ft.padding.symmetric(horizontal=10, vertical=5),
        )

        self.safe_bottom = ft.Container(
            content=ft.Row([self.prev_btn, self.next_btn], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            bgcolor=COLORS.with_opacity(0.85, COLORS.BLACK),
            padding=ft.padding.symmetric(horizontal=10, vertical=8),
        )

        # Keep a hidden slider object for bookkeeping; it is not part of the visible tree.
        self.slider = ft.Slider(
            value=0,
            min=0,
            max=0,
            divisions=1,
            visible=False,
            on_change=self.on_slider_change,
        )

        self.safe_root = ft.Column(
            [
                self.safe_top,
                ft.Container(content=self.image, expand=True, alignment=ft.Alignment.CENTER),
                self.safe_bottom,
            ],
            expand=True,
            spacing=0,
        )

        # Overlay/experimental reader UI can be reintroduced later behind a flag,
        # but must use its own distinct control instances.
        self.content = self.safe_root

    def set_fit(self, mode):
        self.image.fit = mode
        logger.info(f"Reader fit mode changed to: {mode}")
        self.update()

    def load_manifest(self, pub: Publication, manifest_url: str):
        logger.info(f"Opening reader for: {pub.metadata.title}")
        self.image_manager = ImageManager(self.api_client)
        
        self.visible = True
        self.safe_title_text.value = pub.metadata.title
        self.base_url = self.api_client.profile.get_base_url()
        self.progression_sync = ProgressionSync(self.api_client)
        self.progression_url = None
        self.prefetch_set = set()
        self.image.src = TRANSPARENT_DATA_URL

        # Ensure the expected reader layout is mounted.
        self.content = self.safe_root
        
        for link in pub.links:
            if getattr(link, 'rel', '') == "http://www.cantook.com/api/progression":
                self.progression_url = urljoin(self.base_url, link.href)
                break

        self._page.run_task(self._fetch_and_load, pub, manifest_url)
        # Ensure the reader view becomes visible immediately (spinner/first frame).
        try:
            if self.page:
                self.update()
        except Exception:
            pass

    async def _fetch_and_load(self, pub: Publication, manifest_url: str):
        self.reading_order = []
        try:
            if manifest_url:
                response = await self.api_client.get(manifest_url)
                response.raise_for_status()
                data = response.json()
                if "readingOrder" in data:
                    self.reading_order = data["readingOrder"]
            elif pub.readingOrder:
                self.reading_order = [item.model_dump() for item in pub.readingOrder]

            if self.reading_order:
                max_index = max(len(self.reading_order) - 1, 0)
                self.slider.min = 0
                self.slider.max = max_index
                self.slider.divisions = max(max_index, 1)
                
                self.current_index = 0
                if self.progression_url:
                    prog_data = await self.progression_sync.get_progression(self.progression_url)
                    if prog_data and "progression" in prog_data:
                        progress_pct = prog_data["progression"]
                        self.current_index = int(progress_pct * len(self.reading_order))
                        self.current_index = min(max(self.current_index, 0), len(self.reading_order) - 1)
                self.slider.value = self.current_index
                self.slider.update()
                
                self.show_page()
            else:
                logger.error("No pages found in reading order.")
                show_snack(self._page, "This comic has no readable pages.")
                
        except Exception as e:
            logger.error(f"Error initializing reader: {e}")
            show_snack(self._page, f"Error opening reader: {e}")

    def show_page(self):
        if 0 <= self.current_index < len(self.reading_order):
            item = self.reading_order[self.current_index]
            href = item.get("href")
            if not href.startswith("http"):
                href = urljoin(self.base_url, href)
            
            self._page.run_task(self._load_image_bytes, href)
            
            self.safe_page_counter.value = f"{self.current_index + 1} / {len(self.reading_order)}"
            self.prev_btn.disabled = self.current_index <= 0
            self.next_btn.disabled = self.current_index >= (len(self.reading_order) - 1)
            self.slider.value = self.current_index
            self.slider.update()
            self.update()
            
            # Prefetch next 3 pages
            for i in range(1, 4):
                next_idx = self.current_index + i
                if next_idx < len(self.reading_order):
                    next_item = self.reading_order[next_idx]
                    next_href = next_item.get("href")
                    if not next_href.startswith("http"):
                        next_href = urljoin(self.base_url, next_href)
                    if next_href not in self.prefetch_set:
                        self._page.run_task(self._prefetch_image, next_href)

            # Sync progression
            if self.progression_url and len(self.reading_order) > 0:
                current_pct = self.current_index / len(self.reading_order)
                if self.current_index == len(self.reading_order) - 1:
                    current_pct = 1.0
                self._page.run_task(self.progression_sync.update_progression, self.progression_url, current_pct, current_pct)

    async def _load_image_bytes(self, url: str):
        try:
            asset_path = await self.image_manager.get_image_asset_path(url)
            if asset_path:
                # Re-verify we are still on the page that requested this URL
                item = self.reading_order[self.current_index]
                current_url = item.get("href")
                if not current_url.startswith("http"):
                    current_url = urljoin(self.base_url, current_url)
                    
                if url == current_url:
                    self.image.src = asset_path
                    try:
                        self.image.update()
                    except:
                        pass
        except Exception as e:
            logger.error(f"Failed to load image from {url}: {e}")

    async def _prefetch_image(self, url: str):
        if url in self.prefetch_set: return
        self.prefetch_set.add(url)
        try:
            await self.image_manager.get_image_b64(url)
        except:
            pass
        finally:
            self.prefetch_set.discard(url)

    def on_slider_change(self, e):
        # Slider not used in safe layout (kept for API compatibility).
        return

    def handle_tap(self, e: ft.TapEvent):
        # Flet 0.8x: use Page.width/window_width; Page.window is not stable across targets.
        width = (getattr(self._page, "window_width", None) or getattr(self._page, "width", None) or 800)
        if e.local_x > width * 0.8:
            self.next_page()
        elif e.local_x < width * 0.2:
            self.prev_page()

    def handle_keyboard(self, e: ft.KeyboardEvent):
        if not self.visible:
            return
        if e.key == "Arrow Right" or e.key == " ":
            self.next_page()
        elif e.key == "Arrow Left":
            self.prev_page()
        elif e.key == "Escape":
            self.on_exit()

    def next_page(self):
        if self.current_index < len(self.reading_order) - 1:
            self.current_index += 1
            self.show_page()

    def prev_page(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.show_page()
