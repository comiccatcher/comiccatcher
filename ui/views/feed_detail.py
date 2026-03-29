import asyncio
import traceback
import uuid
from pathlib import Path
from typing import List, Union, Any, Optional
from urllib.parse import urljoin

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QFrame, QProgressBar
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap
from ui.theme_manager import ThemeManager, UIConstants

from logger import get_logger
from api.image_manager import ImageManager
from api.progression import ProgressionSync
from models.opds import Publication, Contributor, Link
from ui.flow_layout import FlowLayout
from ui.image_data import TRANSPARENT_DATA_URL
from ui.views.base_detail import BaseDetailView
from ui.utils import format_artist_credits, format_publication_date, format_file_size, parse_opds_date

logger = get_logger("ui.feed_detail")

class ClickableBadge(QFrame):
    def __init__(self, text, on_click):
        super().__init__()
        self.on_click = on_click
        self.setObjectName("badge")
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(5, 2, 5, 2)
        self.label = QLabel(text)
        self.layout.addWidget(self.label)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reapply_theme()

    def reapply_theme(self):
        theme = ThemeManager.get_current_theme_colors()
        self.setStyleSheet(f"""
            QFrame#badge {{
                border-radius: 10px; 
                padding: 2px 5px; 
                border: 1px solid {theme['border']}; 
                background-color: {theme['bg_sidebar']};
            }}
            QFrame#badge:hover {{
                background-color: {theme['bg_item_hover']};
                border-color: {theme['accent']};
            }}
        """)
        self.label.setStyleSheet(f"font-size: 11px; border: none; color: {theme['text_main']};")

    def mousePressEvent(self, event):
        self.on_click()
        super().mousePressEvent(event)

