import flet as ft
import re
import traceback
import os
import asyncio
import math
import time
from typing import Optional, Dict, List
from config import ConfigManager
from api.client import APIClient
from api.opds_v2 import OPDS2Client
from api.image_manager import ImageManager
from api.progression import ProgressionSync
from models.opds import OPDSFeed, Group, Link, Publication
from urllib.parse import urljoin, urlparse, parse_qs, urlunparse, urlencode
from logger import get_logger
from ui.image_data import TRANSPARENT_DATA_URL, data_url_from_b64, guess_mime_from_url

logger = get_logger("ui.browser")

COLORS = getattr(ft, "colors", ft.Colors)
SURFACE_VARIANT = getattr(COLORS, "SURFACE_VARIANT", getattr(COLORS, "SURFACE_CONTAINER", COLORS.SURFACE))

# Estimates for window fitting
LIST_ROW_HEIGHT = 50
GRID_ROW_HEIGHT = 260
COLUMNS = 5
TRADITIONAL_RENDER_BATCH = 24

class BrowserView(ft.Column):
    def __init__(self, page: ft.Page, config_manager: ConfigManager, on_open_detail, on_update_header, on_load_complete, on_navigate):
        super().__init__()
        # Store a reference; do not assign to Control.page.
        self._page = page
        self.config_manager = config_manager
        self.on_open_detail_callback = on_open_detail
        self.on_update_header = on_update_header
        self.on_load_complete = on_load_complete
        self.on_navigate = on_navigate
        self.expand = True
        
        self.current_profile = None
        self.api_client = None
        self.opds_client = None
        self.image_manager = None
        self.progression_sync = None
        
        # --- State ---
        self.current_url = None
        self.next_url = None
        self.total_items = 0
        self.is_loading_more = False
        # Prevent out-of-order async loads from clobbering the UI when users click fast.
        self._load_token = 0
        
        # Viewport/Buffer State
        self.items_buffer = [] 
        self.is_pub_mode = False
        self.is_dashboard = False
        self.viewport_offset = 0 
        self.items_per_screen = 20
        self.total_viewport_pages = 0
        self.current_viewport_page = 1
        # Traditional paging helpers (set during _setup_traditional_paging)
        self._paging_self_url: Optional[str] = None
        self._paging_zero_based: bool = False
        self._paging_can_derive: bool = False
        self._paging_busy: bool = False
        self._thumb_refresh_task: Optional[asyncio.Task] = None
        self._thumb_refresh_deadline: float = 0.0

        # UI Components
        self.paging_status = ft.Text("", size=11, color=COLORS.BLUE_200)
        self.search_input = ft.TextField(hint_text="Search...", expand=True, on_submit=self.execute_search, visible=False, prefix_icon=ft.Icons.SEARCH, height=35, text_size=13, content_padding=ft.padding.symmetric(horizontal=10, vertical=0))
        self.facet_menu = ft.PopupMenuButton(icon=ft.Icons.FILTER_LIST, tooltip="Filter", visible=False, items=[])
        
        # Paging Bar (used by viewport + traditional paging)
        self.page_input = ft.TextField(
            hint_text="Go to...",
            width=70,
            height=35,
            text_size=12,
            content_padding=ft.padding.symmetric(horizontal=10),
            on_submit=self._on_page_input_submit,
        )
        # Row itself should NOT expand in a Column (that would eat vertical space).
        # Wrap it in a Container with alignment=center, which makes the container fill width and center the row.
        self.paging_row = ft.Row(spacing=2, alignment=ft.MainAxisAlignment.CENTER, wrap=True)
        self.paging_spinner = ft.ProgressRing(visible=False, width=14, height=14, stroke_width=2)
        self.paging_bar = ft.Container(
            content=self.paging_row,
            alignment=ft.Alignment.CENTER,
            visible=False,
            padding=ft.padding.only(top=6, bottom=6),
        )
        
        self.header = ft.Row([ft.Container(expand=True), self.paging_status, self.facet_menu, self.search_input], spacing=10)
        
        # Main content area
        # Note: wiring on_scroll for large pages can create a flood of events which triggers
        # expensive auto-update diffs in Flet. We'll enable it only for infinite-scroll mode.
        self.main_content = ft.ListView(expand=True, spacing=15, padding=ft.padding.only(bottom=40, left=10, right=10))
        
        self.loading_indicator = ft.ProgressRing(visible=False, width=30, height=30)
        self.footer_loading = ft.ProgressRing(width=20, height=20, visible=False)
        self.end_of_list_text = ft.Text("End of Library", size=12, color=COLORS.GREY_700, italic=True, visible=False)
        self.footer = ft.Container(content=ft.Row([self.footer_loading, self.end_of_list_text], alignment=ft.MainAxisAlignment.CENTER), padding=20)

        self.controls = [
            self.header,
            self.paging_bar,
            ft.Container(content=self.loading_indicator, alignment=ft.Alignment.CENTER),
            self.main_content
        ]
        
        # Dynamic Resizing
        self._page.on_resize = self._on_window_resize

    def safe_update(self):
        """Helper to update only if the control is attached to a page."""
        try:
            if self.page:
                self.update()
        except: pass

    def safe_content_update(self):
        """Helper to update main_content only if attached."""
        try:
            if self.main_content.page:
                self.main_content.update()
        except: pass

    def load_profile(self, profile):
        self.current_profile = profile
        self.api_client = APIClient(profile)
        self.opds_client = OPDS2Client(self.api_client)
        self.image_manager = ImageManager(self.api_client)
        self.progression_sync = ProgressionSync(self.api_client)

    async def load_feed(self, url: str, title: str = None, force_refresh: bool = False):
        self._load_token += 1
        token = self._load_token
        t0 = time.monotonic()

        self.current_url = url
        self.viewport_offset = 0
        self.items_buffer = []
        self.is_loading_more = False
        self.end_of_list_text.visible = False
        
        method = self.config_manager.get_scroll_method()

        # Provide immediate feedback when paging through large feeds.
        if method == "paging":
            self._set_paging_busy(True)
            # Avoid clearing the list immediately in paging mode; keep previous content visible
            # while we fetch the next page to prevent "blank screen" perceived hangs.
            self.loading_indicator.visible = False
        else:
            self.loading_indicator.visible = True
            self.main_content.controls.clear()
        self.safe_update()
        
        try:
            logger.debug(f"load_feed start token={token} force={force_refresh} url={url}")
            feed = await self.opds_client.get_feed(url, force_refresh=force_refresh)
            # If a newer navigation started while we were awaiting, don't update UI with stale results.
            if token != self._load_token:
                return
            logger.debug(f"load_feed fetched token={token} dt={time.monotonic()-t0:.3f}s url={url}")
            self.on_load_complete(url, title or feed.metadata.title or "Catalog")
            
            self.total_items = getattr(feed.metadata, 'numberOfItems', 0)
            self.next_url = self._find_rel_link(feed, "next", url)
            
            # "Dashboard" is only when groups are used for featured/publication carousels.
            # Many servers (including Codex) also include `groups` for facets on normal list feeds.
            self.is_dashboard = any(bool(getattr(g, "publications", None)) for g in (feed.groups or []))
            self.is_pub_mode = len(feed.publications or []) > 0
            
            if self.is_dashboard:
                self.paging_bar.visible = False
                self.main_content.scroll = ft.ScrollMode.AUTO
                self.main_content.on_scroll = None
                self._render_dashboard(feed)
            else:
                if self.is_pub_mode:
                    self.items_buffer.extend(feed.publications)
                else:
                    self.items_buffer.extend([n for n in (feed.navigation or []) if n.title != "Start"])

                if method == "viewport":
                    self.main_content.scroll = ft.ScrollMode.HIDDEN
                    self.main_content.on_scroll = None
                    self._render_viewport_screen()
                elif method == "paging":
                    self.main_content.scroll = ft.ScrollMode.AUTO
                    self.main_content.on_scroll = None
                    # Now that we have fresh JSON, replace the previous page contents.
                    self.main_content.controls.clear()
                    self._setup_traditional_paging(feed)
                    self._render_traditional_page(feed)
                    # Opportunistic prefetch to reduce perceived latency on next/prev clicks.
                    try:
                        if self.next_url:
                            self._page.run_task(self._prefetch_feed, self.next_url, token)
                        prev = self._find_rel_link_any(feed, ["prev", "previous"], self._paging_self_url or url)
                        if prev:
                            self._page.run_task(self._prefetch_feed, prev, token)
                    except Exception:
                        pass
                else: # infinite
                    self.main_content.scroll = ft.ScrollMode.AUTO
                    self.main_content.on_scroll = self._on_scroll_event
                    self.paging_bar.visible = False
                    self._render_infinite_page(feed, append=False)
            
            self.search_input.visible = self._find_rel_link(feed, "search", url) is not None
            self._setup_facets(feed)
            
        except Exception as e:
            if token != self._load_token:
                return
            logger.error(f"Feed error: {e}\n{traceback.format_exc()}")
            self.main_content.controls.append(ft.Text(f"Error: {e}", color=COLORS.ERROR))
        finally:
            # Only the most recent load should flip loading indicators.
            if token == self._load_token:
                self.loading_indicator.visible = False
                self._set_paging_busy(False)
                self.safe_content_update()
                self.safe_update()
                logger.debug(f"load_feed end token={token} dt={time.monotonic()-t0:.3f}s url={url}")

    def _set_paging_busy(self, busy: bool):
        self._paging_busy = busy
        self.paging_spinner.visible = busy
        # Keep status text compact; title/breadcrumb remains stable.
        if busy:
            self.paging_status.value = "Loading..."

        # Disable page nav controls while a paging fetch is in-flight to avoid request spam.
        for c in list(self.paging_row.controls):
            if isinstance(c, ft.TextButton):
                c.disabled = busy or (c.on_click is None)

        try:
            if self.paging_bar.page:
                self.paging_bar.update()
            else:
                self.safe_update()
        except Exception:
            pass

    async def _prefetch_feed(self, url: str, token: int):
        # Best-effort background warming of OPDS JSON cache.
        try:
            await asyncio.sleep(0)
            if token != self._load_token:
                return
            await self.opds_client.get_feed(url)
        except Exception:
            pass

    def _render_dashboard(self, feed: OPDSFeed):
        logger.debug("Building dashboard...")
        self.main_content.controls.clear()
        
        if feed.navigation:
            nav_items = []
            for n in feed.navigation:
                if n.title == "Start": continue
                rel_str = "".join(n.rel or []) if isinstance(n.rel, list) else (n.rel or "")
                if "facet" in rel_str: continue
                nav_items.append(ft.ListTile(title=ft.Text(n.title, size=14), on_click=lambda e, u=n.href, t=n.title: self.on_navigate(urljoin(self.api_client.profile.get_base_url(), u), t), dense=True))
            if nav_items:
                self.main_content.controls.append(ft.Container(content=ft.Column(nav_items, spacing=0), border=ft.border.all(1, COLORS.OUTLINE_VARIANT), border_radius=5))

        if feed.groups:
            for group in feed.groups:
                group_title = group.metadata.title if (hasattr(group, 'metadata') and group.metadata) else "Untitled Group"
                gl = next((l.href for l in (group.links or []) if l.rel == "self" or (isinstance(l.rel, list) and "self" in l.rel)), None)
                
                self.main_content.controls.append(ft.Row([ft.Text(group_title, size=18, weight=ft.FontWeight.BOLD), ft.TextButton("View All", on_click=lambda e, u=gl, t=group_title: self.on_navigate(urljoin(self.api_client.profile.get_base_url(), u), t), visible=gl is not None)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN))
                
                if group.publications:
                    carousel = ft.Row([self.create_pub_card(pub, is_carousel=True) for pub in group.publications], scroll=ft.ScrollMode.AUTO, spacing=15)
                    self.main_content.controls.append(ft.Container(content=carousel, height=240))
                self.main_content.controls.append(ft.Divider(height=1, color=COLORS.OUTLINE_VARIANT))

        if feed.publications:
            grid = ft.Row(wrap=True, spacing=10, run_spacing=10)
            for p in feed.publications: grid.controls.append(self.create_pub_card(p))
            self.main_content.controls.append(grid)
            
        self.paging_status.value = ""
        self.safe_content_update()
        logger.debug("Dashboard complete.")

    def create_pub_card(self, pub: Publication, is_carousel=False, token: Optional[int] = None):
        img_url = pub.images[0].href if (pub.images and len(pub.images) > 0) else None
        # Stable dimensions for card components
        img = ft.Image(src=TRANSPARENT_DATA_URL, fit=ft.BoxFit.COVER, width=140, height=200)
        
        if img_url:
            full_img_url = urljoin(self.api_client.profile.get_base_url(), img_url)
            self._page.run_task(self._load_thumbnail_async, full_img_url, img, token)
            
        return ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.Container(content=img, bgcolor=SURFACE_VARIANT, border_radius=5),
                    ft.Container(content=ft.Text(pub.metadata.title, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS, size=11, text_align=ft.TextAlign.CENTER), padding=2, height=40)
                ], spacing=5, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                on_click=lambda _: self.on_open_detail_callback(pub, self._get_self_url(pub)),
                border_radius=5, padding=5, width=150
            ),
            elevation=2
        )

    # --- Viewport Mode Logic ---

    def _render_viewport_screen(self):
        self._calculate_viewport_capacity()
        self._setup_viewport_paging_ui()
        self.main_content.controls.clear()
        
        batch = self.items_buffer[self.viewport_offset : self.viewport_offset + self.items_per_screen]
        if self.is_pub_mode:
            grid = ft.Row(wrap=True, spacing=10, run_spacing=10)
            for p in batch: grid.controls.append(self.create_pub_card(p))
            self.main_content.controls.append(grid)
        else:
            nav = ft.Column([ft.ListTile(title=ft.Text(n.title, size=14), on_click=lambda e, u=n.href, t=n.title: self.on_navigate(urljoin(self.api_client.profile.get_base_url(), u), t), dense=True) for n in batch], spacing=0)
            self.main_content.controls.append(ft.Container(content=nav, border=ft.border.all(1, COLORS.OUTLINE_VARIANT), border_radius=5))

        self.paging_status.value = f"Screen {self.current_viewport_page} of {self.total_viewport_pages}"
        if self.viewport_offset + self.items_per_screen >= len(self.items_buffer) - 5 and self.next_url:
            self._page.run_task(self._buffer_next_server_page)
        self.safe_content_update()

    def _calculate_viewport_capacity(self):
        win_h = self._page.window_height or 800
        available_h = win_h - 180
        if self.is_pub_mode:
            rows_fit = int(max(1, (available_h // GRID_ROW_HEIGHT)))
            self.items_per_screen = rows_fit * COLUMNS
        else:
            self.items_per_screen = int(max(5, (available_h // LIST_ROW_HEIGHT)))
        total = self.total_items or len(self.items_buffer)
        self.total_viewport_pages = math.ceil(total / self.items_per_screen) if self.items_per_screen > 0 else 1
        self.current_viewport_page = (self.viewport_offset // self.items_per_screen) + 1 if self.items_per_screen > 0 else 1

    def _setup_viewport_paging_ui(self):
        if self.total_viewport_pages <= 1:
            self.paging_bar.visible = False
            return
        self.paging_bar.visible = True
        self.paging_row.controls.clear()
        def btn(label, target_offset, tooltip=None, is_current=False):
            return ft.TextButton(label, on_click=lambda _: self.jump_to_viewport_offset(target_offset), disabled=is_current, style=ft.ButtonStyle(color=COLORS.BLUE_400 if is_current else None, padding=2), tooltip=tooltip)
        self.paging_row.controls.append(btn("<<", 0, "First Screen"))
        self.paging_row.controls.append(btn("<", max(0, self.viewport_offset - self.items_per_screen), "Prev Screen"))
        curr = self.current_viewport_page
        for p in range(max(1, curr - 2), min(self.total_viewport_pages, curr + 2) + 1):
            offset = (p - 1) * self.items_per_screen
            self.paging_row.controls.append(btn(str(p), offset, is_current=(p == curr)))
        last_offset = (self.total_viewport_pages - 1) * self.items_per_screen
        self.paging_row.controls.append(btn(">", min(last_offset, self.viewport_offset + self.items_per_screen), "Next Screen"))
        self.paging_row.controls.append(btn(">>", last_offset, "Last Screen"))
        self.paging_row.controls.extend([ft.VerticalDivider(width=1, color=COLORS.GREY_800), self.page_input])
        self.page_input.value = str(curr)

    def jump_to_viewport_offset(self, offset):
        self.viewport_offset = offset
        if offset >= len(self.items_buffer) and self.next_url:
            self._page.run_task(self._buffer_until_offset, offset)
        else:
            self._render_viewport_screen()

    def jump_to_viewport_page(self, e):
        try:
            target = int(self.page_input.value)
            if 1 <= target <= self.total_viewport_pages: self.jump_to_viewport_offset((target - 1) * self.items_per_screen)
        except: pass

    def _on_page_input_submit(self, e):
        method = self.config_manager.get_scroll_method()
        if method == "viewport":
            self.jump_to_viewport_page(e)
        elif method == "paging":
            self.jump_to_traditional_page(e)

    def jump_to_traditional_page(self, e):
        try:
            target = int(self.page_input.value)
        except:
            return
        if target < 1:
            return
        # User input is always 1-based. Convert to server index if needed.
        server_page = target - 1 if self._paging_zero_based else target
        base = self._paging_self_url or self.current_url
        url = self._derive_server_url(base, server_page)
        if not url:
            return
        # Replace current history entry and keep breadcrumb title stable.
        self._set_paging_busy(True)
        self._page.run_task(self._deferred_paging_navigate, url)

    async def _deferred_paging_navigate(self, url: str):
        # Let the UI render the spinner before we do any other work.
        await asyncio.sleep(0)
        self.on_navigate(url, "Loading...", replace=True, keep_title=True)

    async def _buffer_until_offset(self, target_offset):
        self.footer_loading.visible = True; self.safe_update()
        while target_offset + self.items_per_screen > len(self.items_buffer) and self.next_url:
            await self._buffer_next_server_page()
        self.footer_loading.visible = False; self._render_viewport_screen()

    async def _buffer_next_server_page(self):
        if not self.next_url or self.is_loading_more: return
        self.is_loading_more = True
        try:
            feed = await self.opds_client.get_feed(self.next_url)
            self.next_url = self._find_rel_link(feed, "next", self.next_url)
            if self.is_pub_mode: self.items_buffer.extend(feed.publications or [])
            else: self.items_buffer.extend([n for n in (feed.navigation or []) if n.title != "Start"])
        except: pass
        finally: self.is_loading_more = False

    def next_viewport_screen(self):
        if self.viewport_offset + self.items_per_screen < len(self.items_buffer):
            self.viewport_offset += self.items_per_screen
            self._render_viewport_screen()
        elif self.next_url:
            self._page.run_task(self._fetch_and_flip_viewport)

    async def _fetch_and_flip_viewport(self):
        self.footer_loading.visible = True; self.safe_update()
        await self._buffer_next_server_page()
        self.footer_loading.visible = False; self.next_viewport_screen()

    def prev_viewport_screen(self):
        if self.viewport_offset > 0:
            self.viewport_offset = max(0, self.viewport_offset - self.items_per_screen)
            self._render_viewport_screen()

    # --- Paging Mode Logic ---

    def _setup_traditional_paging(self, feed: OPDSFeed):
        # Prefer server-provided links; only derive jump URLs when we can do so safely.
        meta = getattr(feed, "metadata", None)
        items_p = getattr(meta, "itemsPerPage", None) if meta else None
        curr_p = getattr(meta, "currentPage", None) if meta else None
        # Important: currentPage can be 0 on some servers (0-based paging).
        items_p = int(items_p) if items_p is not None else None
        curr_p = int(curr_p) if curr_p is not None else None

        self_url = self._find_rel_link_any(feed, ["self"], self.current_url) or self.current_url
        self._paging_self_url = self_url

        first_url = self._find_rel_link_any(feed, ["first"], self_url)
        prev_url = self._find_rel_link_any(feed, ["prev", "previous"], self_url)
        next_url = self._find_rel_link_any(feed, ["next"], self_url)
        last_url = self._find_rel_link_any(feed, ["last"], self_url)

        # Detect whether the server is 0-based or 1-based for display/jumps.
        # If currentPage isn't provided, fall back to the common `?page=` convention.
        self._paging_zero_based = False
        if curr_p == 0:
            self._paging_zero_based = True
        else:
            try:
                q = parse_qs(urlparse(self_url).query)
                if "page" in q and q["page"] and q["page"][0] == "0":
                    self._paging_zero_based = True
            except Exception:
                pass

        # If the server doesn't provide first/last, derive them only when we can.
        total_p = None
        if items_p and self.total_items:
            total_p = max(1, (self.total_items + items_p - 1) // items_p)

        self._paging_can_derive = self._can_derive_page_urls(self_url, next_url, prev_url)
        if self._paging_can_derive:
            first_index = 0 if self._paging_zero_based else 1
            if not first_url:
                first_url = self._derive_server_url(self_url, first_index)
            if not last_url and total_p:
                last_index = (total_p - 1) if self._paging_zero_based else total_p
                last_url = self._derive_server_url(self_url, last_index)

        has_any = any([first_url, prev_url, next_url, last_url])
        if not has_any:
            self.paging_bar.visible = False
            self.paging_status.value = ""
            return

        self.paging_bar.visible = True
        self.paging_row.controls.clear()

        def nav_btn(label: str, url: Optional[str], disabled: bool = False):
            def _go(_):
                self._set_paging_busy(True)
                logger.debug(f"paging nav click label={label} url={url}")
                self._page.run_task(self._deferred_paging_navigate, url)
            return ft.TextButton(
                label,
                # Paging within the same feed: do not create a new breadcrumb entry.
                on_click=_go if url and not disabled else None,
                disabled=(url is None) or disabled,
                style=ft.ButtonStyle(padding=2),
            )

        # Spinner is always present (just toggled visible) to avoid layout jumps.
        self.paging_row.controls.append(self.paging_spinner)

        # Core controls: first/prev/next/last
        self.paging_row.controls.extend(
            [
                nav_btn("<<", first_url, disabled=(curr_p == (0 if self._paging_zero_based else 1))),
                nav_btn("<", prev_url),
                nav_btn(">", next_url),
                nav_btn(
                    ">>",
                    last_url,
                    disabled=(
                        total_p is not None
                        and curr_p
                        == ((total_p - 1) if self._paging_zero_based else total_p)
                    ),
                ),
            ]
        )

        # Status + optional "Go to page" when random-access is possible.
        if curr_p is not None:
            display_curr = curr_p + 1 if self._paging_zero_based else curr_p
            if total_p:
                self.paging_status.value = f"Page {display_curr} of {total_p}"
            else:
                self.paging_status.value = f"Page {display_curr}"
            if self._paging_can_derive:
                self.page_input.value = str(display_curr)
                self.paging_row.controls.extend([ft.VerticalDivider(width=1, color=COLORS.GREY_800), self.page_input])
        else:
            self.paging_status.value = ""

    def _can_derive_page_urls(self, self_url: str, next_url: Optional[str], prev_url: Optional[str]) -> bool:
        """Return True when we have high confidence we can derive arbitrary page URLs."""
        try:
            q = parse_qs(urlparse(self_url).query)
            if "page" in q or "currentPage" in q:
                return True
        except Exception:
            pass

        # If the server's own paging links only tweak the last numeric path segment, we can derive safely.
        for neighbor in [next_url, prev_url]:
            if not neighbor:
                continue
            try:
                a = urlparse(self_url)
                b = urlparse(neighbor)
                if (a.scheme, a.netloc, a.query, a.params, a.fragment) != (b.scheme, b.netloc, b.query, b.params, b.fragment):
                    continue
                ap = a.path.rstrip("/").split("/")
                bp = b.path.rstrip("/").split("/")
                if len(ap) != len(bp) or len(ap) == 0:
                    continue
                if ap[:-1] != bp[:-1]:
                    continue
                if not ap[-1].isdigit() or not bp[-1].isdigit():
                    continue
                return True
            except Exception:
                continue
        return False

    def _derive_server_url(self, base_url: str, page_num: int) -> Optional[str]:
        """Derive a page URL from a known paged URL. Returns None when unsafe/unsupported."""
        try:
            parsed = urlparse(base_url)
        except Exception:
            return None

        # Prefer common query-based paging. Only overwrite params that already exist.
        try:
            query = parse_qs(parsed.query, keep_blank_values=True)
            for k in ["page", "currentPage"]:
                if k in query:
                    query[k] = [str(page_num)]
                    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))
        except Exception:
            pass

        # Replace last numeric path segment (common in OPDS implementations like .../1, .../2, etc.).
        try:
            parts = parsed.path.rstrip("/").split("/")
            if parts and parts[-1].isdigit():
                parts[-1] = str(page_num)
                new_path = "/".join(parts)
                return urlunparse(parsed._replace(path=new_path))
        except Exception:
            pass

        return None

    def _render_traditional_page(self, feed: OPDSFeed):
        self.main_content.controls.clear()
        token = self._load_token
        if feed.navigation:
            nav_links = []
            for n in feed.navigation:
                if n.title == "Start":
                    continue
                rel_str = "".join(n.rel or []) if isinstance(n.rel, list) else (n.rel or "")
                if "facet" in rel_str:
                    continue
                nav_links.append(n)

            if nav_links:
                nav = ft.Column(spacing=0)
                self.main_content.controls.append(
                    ft.Container(
                        content=nav,
                        border=ft.border.all(1, COLORS.OUTLINE_VARIANT),
                        border_radius=5,
                    )
                )
                # Render the first chunk immediately, then append the rest asynchronously.
                first = nav_links[:TRADITIONAL_RENDER_BATCH]
                for n in first:
                    nav.controls.append(
                        ft.ListTile(
                            title=ft.Text(n.title, size=14),
                            on_click=lambda e, u=n.href, t=n.title: self.on_navigate(
                                urljoin(self.api_client.profile.get_base_url(), u), t
                            ),
                            dense=True,
                        )
                    )
                rest = nav_links[TRADITIONAL_RENDER_BATCH:]
                if rest:
                    self._page.run_task(self._append_nav_items_batched, nav, rest, token)

        if feed.publications:
            grid = ft.Row(wrap=True, spacing=10, run_spacing=10)
            self.main_content.controls.append(grid)
            pubs = list(feed.publications)
            first = pubs[:TRADITIONAL_RENDER_BATCH]
            for p in first:
                grid.controls.append(self.create_pub_card(p, token=token))
            rest = pubs[TRADITIONAL_RENDER_BATCH:]
            if rest:
                self._page.run_task(self._append_pub_cards_batched, grid, rest, token)
        self.safe_content_update()

    async def _append_nav_items_batched(self, nav_col: ft.Column, items: List[Link], token: int):
        for i in range(0, len(items), TRADITIONAL_RENDER_BATCH):
            if token != self._load_token or not nav_col.page:
                return
            chunk = items[i : i + TRADITIONAL_RENDER_BATCH]
            for n in chunk:
                nav_col.controls.append(
                    ft.ListTile(
                        title=ft.Text(n.title, size=14),
                        on_click=lambda e, u=n.href, t=n.title: self.on_navigate(
                            urljoin(self.api_client.profile.get_base_url(), u), t
                        ),
                        dense=True,
                    )
                )
            self.safe_content_update()
            await asyncio.sleep(0)

    async def _append_pub_cards_batched(self, grid_row: ft.Row, pubs: List[Publication], token: int):
        for i in range(0, len(pubs), TRADITIONAL_RENDER_BATCH):
            if token != self._load_token or not grid_row.page:
                return
            chunk = pubs[i : i + TRADITIONAL_RENDER_BATCH]
            for p in chunk:
                grid_row.controls.append(self.create_pub_card(p, token=token))
            self.safe_content_update()
            await asyncio.sleep(0)

    # --- Infinite Scroll Logic ---

    def _render_infinite_page(self, feed: OPDSFeed, append: bool = False):
        if not append: self.main_content.controls.clear()
        else: self.main_content.controls.append(ft.Divider(color=COLORS.GREY_900, height=30))
        if feed.navigation:
            nav = ft.Column([ft.ListTile(title=ft.Text(n.title, size=14), on_click=lambda e, u=n.href, t=n.title: self.on_navigate(urljoin(self.api_client.profile.get_base_url(), u), t), dense=True) for n in feed.navigation if n.title not in ["Publishers", "Series", "Issues", "Folders", "Story Arcs", "Start"] and "facet" not in (n.rel if isinstance(n.rel, str) else "".join(n.rel or []))])
            if nav.controls: self.main_content.controls.append(ft.Container(content=nav, border=ft.border.all(1, COLORS.OUTLINE_VARIANT), border_radius=5))
        if feed.publications:
            grid = ft.Row(wrap=True, spacing=10, run_spacing=10)
            for p in feed.publications: grid.controls.append(self.create_pub_card(p))
            self.main_content.controls.append(grid)
        self.paging_status.value = f"Showing {len(self.items_buffer)} of {self.total_items} items"
        if self.footer not in self.main_content.controls: self.main_content.controls.append(self.footer)
        self.safe_content_update()

    async def load_next_infinite_page(self):
        if not self.next_url or self.is_loading_more: return
        self.is_loading_more = True; self.footer_loading.visible = True; self.safe_update()
        try:
            feed = await self.opds_client.get_feed(self.next_url)
            self.next_url = self._find_rel_link(feed, "next", self.next_url)
            if self.is_pub_mode: self.items_buffer.extend(feed.publications or [])
            else: self.items_buffer.extend([n for n in (feed.navigation or []) if n.title != "Start"])
            self._render_infinite_page(feed, append=True)
        except: pass
        finally: self.is_loading_more = False; self.footer_loading.visible = False; self.safe_update()

    # --- Input Handlers ---

    def _on_scroll_event(self, e: ft.OnScrollEvent):
        method = self.config_manager.get_scroll_method()
        if self.is_dashboard:
            return
        # Disable "special" mouse wheel handling in viewport mode. Use buttons/keyboard to page.
        if method == "infinite":
            if self.next_url and not self.is_loading_more and e.pixels >= e.max_scroll_extent - 800:
                self._page.run_task(self.load_next_infinite_page)

    def _on_window_resize(self, e):
        # Page resize can fire before this view is mounted or after it is replaced.
        if not self.page:
            return
        if self.config_manager.get_scroll_method() == "viewport" and not self.is_dashboard and self.current_url:
            self._render_viewport_screen()

    def handle_keyboard(self, e: ft.KeyboardEvent):
        method = self.config_manager.get_scroll_method()
        if method == "viewport" and not self.is_dashboard:
            if e.key in ["Arrow Right", "Page Down", " "]: self.next_viewport_screen()
            elif e.key in ["Arrow Left", "Page Up"]: self.prev_viewport_screen()
            elif e.key == "Home": self.jump_to_viewport_offset(0)
            elif e.key == "End": self.jump_to_viewport_offset((self.total_viewport_pages - 1) * self.items_per_screen)

    def _get_self_url(self, pub: Publication) -> str:
        base = self.api_client.profile.get_base_url()
        for l in (pub.links or []):
            if l.rel == "self" or (isinstance(l.rel, list) and "self" in l.rel): return urljoin(base, l.href)
        return base

    async def _load_thumbnail_async(self, url: str, img_control: ft.Image, token: Optional[int] = None):
        try:
            if token is not None and token != self._load_token:
                return
            # Limit concurrent thumbnail fetch/decode to keep paging responsive on large pages.
            if not hasattr(self, "_thumb_sem"):
                self._thumb_sem = asyncio.Semaphore(8)
            async with self._thumb_sem:
                b64 = await self.image_manager.get_image_b64(url)
            if token is not None and token != self._load_token:
                return
            if b64:
                img_control.src = data_url_from_b64(b64, guess_mime_from_url(url))
                try:
                    if img_control.page:
                        img_control.update()
                except:
                    pass
            return
        except: pass

    def _schedule_thumbnail_refresh(self, token: Optional[int]):
        if token is not None and token != self._load_token:
            return
        if not self.main_content.page:
            return

        now = time.monotonic()
        # Push the refresh out slightly to allow more thumbnails to accumulate.
        self._thumb_refresh_deadline = max(self._thumb_refresh_deadline, now + 0.05)
        if self._thumb_refresh_task and not self._thumb_refresh_task.done():
            return

        async def _runner(expected_token: int):
            try:
                while True:
                    if expected_token != self._load_token:
                        return
                    delay = self._thumb_refresh_deadline - time.monotonic()
                    if delay > 0:
                        await asyncio.sleep(delay)
                    else:
                        break
                if expected_token == self._load_token and self.main_content.page:
                    self.safe_content_update()
            except Exception:
                pass

        self._thumb_refresh_task = self._page.run_task(_runner, self._load_token)

    def _find_rel_link(self, feed: OPDSFeed, rel_target: str, base_url: str) -> Optional[str]:
        if not feed.links: return None
        for link in feed.links:
            rel = link.rel
            if (isinstance(rel, str) and rel == rel_target) or (isinstance(rel, list) and rel_target in rel): return urljoin(base_url, link.href)
        return None

    def _find_rel_link_any(self, feed: OPDSFeed, rel_targets: List[str], base_url: str) -> Optional[str]:
        for rel in rel_targets:
            u = self._find_rel_link(feed, rel, base_url)
            if u:
                return u
        return None

    def _setup_facets(self, feed: OPDSFeed):
        facet_groups = []
        if hasattr(feed, 'facets') and feed.facets: facet_groups.extend(feed.facets)
        if feed.groups:
            for group in feed.groups:
                if group.navigation and any("facet" in (n.rel if isinstance(n.rel, str) else "".join(n.rel or [])) for n in group.navigation): facet_groups.append(group)
        self.facet_menu.items.clear()
        if not facet_groups: self.facet_menu.visible = False; return
        self.facet_menu.visible = True
        for group in facet_groups:
            # Handle both dicts (from feed.facets) and Pydantic models (from feed.groups)
            is_dict = isinstance(group, dict)
            metadata = group.get("metadata") if is_dict else getattr(group, "metadata", None)
            title = "Filter"
            if metadata:
                title = metadata.get("title") if isinstance(metadata, dict) else getattr(metadata, "title", "Filter")
            
            self.facet_menu.items.append(ft.PopupMenuItem(content=ft.Text(title), disabled=True))
            
            links = []
            if is_dict:
                links = group.get("navigation") or group.get("links") or []
            else:
                links = group.navigation or group.links or []
                
            for link in links:
                l_is_dict = isinstance(link, dict)
                l_title = link.get("title", "Option") if l_is_dict else getattr(link, "title", "Option")
                l_href = link.get("href") if l_is_dict else getattr(link, "href", None)
                if l_href:
                    self.facet_menu.items.append(ft.PopupMenuItem(content=ft.Text(f"  {l_title}"), on_click=lambda e, u=l_href, t=l_title: self.on_navigate(urljoin(self.api_client.profile.get_base_url(), u), t)))

    async def execute_search(self, e):
        pass
