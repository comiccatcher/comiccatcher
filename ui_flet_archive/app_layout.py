import flet as ft
import os
from pathlib import Path
from config import ConfigManager
from ui.views.servers import ServersView
from ui.views.settings import SettingsView
from ui.views.browser import BrowserView
from ui.views.library import LocalLibraryView
from ui.views.library_detail import LocalComicDetailView
from ui.views.local_reader import LocalReaderView
from ui.views.detail import DetailView
from ui.views.reader import ReaderView
from ui.views.downloads import DownloadsView
from api.download_manager import DownloadManager
from api.opds_v2 import OPDS2Client
from api.image_manager import ImageManager
from logger import get_logger
from ui.snack import show_snack
from urllib.parse import urljoin

logger = get_logger("ui.layout")

COLORS = getattr(ft, "colors", ft.Colors)

class AppLayout(ft.Row):
    def __init__(self, page: ft.Page, config_manager: ConfigManager):
        super().__init__()
        # Do not assign to Control.page (Flet sets it when mounted). Store a reference separately.
        self._page = page
        self.config_manager = config_manager
        self.expand = True

        # --- Managers (Shared) ---
        self.api_client = None
        self.opds_client = None
        self.image_manager = None
        self.download_manager = None

        # --- History Management ---
        self.history = [] 
        self.current_index = -1

        # --- Shared Header Components ---
        self.breadcrumb_row = ft.Row(spacing=5, vertical_alignment=ft.CrossAxisAlignment.CENTER, wrap=True, expand=True)
        self.debug_url_text = ft.Text("", size=10, color=COLORS.SECONDARY, italic=True, expand=True)
        self.history_counter = ft.Text("", size=10, color=COLORS.BLUE_200, weight=ft.FontWeight.BOLD)
        
        self.debug_row = ft.Row([
            self.history_counter,
            ft.VerticalDivider(width=1, color=COLORS.GREY_800),
            self.debug_url_text,
            ft.IconButton(icon=ft.Icons.COPY, icon_size=12, tooltip="Copy URL", on_click=lambda _: self._page.set_clipboard(self.debug_url_text.value)),
            ft.IconButton(icon=ft.Icons.TERMINAL, icon_size=12, tooltip="Show Recent Logs", on_click=self._show_logs_dialog)
        ], visible=False, spacing=10)

        self.refresh_button = ft.IconButton(icon=ft.Icons.REFRESH, icon_size=20, tooltip="Refresh", on_click=self.on_manual_refresh)

        self.top_header = ft.Column([
            self.debug_row,
            ft.Row([self.breadcrumb_row, self.refresh_button], alignment=ft.MainAxisAlignment.START)
        ], spacing=5)

        # --- Views ---
        self.servers_view = ServersView(self._page, self.config_manager, self.on_profile_selected)
        self.settings_view = SettingsView(self._page, self.config_manager)
        self.browser_view = BrowserView(self._page, self.config_manager, self.on_open_detail, self.update_header, self.on_browser_load_complete, self.on_navigate_to_url)
        self.local_library_view = LocalLibraryView(self._page, self.config_manager, self.on_open_local_comic)
        # Readers are created lazily to avoid client-side crashes during initial mount.
        self.local_reader_view = None
        self.reader_view = None
        self.local_detail_view = LocalComicDetailView(self._page, self.on_back_to_local_library, self.on_read_local_comic)
        self.detail_view = DetailView(self._page, self.on_back_to_browser, self.on_read_book, self.on_navigate_to_url, self.update_header, self.on_detail_load_complete, self.on_start_download, self.on_open_detail)
        self.downloads_view = None
        
        self.content_container = ft.Container(content=self.servers_view, expand=True, alignment=ft.alignment.top_left)
        
        self.main_content_area = ft.Column([
            ft.Container(content=self.top_header, padding=ft.padding.only(left=20, right=20, top=10)),
            ft.Container(content=self.content_container, expand=True)
        ], expand=True, spacing=0)

        self.rail = ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=100,
            destinations=[
                ft.NavigationRailDestination(icon=ft.Icons.DNS_OUTLINED, selected_icon=ft.Icons.DNS, label="Servers"),
                ft.NavigationRailDestination(icon=ft.Icons.SETTINGS_OUTLINED, selected_icon=ft.Icons.SETTINGS, label="Settings"),
                ft.NavigationRailDestination(icon=ft.Icons.LIBRARY_BOOKS_OUTLINED, selected_icon=ft.Icons.LIBRARY_BOOKS, label="Browser"),
                ft.NavigationRailDestination(icon=ft.Icons.FOLDER_OUTLINED, selected_icon=ft.Icons.FOLDER, label="Library"),
                ft.NavigationRailDestination(icon=ft.Icons.DOWNLOAD_OUTLINED, selected_icon=ft.Icons.DOWNLOAD, label="Downloads"),
            ],
            on_change=self.on_nav_change,
        )

        self.vertical_divider = ft.VerticalDivider(width=1)
        self.controls = [self.rail, self.vertical_divider, self.main_content_area]
        self._page.on_keyboard_event = self.on_keyboard

    def on_profile_selected(self, profile):
        self.rail.selected_index = 2 # Switch to Browser
        self.top_header.visible = True
        self.history.clear()
        self.current_index = -1
        from api.client import APIClient
        self.api_client = APIClient(profile)
        self.opds_client = OPDS2Client(self.api_client)
        self.image_manager = ImageManager(self.api_client)
        self.download_manager = DownloadManager(self.api_client, download_dir=self.config_manager.get_library_dir())
        self.browser_view.load_profile(profile)
        self.browser_view.image_manager = self.image_manager
        self.downloads_view = DownloadsView(self._page, self.download_manager)
        self.content_container.content = self.browser_view
        self._page.update()
        base_url = profile.url
        start_url = base_url if "opds" in base_url.lower() else urljoin(base_url, "/codex/opds/v2.0/")
        self.on_navigate_to_url(start_url, title=profile.name)

    def on_navigate_to_url(self, url, title="Loading...", replace: bool = False, keep_title: bool = False):
        """
        Navigate browser to a URL.
        - replace=True updates the current history entry instead of pushing a new breadcrumb.
        - keep_title=True preserves the current breadcrumb title (useful for paging within the same feed).
        """
        if replace and self.current_index >= 0 and self.history[self.current_index]["type"] == "browser":
            entry = self.history[self.current_index]
            entry["url"] = url
            if not keep_title:
                entry["title"] = title
            self.content_container.content = self.browser_view
            self.update_header()
            self._page.run_task(self.browser_view.load_feed, url, entry["title"], False)
            return

        if self.current_index < len(self.history) - 1:
            del self.history[self.current_index + 1:]
        self.history.append({"type": "browser", "title": title, "url": url, "pub": None})
        self.current_index = len(self.history) - 1
        self.content_container.content = self.browser_view
        self.update_header()
        self._page.run_task(self.browser_view.load_feed, url, title, False)

    def on_browser_load_complete(self, url, title):
        if self.current_index >= 0 and self.history[self.current_index]["url"] == url:
            self.history[self.current_index]["title"] = title
            self.update_header()

    def on_open_detail(self, pub, base_url):
        if self.current_index < len(self.history) - 1:
            del self.history[self.current_index + 1:]
        self.history.append({"type": "detail", "title": pub.metadata.title, "url": base_url, "pub": pub})
        self.current_index = len(self.history) - 1
        self.content_container.content = self.detail_view
        self.update_header()
        self.detail_view.load_publication(pub, base_url, self.api_client, self.opds_client, self.image_manager, self.history)

    def on_detail_load_complete(self, url, title, full_pub=None):
        if self.current_index >= 0 and self.history[self.current_index]["url"] == url:
            self.history[self.current_index]["title"] = title
            if full_pub: self.history[self.current_index]["pub"] = full_pub
            self.update_header()

    def on_jump_to_history(self, index):
        del self.history[index + 1:]
        self.current_index = index
        entry = self.history[index]
        if entry["type"] == "browser":
            self.content_container.content = self.browser_view
            self.update_header()
            self._page.run_task(self.browser_view.load_feed, entry["url"], entry["title"], False)
        else:
            self.content_container.content = self.detail_view
            self.update_header()
            self.detail_view.load_publication(entry["pub"], entry["url"], self.api_client, self.opds_client, self.image_manager, self.history)

    def on_manual_refresh(self, e):
        if self.current_index < 0: return
        entry = self.history[self.current_index]
        if entry["type"] == "browser":
            self._page.run_task(self.browser_view.load_feed, entry["url"], entry["title"], True)
        else:
            self.detail_view.load_publication(entry["pub"], entry["url"], self.api_client, self.opds_client, self.image_manager, self.history, True)

    def on_back_to_browser(self):
        for i in range(self.current_index - 1, -1, -1):
            if self.history[i]["type"] == "browser":
                self.on_jump_to_history(i)
                return
        self.rail.selected_index = 0
        self.on_nav_change(None)

    def on_start_download(self, pub, url):
        if self.download_manager:
            import hashlib
            book_id = pub.metadata.identifier or hashlib.md5(url.encode()).hexdigest()
            self._page.run_task(self.download_manager.start_download, book_id, pub.metadata.title, url)
            show_snack(self._page, f"Added to Downloads: {pub.metadata.title}")

    def update_header(self, *args, **kwargs):
        is_debug = os.getenv("DEBUG") == "1"
        self.debug_row.visible = is_debug
        if self.current_index >= 0:
            entry = self.history[self.current_index]
            self.debug_url_text.value = entry["url"]
            self.history_counter.value = f"[{self.current_index + 1}/{len(self.history)}]"
        self.breadcrumb_row.controls.clear()
        for i in range(len(self.history)):
            entry = self.history[i]
            if i != self.current_index:
                self.breadcrumb_row.controls.append(ft.TextButton(entry["title"], on_click=lambda e, idx=i: self.on_jump_to_history(idx), style=ft.ButtonStyle(padding=5)))
                self.breadcrumb_row.controls.append(ft.Icon(ft.Icons.CHEVRON_RIGHT, size=16, color=COLORS.GREY_700))
            else:
                self.breadcrumb_row.controls.append(ft.Text(entry["title"], size=16, weight=ft.FontWeight.BOLD, color=COLORS.BLUE_200))
        try: self._page.update()
        except: pass

    def _show_logs_dialog(self, e):
        try:
            with open("comiccatcher.log", "r") as f:
                log_text = "".join(f.readlines()[-30:])
        except: log_text = "Could not read log file."
        self._page.dialog = ft.AlertDialog(title=ft.Text("System Logs"), content=ft.TextField(value=log_text, multiline=True, read_only=True, text_size=10, min_lines=15, max_lines=30), actions=[ft.TextButton("Close", on_click=lambda _: setattr(self._page.dialog, "open", False) or self._page.update())])
        self._page.dialog.open = True
        self._page.update()

    def on_nav_change(self, e):
        # 0: Servers, 1: Settings, 2: Browser, 3: Library, 4: Downloads
        self.top_header.visible = (self.rail.selected_index in (2, 4))
        if self.rail.selected_index == 0: self.content_container.content = self.servers_view
        elif self.rail.selected_index == 1: self.content_container.content = self.settings_view
        elif self.rail.selected_index == 2:
            self.content_container.content = self.browser_view
            if not self.history: self.top_header.visible = False
        elif self.rail.selected_index == 3:
            self.content_container.content = self.local_library_view
            self.local_library_view.refresh()
        elif self.rail.selected_index == 4:
            if not self.downloads_view:
                show_snack(self._page, "Select a server profile first!")
                self.rail.selected_index = 0
            else: self.content_container.content = self.downloads_view
        self._page.update()

    def on_open_local_comic(self, path):
        self.rail.selected_index = 3
        self.top_header.visible = False
        self.content_container.content = self.local_detail_view
        self.local_detail_view.load_path(Path(path))
        self._page.update()

    def on_read_local_comic(self, path: Path):
        p = Path(path)
        ext = p.suffix.lower()
        if ext != ".cbz":
            show_snack(self._page, f"Local reading not supported for {ext} yet (CBZ only for now).", text_color=COLORS.ERROR)
            return
        if self.local_reader_view is None:
            self.local_reader_view = LocalReaderView(self._page, self.on_exit_local_reader)
        self.rail.visible = False
        self.vertical_divider.visible = False
        self.top_header.visible = False
        self.main_content_area.controls[1].padding = 0
        self.content_container.content = self.local_reader_view
        self.local_reader_view.load_cbz(p)
        self._page.update()

    def on_back_to_local_library(self):
        self.rail.selected_index = 3
        self.top_header.visible = False
        self.content_container.content = self.local_library_view
        self.local_library_view.refresh()
        self._page.update()

    def on_read_book(self, pub, manifest_url):
        self.rail.visible = False
        self.vertical_divider.visible = False
        self.top_header.visible = False
        self.main_content_area.controls[1].padding = 0
        if self.reader_view is None:
            self.reader_view = ReaderView(self._page, None, self.on_exit_reader)
        # Configure reader before mounting to avoid client-side render glitches.
        self.reader_view.api_client = self.api_client
        self.reader_view.visible = True
        self.reader_view.load_manifest(pub, manifest_url)
        self.content_container.content = self.reader_view
        self._page.update()

    def on_exit_reader(self):
        self.rail.visible = True
        self.vertical_divider.visible = True
        self.top_header.visible = True
        self.main_content_area.controls[1].padding = 20
        if self.reader_view:
            self.reader_view.visible = False
        self.content_container.content = self.detail_view
        self._page.update()

    def on_exit_local_reader(self):
        self.rail.visible = True
        self.vertical_divider.visible = True
        self.top_header.visible = False
        self.main_content_area.controls[1].padding = ft.padding.only(left=20, right=20, top=10, bottom=20)
        self.content_container.content = self.local_detail_view
        self._page.update()

    def on_keyboard(self, e):
        if self.reader_view and self.content_container.content == self.reader_view: self.reader_view.handle_keyboard(e)
        elif self.local_reader_view and self.content_container.content == self.local_reader_view: self.local_reader_view.handle_keyboard(e)
        elif self.content_container.content == self.browser_view: self.browser_view.handle_keyboard(e)