class FeedDetailView(BaseDetailView):
    def __init__(self, config_manager, on_back, on_read, on_navigate, on_start_download, on_open_detail, image_manager: ImageManager, local_db=None):
        super().__init__(on_back, image_manager)
        self.config_manager = config_manager
        self.on_read = on_read
        self.on_navigate = on_navigate
        self.on_start_download = on_start_download
        self.on_open_detail = on_open_detail
        self.db = local_db
        
        self.api_client = None
        self.opds_client = None
        self.progression_sync = None
        
        self._current_pub = None
        self._current_base_url = None
        self._active_load_id = None
    def reapply_theme(self):
        super().reapply_theme()
        theme = ThemeManager.get_current_theme_colors()
        s = UIConstants.scale
        
        # Propagate to dynamic badges and buttons
        for badge in self.findChildren(ClickableBadge):
            badge.reapply_theme()
            
        for label in self.findChildren(QLabel):
            if label.objectName() == "badge_static":
                label.setStyleSheet(f"border-radius: {s(10)}px; padding: {s(2)}px {s(10)}px; font-size: {s(11)}px; border: {max(1, s(1))}px solid {theme['border']}; background-color: {theme['bg_sidebar']}; color: {theme['text_dim']};")
            elif label.objectName() == "carousel_header":
                label.setStyleSheet(f"font-size: {s(18)}px; font-weight: bold; margin-top: {s(20)}px; color: {theme['text_main']};")
            elif label.objectName() == "meta_label":
                label.setStyleSheet(f"font-weight: bold; color: {theme['text_dim']};")
                
        for btn in self.findChildren(QPushButton):
            if btn.objectName() == "see_all_button":
                btn.setStyleSheet(f"color: {theme['accent']}; font-weight: bold; background: transparent; border: none;")
            elif btn.objectName() == "link_button":
                btn.setStyleSheet(f"color: {theme['accent']}; text-align: left; background: transparent; border: none;")

    def load_publication(self, pub: Publication, base_url: str, api_client, opds_client, image_manager, context_pubs=None, history=None, force_refresh: bool = False):
        self.api_client = api_client
        self.opds_client = opds_client
        self.image_manager = image_manager
        self._context_pubs = context_pubs
        
        device_id = self.config_manager.get_device_id()
        self.progression_sync = ProgressionSync(api_client, device_id)
        
        self._current_pub = pub
        self._current_base_url = base_url
        self._active_load_id = str(uuid.uuid4())
        
        self.setUpdatesEnabled(False)
        try:
            self._clear_layout(self.content_layout)
            self.progress.setVisible(True)
            
            if not (pub.readingOrder and len(pub.readingOrder) > 0):
                asyncio.create_task(self._fetch_full_metadata(pub, base_url, self._active_load_id, force_refresh))
            else:
                self._render_details(pub, base_url)
                self.progress.setVisible(False)
                asyncio.create_task(self._fetch_progression(pub, base_url, self._active_load_id))
        finally:
            self.setUpdatesEnabled(True)

    async def _fetch_full_metadata(self, pub: Publication, base_url: str, load_id: str, force_refresh: bool = False):
        manifest_url = None
        for link in pub.links:
            if link.type in ["application/webpub+json", "application/divina+json"]:
                manifest_url = link.href
                break
        
        fetched_pub = pub
        if manifest_url and load_id == self._active_load_id:
            try:
                full_url = urljoin(base_url, manifest_url)
                full_pub = await self.opds_client.get_publication(full_url, force_refresh=force_refresh)
                
                if load_id == self._active_load_id:
                    if not full_pub.images and pub.images: full_pub.images = pub.images
                    if not full_pub.metadata.description and pub.metadata.description: 
                        full_pub.metadata.description = pub.metadata.description
                    fetched_pub = full_pub
            except Exception as e:
                logger.error(f"Error upgrading metadata: {e}")
        
        if load_id == self._active_load_id:
            self._current_pub = fetched_pub
            self.setUpdatesEnabled(False)
            try:
                self._render_details(fetched_pub, base_url)
            finally:
                self.setUpdatesEnabled(True)
            self.progress.setVisible(False)
            asyncio.create_task(self._fetch_progression(fetched_pub, base_url, load_id))

    async def _fetch_progression(self, pub: Publication, base_url: str, load_id: str):
        prog_url = None
        for link in pub.links:
            rels = [link.rel] if isinstance(link.rel, str) else (link.rel or [])
            if any(r in rels for r in ["http://librarysimplified.org/terms/rel/state", "http://www.cantook.com/api/progression", "http://readium.org/rel/progression"]):
                prog_url = urljoin(base_url, link.href)
                break
        
        if prog_url and load_id == self._active_load_id:
            try:
                data = await self.progression_sync.get_progression(prog_url)
                if data and load_id == self._active_load_id:
                    # Check for nested Readium Locator structure first
                    loc = data.get("locator", {}).get("locations", {})
                    pct = loc.get("progression")
                    pos = loc.get("position")
                    
                    # Fallback to flat structure
                    if pct is None:
                        pct = data.get("progression")
                    
                    if pct is not None:
                        self._update_progression_ui(float(pct), pub, pos)
            except Exception as e:
                logger.error(f"Error fetching progression: {e}")

    def _update_progression_ui(self, pct: float, pub: Publication, pos: int = None):
        if hasattr(self, 'progression_label'):
            total_pages = 0
            if pub.readingOrder:
                total_pages = len(pub.readingOrder)
            elif hasattr(pub.metadata, 'numberOfPages') and pub.metadata.numberOfPages:
                total_pages = int(pub.metadata.numberOfPages)
            
            theme = ThemeManager.get_current_theme_colors()
            dim_color = theme['text_dim']
            
            if total_pages > 0:
                if pos is not None and pos > 0:
                    current_page = pos
                else:
                    current_page = int(pct * total_pages) + 1
                
                current_page = min(current_page, total_pages)
                prog_text = f"Page {current_page} of {total_pages} ({int(pct*100)}%)"
                if self._file_size_str:
                    prog_text += f"&nbsp;&nbsp;&nbsp;•&nbsp;&nbsp;&nbsp;<span style='color: {dim_color};'>{self._file_size_str}</span>"
                self.progression_label.setText(prog_text)
                self._update_cover_progress(current_page, total_pages)
                
                # Update button text
                if current_page >= total_pages:
                    self.btn_read.setText("Read Again")
                elif current_page > 1 or pct > 0.01: # Use a small epsilon
                    self.btn_read.setText("Resume")
                else:
                    self.btn_read.setText("Read Now")
            else:
                prog_text = f"Progress: {int(pct*100)}%"
                if self._file_size_str:
                    prog_text += f"&nbsp;&nbsp;&nbsp;•&nbsp;&nbsp;&nbsp;<span style='color: {dim_color};'>{self._file_size_str}</span>"
                self.progression_label.setText(prog_text)
                if pct > 0.01:
                    self.btn_read.setText("Resume")

    async def _check_for_local_copy(self, pub: Publication, download_url: str):
        # We search by URL in the local DB
        row = await asyncio.to_thread(self.db.get_comic_by_url, download_url)
        if row:
            path_str = row["file_path"]
            if path_str:
                p = Path(path_str)
                if p.exists():
                    try:
                        size_bytes = p.stat().st_size
                        def format_size(num):
                            for unit in ['B', 'KB', 'MB', 'GB']:
                                if abs(num) < 1024.0:
                                    return f"{num:3.1f} {unit}"
                                num /= 1024.0
                            return f"{num:.1f} TB"
                        self._file_size_str = format_size(size_bytes)
                        # Refresh label if already showing something
                        theme = ThemeManager.get_current_theme_colors()
                        dim_color = theme['text_dim']
                        
                        txt = self.progression_label.text()
                        if txt:
                            if self._file_size_str not in txt:
                                # Replace plain dot with spaced dot and colored size
                                self.progression_label.setText(f"{txt}&nbsp;&nbsp;&nbsp;•&nbsp;&nbsp;&nbsp;<span style='color: {dim_color};'>{self._file_size_str}</span>")
                        else:
                            self.progression_label.setText(f"<span style='color: {dim_color};'>{self._file_size_str}</span>")
                    except:
                        pass

    def _on_delete_local(self, path: str):
        try:
            p = Path(path)
            if p.exists():
                p.unlink()
                logger.info(f"Deleted local file from detail view: {p}")
            
            if self.db:
                self.db.remove_comic(str(p))
                logger.info(f"Removed from local DB: {p}")
            
            # Refresh view (remove delete button/update UI) or go back
            self.on_back() 
        except Exception as e:
            logger.error(f"Error during online detail delete: {e}")

    def _render_details(self, pub: Publication, base_url: str):
        self.setUpdatesEnabled(False)
        try:
            info_layout = self._setup_main_info_layout()
            
            # Reset cover while loading
            self.cover_label.clear()
            self.cover_label.setText("Loading Cover...")
            
            m = pub.metadata
            
            self._add_title(m.title, m.subtitle)

            # Publisher and Pub Date line
            pub_val = m.publisher
            pub_name = None
            if isinstance(pub_val, list) and len(pub_val) > 0:
                p = pub_val[0]
                pub_name = p.name if hasattr(p, 'name') else (p.get("name") if isinstance(p, dict) else str(p))
            elif pub_val:
                pub_name = pub_val.name if hasattr(pub_val, 'name') else (pub_val.get("name") if isinstance(pub_val, dict) else str(pub_val))
            
            month, year = parse_opds_date(m.published)
            display_date = format_publication_date(month, year)

            pub_parts = []
            if pub_name: pub_parts.append(pub_name)
            if display_date: pub_parts.append(display_date)
            
            if pub_parts:
                line_text = " • ".join(pub_parts)
                pub_label = QLabel(line_text)
                theme = ThemeManager.get_current_theme_colors()
                pub_label.setStyleSheet(f"font-size: 14px; color: {theme['text_dim']}; margin-top: 2px;")
                self.info_layout.addWidget(pub_label)

            # Action Buttons
            manifest_url = next((urljoin(base_url, l.href) for l in pub.links if l.type in ["application/webpub+json", "application/divina+json"]), base_url)
            btn_read = self._add_read_button(lambda: self.on_read(pub, manifest_url, self._context_pubs), "Read Now")
            btn_read.setObjectName("primary_button")
            
            download_url = next((urljoin(base_url, l.href) for l in pub.links if l.rel == "http://opds-spec.org/acquisition" or (l.type and "cbz" in l.type)), None)
            if download_url:
                btn_down = QPushButton("Download")
                btn_down.setMinimumHeight(40)
                btn_down.clicked.connect(lambda: self.on_start_download(pub, download_url))
                self.actions_layout.insertWidget(1, btn_down)
                
                # Check if already downloaded
                self._file_size_str = None
                if self.db:
                    asyncio.create_task(self._check_for_local_copy(pub, download_url))

            # Progression & Page Count
            self._add_progression_label()
            
            total_pages = 0
            if hasattr(m, 'numberOfPages') and m.numberOfPages:
                total_pages = m.numberOfPages
            elif pub.readingOrder:
                total_pages = len(pub.readingOrder)
                
            if total_pages:
                self.progression_label.setText(f"Pages: {total_pages}")

            # Summary (Description)
            if m.description:
                self._add_description(m.description)
                
            # Cover
            img_url = self._get_image_url(pub)
            if img_url:
                asyncio.create_task(self._load_cover(urljoin(base_url, img_url)))

            # Metadata
            roles = {}
            role_map = {
                "author": "Author", "artist": "Artist", "penciler": "Penciller", 
                "inker": "Inker", "colorist": "Colorist", "letterer": "Letterer", 
                "editor": "Editor"
            }
            for attr, label in role_map.items():
                val = getattr(m, attr, None)
                if val:
                    # Collect for artist grouping
                    if isinstance(val, list):
                        names = [ (v.name if hasattr(v, 'name') else str(v)) for v in val ]
                        roles[label] = ", ".join(names)
                    else:
                        roles[label] = val.name if hasattr(val, 'name') else str(val)
            
            final_creds = format_artist_credits(roles)
            for cred in final_creds:
                if ":" in cred:
                    label, val = cred.split(":", 1)
                    # We keep them clickable if they were clickable before, but let's stick to simple display for now to match local
                    self._add_clickable_metadata(info_layout, label.strip(), roles.get(label.strip(), val.strip()), base_url)
            
            # Subjects
            if m.subject:
                self._add_subjects(info_layout, m.subject, base_url)

            self.info_layout.addStretch()

            # carousels
            self._add_carousels(pub, base_url)
        finally:
            self.setUpdatesEnabled(True)

    async def _load_cover(self, url: str):
        await self.image_manager.get_image_b64(url)
        full_path = self.image_manager._get_cache_path(url)
        if full_path.exists():
            pixmap = QPixmap(str(full_path))
            if not pixmap.isNull():
                self.cover_label.setPixmap(pixmap)

    def _get_image_url(self, pub: Publication) -> Optional[str]:
        if pub.images: return pub.images[0].href
        if pub.links:
            for link in pub.links:
                if "image" in (link.rel or "") or (link.type and "image/" in link.type):
                    return link.href
        return None

    def _add_clickable_metadata(self, layout, label, contributors, base_url):
        items = contributors if isinstance(contributors, list) else [contributors]
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(5)
        
        l_label = QLabel(f"<b>{label}:</b>")
        l_label.setFixedWidth(100)
        l_label.setObjectName("meta_label")
        row_layout.addWidget(l_label)
        
        flow_layout = FlowLayout(spacing=5)
        
        for item in items:
            name = item.name if hasattr(item, 'name') else (item.get("name") if isinstance(item, dict) else str(item))
            href = None
            links = item.get("links", []) if isinstance(item, dict) else (getattr(item, 'links', []) or [])
            for l in links:
                l_type = l.get("type", "") if isinstance(l, dict) else getattr(l, 'type', '') or ""
                if "opds" in l_type:
                    href = l.get("href") if isinstance(l, dict) else l.href
                    break
            
            if href:
                full_href = urljoin(base_url, href)
                btn = QPushButton(name)
                btn.setFlat(True)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setObjectName("link_button")
                btn.clicked.connect(lambda _, u=full_href, t=name: self.on_navigate(u, t))
                flow_layout.addWidget(btn)
            else:
                l = QLabel(name)
                flow_layout.addWidget(l)
        
        row_widget = QWidget()
        row_widget.setLayout(flow_layout)
        row_layout.addWidget(row_widget, 1)
        
        container = QWidget()
        container.setLayout(row_layout)
        layout.addWidget(container)

    def _add_subjects(self, layout, subject, base_url):
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(5)
        
        l_label = QLabel("<b>Subjects:</b>")
        l_label.setFixedWidth(100)
        l_label.setObjectName("meta_label")
        row_layout.addWidget(l_label)
        
        subj_widget = QWidget()
        subj_layout = FlowLayout(subj_widget, spacing=5)
        
        subjects = subject if isinstance(subject, list) else [subject]
        for s in subjects:
            name = s.get("name") if isinstance(s, dict) else str(s)
            href = None
            links = s.get("links", []) if isinstance(s, dict) else []
            for l in links:
                if "opds" in (l.get("type", "") if isinstance(l, dict) else getattr(l, 'type', '') or ""):
                    href = l.get("href") if isinstance(l, dict) else l.href
                    break
            
            if href:
                full_href = urljoin(base_url, href)
                badge = ClickableBadge(name, lambda u=full_href, t=name: self.on_navigate(u, t))
                subj_layout.addWidget(badge)
            else:
                l = QLabel(name)
                l.setObjectName("badge_static")
                l.setStyleSheet("border-radius: 10px; padding: 2px 10px; font-size: 11px; border: 1px solid rgba(128, 128, 128, 50); background-color: rgba(128, 128, 128, 20);")
                subj_layout.addWidget(l)
        
        row_layout.addWidget(subj_widget, 1)
        container = QWidget()
        container.setLayout(row_layout)
        layout.addWidget(container)

    def _add_carousels(self, pub: Publication, base_url: str):
        belongs_to = pub.metadata.belongsTo or pub.belongsTo
        if not belongs_to: return
        
        for rel_type in ["series", "collection"]:
            items = belongs_to.get(rel_type, [])
            if not isinstance(items, list): items = [items]
            for item in items:
                links = item.get("links", [])
                for link in links:
                    l_href = link.get("href") if isinstance(link, dict) else getattr(link, 'href', None)
                    if not l_href: continue
                    
                    label_text = item.get("name") or rel_type.capitalize()
                    if rel_type == "series": label_text = f"More from {label_text}"
                    
                    header = QHBoxLayout()
                    l_title = QLabel(label_text)
                    l_title.setObjectName("carousel_header")
                    header.addWidget(l_title)
                    header.addStretch()

                    full_href = urljoin(base_url, l_href)
                    btn_all = self.create_action_button(
                        "See All",
                        lambda _, u=full_href, t=label_text: self.on_navigate(u, t)
                    )
                    header.addWidget(btn_all)
                    self.content_layout.insertLayout(self.content_layout.count() - 1, header)
                    
                    from ui.components.base_ribbon import BaseCardRibbon
                    from ui.components.feed_card_delegate import FeedCardDelegate
                    from ui.components.feed_browser_model import FeedBrowserModel

                    # Use a horizontal ribbon-style list view
                    model = FeedBrowserModel()
                    delegate = FeedCardDelegate(self, self.image_manager, show_labels=True)
                    
                    view = BaseCardRibbon(self, show_labels=True)
                    view.setModel(model)
                    view.setItemDelegate(delegate)
                    view.update_ribbon_height()
                    view.clicked.connect(self._on_carousel_clicked)
                    
                    self.content_layout.insertWidget(self.content_layout.count() - 1, view)
                    self.reapply_theme()
                    
                    asyncio.create_task(self._load_carousel_data(full_href, model))

    def _on_carousel_clicked(self, index):
        from ui.components.feed_browser_model import FeedBrowserModel
        model = index.model()
        item = model.data(index, FeedBrowserModel.ItemDataRole)
        if item and item.raw_pub:
            self.on_open_detail(item.raw_pub, None)

    async def _load_carousel_data(self, url, model):
        try:
            from api.feed_reconciler import FeedReconciler
            feed = await self.opds_client.get_feed(url)
            
            # Use FeedReconciler to get FeedItems
            base_feed_url = self.api_client.profile.get_base_url()
            feed_page = FeedReconciler.reconcile(feed, base_feed_url)
            
            items = []
            for section in feed_page.sections:
                items.extend(section.items)
            
            if not items:
                # We don't have a good way to show "No items" in the model easily here without custom items
                # so we just leave it empty or could add a dummy item
                return

            model.update_total_count(len(items[:15]))
            model.set_items_for_page(1, items[:15])
            
        except Exception as e:
            logger.error(f"Carousel error: {e}")
