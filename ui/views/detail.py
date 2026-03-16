import flet as ft
import os
import traceback
import uuid
from models.opds import Publication, Contributor
from urllib.parse import urljoin
from api.image_manager import ImageManager
from logger import get_logger
from typing import List, Union, Any, Optional
from ui.snack import show_snack
from ui.image_data import TRANSPARENT_DATA_URL, data_url_from_b64, guess_mime_from_url

logger = get_logger("ui.detail")

COLORS = getattr(ft, "colors", ft.Colors)
SURFACE_VARIANT = getattr(COLORS, "SURFACE_VARIANT", getattr(COLORS, "SURFACE_CONTAINER", COLORS.SURFACE))

class DetailView(ft.Column):
    def __init__(self, page: ft.Page, on_back, on_read, on_navigate, on_update_header, on_load_complete, on_start_download, on_open_detail):
        super().__init__()
        # Store a reference; do not assign to Control.page.
        self._page = page
        self.on_back_callback = on_back
        self.on_read = on_read
        self.on_navigate = on_navigate
        self.on_update_header = on_update_header
        self.on_load_complete = on_load_complete
        self.on_start_download = on_start_download
        self.on_open_detail = on_open_detail
        
        self.api_client = None
        self.opds_client = None
        self.image_manager = None
        self.expand = True
        self.scroll = ft.ScrollMode.AUTO
        
        self.loading_indicator = ft.ProgressBar(visible=False)
        self.content_container = ft.Container(expand=True, padding=ft.padding.only(bottom=20))
        
        self.controls = [
            self.loading_indicator,
            self.content_container
        ]
        
        self._current_pub = None
        self._current_base_url = None
        self._last_cover_b64 = None
        self._history = []
        self._active_load_id = None

    def _safe_update(self):
        try:
            if self.page:
                self.update()
        except:
            pass

    def load_publication(self, pub: Publication, base_url: str, api_client, opds_client, image_manager, history, force_refresh: bool = False):
        self.api_client = api_client
        self.opds_client = opds_client
        # Reuse shared ImageManager when provided (keeps cache consistent across views).
        self.image_manager = image_manager or ImageManager(self.api_client)
        self._current_pub = pub
        self._current_base_url = base_url
        self._history = history
        self._last_cover_b64 = None
        self._active_load_id = str(uuid.uuid4())
        
        self.loading_indicator.visible = True
        self._safe_update()
        
        # Initial render from feed data
        self._render_details(pub, base_url, None)
        
        # Check if this is already a full manifest and not forcing refresh
        if not force_refresh and pub.readingOrder and len(pub.readingOrder) > 0:
            logger.debug(f"Publication '{pub.metadata.title}' already has manifest data.")
            self.loading_indicator.visible = False
            self._safe_update()
            return

        # Start background fetch for full manifest
        self._page.run_task(self._fetch_full_metadata, pub, base_url, self._active_load_id, force_refresh)

    async def _fetch_full_metadata(self, pub: Publication, base_url: str, load_id: str, force_refresh: bool = False):
        manifest_url = None
        # Robust manifest discovery
        for link in pub.links:
            if link.type in ["application/webpub+json", "application/divina+json"]:
                manifest_url = link.href
                break
            if link.rel == "http://opds-spec.org/acquisition" and link.type and "json" in link.type:
                manifest_url = link.href
                break
        
        if manifest_url and load_id == self._active_load_id:
            try:
                if not manifest_url.startswith("http"):
                    manifest_url = urljoin(base_url, manifest_url)
                
                logger.info(f"Fetching manifest (force={force_refresh}): {manifest_url}")
                full_pub = await self.opds_client.get_publication(manifest_url, force_refresh=force_refresh)
                
                if load_id == self._active_load_id:
                    # SMART MERGE: Keep existing data if manifest is thinner
                    if not full_pub.images and pub.images: full_pub.images = pub.images
                    if not full_pub.metadata.description and pub.metadata.description: 
                        full_pub.metadata.description = pub.metadata.description
                    
                    self._current_pub = full_pub
                    self._render_details(full_pub, base_url, manifest_url)
                    self.on_load_complete(base_url, full_pub.metadata.title, full_pub)
                    logger.info("Metadata successfully upgraded from manifest.")
            except Exception as e:
                logger.error(f"Error upgrading metadata from {manifest_url}: {e}\n{traceback.format_exc()}")
        
        if load_id == self._active_load_id:
            self.loading_indicator.visible = False
            self._safe_update()

    def _render_details(self, pub: Publication, base_url: str, manifest_url: str):
        m = pub.metadata
        self.on_update_header() # Trigger layout refresh
        
        image_url = self._get_image_url(pub)
        if image_url and not image_url.startswith("http"):
            image_url = urljoin(self.api_client.profile.get_base_url(), image_url)

        if self._last_cover_b64:
            mime = guess_mime_from_url(image_url or "")
            img_control = ft.Image(src=data_url_from_b64(self._last_cover_b64, mime), width=300, fit=ft.BoxFit.CONTAIN, border_radius=10)
        else:
            img_control = ft.Image(src=TRANSPARENT_DATA_URL, width=300, fit=ft.BoxFit.CONTAIN, border_radius=10)
            if image_url:
                self._page.run_task(self._load_cover_async, image_url, img_control)
        
        img_col = ft.Container(content=img_control, width=300, alignment=ft.Alignment.TOP_CENTER)

        # Title & Series
        title_section = ft.Column([ft.Text(m.title, size=28, weight=ft.FontWeight.BOLD)], spacing=2)
        if m.subtitle: title_section.controls.append(ft.Text(m.subtitle, size=18, italic=True, color=COLORS.ON_SURFACE_VARIANT))

        belongs_to = m.belongsTo or pub.belongsTo
        series_info = []
        series_name = None
        if belongs_to:
            series = belongs_to.get("series")
            if series:
                s_obj = series[0] if isinstance(series, list) else series
                series_name = s_obj.get("name")
                pos = s_obj.get("position")
                if not m.title.lower().startswith(series_name.lower()):
                    series_str = f"Series: {series_name}"
                    if pos: series_str += f" #{pos}"
                    series_info.append(ft.Text(series_str, size=16, weight=ft.FontWeight.W_500))
                elif pos:
                    series_info.append(ft.Text(f"Issue #{pos}", size=16, weight=ft.FontWeight.W_500))

        # Action Buttons
        download_url = next((urljoin(base_url, l.href) for l in pub.links if l.rel == "http://opds-spec.org/acquisition" or (l.type and ("zip" in l.type or "cbz" in l.type))), None)
        action_buttons = ft.Row([
            ft.ElevatedButton("Read Now", icon=ft.Icons.MENU_BOOK, on_click=lambda e: self.on_read(pub, manifest_url or base_url)),
            ft.OutlinedButton("Download CBZ", icon=ft.Icons.DOWNLOAD, disabled=not download_url, on_click=lambda e: self.on_start_download(pub, download_url))
        ], spacing=10)

        # Credits & Subjects
        role_map = {"author": "Author", "artist": "Artist", "penciler": "Penciler", "inker": "Inker", "colorist": "Colorist", "letterer": "Letterer", "editor": "Editor", "translator": "Translator", "contributor": "Contributor"}
        credit_controls = [self._build_clickable_group(label, getattr(m, attr), base_url) for attr, label in role_map.items() if getattr(m, attr, None)]
        
        pub_info = []
        if m.publisher: pub_info.append(ft.Text(f"Publisher: {self._format_contributors(m.publisher)}", size=14))
        if m.published: pub_info.append(ft.Text(f"Published: {m.published}", size=14))

        subject_section = ft.Column([ft.Text("Subjects", size=16, weight=ft.FontWeight.BOLD), self._build_clickable_subjects(m.subject, base_url)], visible=m.subject is not None)
        summary_section = ft.Column([ft.Text("Summary", size=18, weight=ft.FontWeight.BOLD), ft.Text(m.description or "No description available.", size=14)], spacing=10)

        # Bottom Carousels
        carousels = ft.Column(spacing=20)
        if belongs_to:
            for rel_type in ["series", "collection"]:
                items = belongs_to.get(rel_type, [])
                if not isinstance(items, list): items = [items]
                for item in items:
                    links = item.get("links", [])
                    for link in links:
                        l_href = link.get("href") if isinstance(link, dict) else getattr(link, 'href', None)
                        if not l_href: continue
                        label = item.get("name") or rel_type.capitalize()
                        if rel_type == "series": label = f"More from {label}"
                        carousels.controls.append(
                            ft.Column([
                                ft.Row([
                                    ft.Text(label, size=18, weight=ft.FontWeight.BOLD),
                                    ft.TextButton("See All", on_click=lambda e, u=l_href, t=label: self.on_navigate(urljoin(base_url, u), t), style=ft.ButtonStyle(padding=0))
                                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                                self._build_horizontal_carousel(l_href, base_url)
                            ], spacing=5)
                        )

        info_col = ft.Column([
            action_buttons,
            ft.Column(series_info, spacing=2),
            ft.Divider(height=20, color=COLORS.OUTLINE_VARIANT),
            ft.Column(credit_controls, spacing=5),
            ft.Column(pub_info, spacing=2),
            subject_section,
            ft.Divider(height=20, color=COLORS.OUTLINE_VARIANT),
            summary_section,
            ft.Divider(height=20, color=COLORS.OUTLINE_VARIANT),
            carousels
        ], expand=True, spacing=15)

        self.content_container.content = ft.Row([
            img_col,
            ft.VerticalDivider(width=20, color=COLORS.TRANSPARENT),
            info_col
        ], vertical_alignment=ft.CrossAxisAlignment.START, expand=True)
        
        self._safe_update()

    def _build_clickable_group(self, label, contributors, base_url):
        items = contributors if isinstance(contributors, list) else [contributors]
        links_row = ft.Row(wrap=True, spacing=5)
        for item in items:
            name = item.name if hasattr(item, 'name') else (item.get("name") if isinstance(item, dict) else str(item))
            href = None
            links = item.get("links", []) if isinstance(item, dict) else (getattr(item, 'links', []) or [])
            for l in links:
                l_dict = l if isinstance(l, dict) else l.model_dump()
                if "opds" in l_dict.get("type", ""):
                    href = l_dict["href"]
                    break
            if href:
                links_row.controls.append(ft.TextButton(name, on_click=lambda e, u=href, t=name: self.on_navigate(urljoin(base_url, u), t), style=ft.ButtonStyle(padding=0)))
            else:
                links_row.controls.append(ft.Text(name, size=14))
        return ft.Row([ft.Text(f"{label}: ", size=14, weight=ft.FontWeight.BOLD), links_row], spacing=0)

    def _build_clickable_subjects(self, subjects, base_url):
        if not subjects: return ft.Container()
        items = subjects if isinstance(subjects, list) else [subjects]
        row = ft.Row(wrap=True, spacing=5)
        for s in items:
            name = s.get("name") if isinstance(s, dict) else str(s)
            href = None
            links = s.get("links", []) if isinstance(s, dict) else []
            for l in links:
                l_dict = l if isinstance(l, dict) else l.model_dump() if hasattr(l, 'model_dump') else {}
                if "opds" in l_dict.get("type", ""):
                    href = l_dict["href"]
                    break
            if href:
                row.controls.append(ft.Container(content=ft.Text(name, size=12), bgcolor=SURFACE_VARIANT, padding=ft.padding.symmetric(horizontal=10, vertical=5), border_radius=15, on_click=lambda e, u=href, t=name: self.on_navigate(urljoin(base_url, u), t)))
            else:
                row.controls.append(ft.Container(content=ft.Text(name, size=12), bgcolor=SURFACE_VARIANT, padding=ft.padding.symmetric(horizontal=10, vertical=5), border_radius=15))
        return row

    def _build_horizontal_carousel(self, url, base_url):
        carousel = ft.Row(scroll=ft.ScrollMode.AUTO, spacing=15)
        carousel.data = url
        full_url = urljoin(base_url, url)
        self._page.run_task(self._load_carousel_data, full_url, carousel)
        return ft.Container(content=carousel, height=220, padding=ft.padding.only(bottom=10))

    async def _load_carousel_data(self, url, row):
        try:
            feed = await self.opds_client.get_feed(url)
            pubs = feed.publications or []
            if not pubs and feed.groups:
                for g in feed.groups:
                    if g.publications: pubs.extend(g.publications)
            
            if not pubs:
                row.controls.append(ft.Text("No other items found.", size=12, italic=True))
                row.update()
                return

            base_server_url = self.api_client.profile.get_base_url()
            for pub in pubs[:15]:
                img_url = self._get_image_url(pub)
                if img_url and not img_url.startswith("http"):
                    img_url = urljoin(base_server_url, img_url)
                
                mini_img = ft.Image(src=TRANSPARENT_DATA_URL, height=160, fit=ft.BoxFit.CONTAIN, border_radius=5)
                
                row.controls.append(
                    ft.Container(
                        content=ft.Column([
                            mini_img,
                            ft.Text(pub.metadata.title, size=11, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS, text_align=ft.TextAlign.CENTER)
                        ], spacing=5, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        on_click=lambda e, p=pub: self.on_open_detail(p, url),
                        width=120,
                        tooltip=pub.metadata.title
                    )
                )
                if img_url: self._page.run_task(self._load_cover_async, img_url, mini_img)
                
            row.update()
        except Exception as e:
            logger.error(f"Carousel error: {e}")

    def _get_image_url(self, pub: Publication) -> Optional[str]:
        if pub.images: return pub.images[0].href
        if pub.links:
            for link in pub.links:
                if "image" in (link.rel or "") or (link.type and "image/" in link.type):
                    return link.href
        return None

    def _format_contributors(self, val: Any) -> str:
        if not val: return ""
        if isinstance(val, str): return val
        
        def get_name(obj):
            if isinstance(obj, str): return obj
            if hasattr(obj, "name"): return obj.name
            if isinstance(obj, dict): return obj.get("name", "")
            return str(obj)

        if isinstance(val, list):
            names = [get_name(item) for item in val]
            return ", ".join(filter(None, names))
        return get_name(val)

    async def _load_cover_async(self, url: str, img_control: ft.Image):
        try:
            b64 = await self.image_manager.get_image_b64(url)
            if b64:
                img_control.src = data_url_from_b64(b64, guess_mime_from_url(url))
                if img_control.width == 300: self._last_cover_b64 = b64
                try:
                    img_control.update()
                except: pass
        except Exception as e:
            logger.error(f"Image load error: {e}")

    def start_download(self, pub, url):
        show_snack(self._page, f"Downloading: {pub.metadata.title}")
