import asyncio
import traceback
import uuid
from pathlib import Path
from typing import List, Union, Any, Optional, Set, Tuple
from urllib.parse import urljoin

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QFrame, QProgressBar
)
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QPixmap
from comiccatcher.ui.theme_manager import ThemeManager, UIConstants

from comiccatcher.logger import get_logger
from comiccatcher.api.image_manager import ImageManager
from comiccatcher.api.progression import ProgressionSync
from comiccatcher.models.opds import Publication, Contributor, Link
from comiccatcher.models.feed_page import FeedItem
from comiccatcher.api.feed_reconciler import FeedReconciler
from comiccatcher.ui.flow_layout import FlowLayout
from comiccatcher.ui.image_data import TRANSPARENT_DATA_URL
from comiccatcher.ui.views.base_detail import BaseDetailView
from comiccatcher.ui.utils import format_artist_credits, format_publication_date, format_file_size, parse_opds_date
from comiccatcher.ui.components.base_ribbon import BaseCardRibbon
from comiccatcher.ui.components.feed_card_delegate import FeedCardDelegate
from comiccatcher.ui.components.feed_browser_model import FeedBrowserModel
from comiccatcher.ui.view_helpers import ViewportHelper

logger = get_logger("ui.feed_detail")

class Badge(QFrame):
    def __init__(self, text, on_click=None):
        super().__init__()
        self.on_click = on_click
        self.setFrameShape(QFrame.Shape.NoFrame)
        obj_name = "badge" if on_click else "badge_static"
        self.setObjectName(obj_name)

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(text)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.label)

        if on_click:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reapply_theme()

    def reapply_theme(self):
        theme = ThemeManager.get_current_theme_colors()
        s = UIConstants.scale
        is_clickable = self.on_click is not None
        obj_name = self.objectName()

        bg = theme['bg_sidebar'] if is_clickable else "rgba(128, 128, 128, 20)"
        border_color = theme['border'] if is_clickable else "rgba(128, 128, 128, 50)"

        self.setStyleSheet(f"""
            QFrame#{obj_name} {{
                border-radius: {s(10)}px;
                padding: {s(1)}px {s(10)}px;
                border: {max(1, s(1))}px solid {border_color};
                background-color: {bg};
            }}
            QFrame#{obj_name}:hover {{
                background-color: {theme['bg_item_hover'] if is_clickable else bg};
                border-color: {theme['accent'] if is_clickable else border_color};
            }}
        """)
        self.label.setStyleSheet(f"font-size: {UIConstants.FONT_SIZE_BADGE}px; border: none; background: transparent; color: {theme['text_main'] if is_clickable else theme['text_dim']};")
    def mousePressEvent(self, event):
        if self.on_click:
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
        self._pending_covers: Set[str] = set()
        
        # Monitor scrolling to trigger cover fetches for carousels
        self.scroll.verticalScrollBar().valueChanged.connect(lambda: self._on_scroll_debounced())
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.setInterval(150)
        self._scroll_timer.timeout.connect(self.ensure_visible_covers)

    def _on_scroll_debounced(self):
        self._scroll_timer.start()

    def _on_cover_request(self, url):
        # Trigger async fetch via helper
        def on_done():
            if self.isVisible():
                for ribbon in self.findChildren(BaseCardRibbon):
                    ribbon.viewport().update()

        asyncio.create_task(ViewportHelper.fetch_cover_async(
            url, self.image_manager, self._pending_covers, 
            on_done_callback=on_done, max_dim=300
        ))

    def ensure_visible_covers(self):
        """Triggers a fetch for all covers currently visible in any carousel ribbon."""
        if not self.isVisible():
            return
            
        for ribbon in self.findChildren(BaseCardRibbon):
            if not ribbon.isVisible():
                continue
            
            first, last = ViewportHelper.get_visible_range(ribbon)
            model = ribbon.model()
            if not model: continue
            
            for row in range(first, last + 1):
                item = model.get_item(row)
                if isinstance(item, FeedItem) and item.cover_url:
                    self._on_cover_request(item.cover_url)

    def reapply_theme(self):
        super().reapply_theme()
        theme = ThemeManager.get_current_theme_colors()
        s = UIConstants.scale
        
        # Propagate to dynamic badges and buttons
        for badge in self.findChildren(Badge):
            badge.reapply_theme()

        for label in self.findChildren(QLabel):
            if label.objectName() == "carousel_header":
                label.setStyleSheet(f"font-size: {s(18)}px; font-weight: bold; margin-top: {s(20)}px; color: {theme['text_main']};")
            elif label.objectName() == "meta_label":
                label.setStyleSheet(f"font-weight: bold; font-size: {UIConstants.FONT_SIZE_DETAIL_INFO}px; margin-bottom: {UIConstants.scale(2)}px; color: {theme['text_dim']};")
            elif label.objectName() == "meta_status_hint":
                label.setStyleSheet(f"font-size: {UIConstants.FONT_SIZE_BADGE}px; color: {theme['text_dim']}; font-style: italic; margin-top: {UIConstants.scale(5)}px;")
            else:

                # Default for other dynamic labels like the credit values
                if label.text() and not label.objectName():
                     label.setStyleSheet(f"font-size: {UIConstants.FONT_SIZE_DETAIL_INFO}px; color: {theme['text_main']};")
                
        for btn in self.findChildren(QPushButton):
            if btn.objectName() == "link_button":
                btn.setStyleSheet(f"""
                    QPushButton {{ color: {theme['accent']}; font-size: {s(13)}px; text-align: left; background: transparent; border: none; }}
                    QPushButton:disabled {{ color: {theme['text_dim']}; }}
                """)

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
            
            if not (pub.readingOrder and len(pub.readingOrder) > 0) or force_refresh:
                asyncio.create_task(self._fetch_full_metadata(pub, base_url, self._active_load_id, force_refresh))
            else:
                self._render_details(pub, base_url)
                self.progress.setVisible(False)
                asyncio.create_task(self._fetch_progression(pub, base_url, self._active_load_id))
            
            if force_refresh:
                QTimer.singleShot(500, self.ensure_visible_covers)
        finally:
            self.setUpdatesEnabled(True)

    async def _fetch_full_metadata(self, pub: Publication, base_url: str, load_id: str, force_refresh: bool = False):
        manifest_url = None
        for link in (pub.links or []):
            if link.type in ["application/webpub+json", "application/divina+json", "application/opds-publication+json"]:
                manifest_url = link.href
                break
        
        fetched_pub = pub
        if manifest_url and load_id == self._active_load_id:
            try:
                full_url = urljoin(base_url, manifest_url)
                full_pub = await self.opds_client.get_publication(full_url, force_refresh=force_refresh)
                
                if load_id == self._active_load_id:
                    if not full_pub.images and pub.images: full_pub.images = pub.images
                    if full_pub.metadata and pub.metadata:
                        if not full_pub.metadata.description and pub.metadata.description: 
                            full_pub.metadata.description = pub.metadata.description
                        if not full_pub.metadata.numberOfBytes and pub.metadata.numberOfBytes:
                            full_pub.metadata.numberOfBytes = pub.metadata.numberOfBytes
                    elif not full_pub.metadata and pub.metadata:
                        full_pub.metadata = pub.metadata
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
        if pub.links:
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
            if not m:
                m = Metadata(title="Unknown")
            
            self._add_title(m.title, m.subtitle)

            # Series and Position line
            if m.belongsTo:
                # Prioritize series, then collection
                coll = None
                if m.belongsTo.series and len(m.belongsTo.series) > 0:
                    coll = m.belongsTo.series[0]
                elif m.belongsTo.collection and len(m.belongsTo.collection) > 0:
                    coll = m.belongsTo.collection[0]
                
                if coll:
                    name_html = f"<i>{coll.name}</i>"
                    pos_str = ""
                    if coll.position is not None:
                        p = str(coll.position)
                        if p.endswith(".0"): p = p[:-2]
                        pos_str = f" #{p}"
                    
                    series_label = QLabel(f"{name_html}{pos_str}")
                    series_label.setTextFormat(Qt.TextFormat.RichText)
                    theme = ThemeManager.get_current_theme_colors()
                    series_label.setStyleSheet(f"font-size: 16px; color: {theme['text_main']}; margin-top: 2px;")
                    self.info_layout.addWidget(series_label)

            # Publisher and Pub Date line
            pub_contributor = None
            if m.publisher and len(m.publisher) > 0:
                pub_contributor = m.publisher[0]
            
            month, year = parse_opds_date(m.published)
            display_date = format_publication_date(month, year)

            if pub_contributor or display_date:
                line_layout = QHBoxLayout()
                line_layout.setContentsMargins(0, 0, 0, 0)
                line_layout.setSpacing(5)
                line_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
                theme = ThemeManager.get_current_theme_colors()
                
                if pub_contributor:
                    # Link logic
                    on_click = None
                    if pub_contributor.links and len(pub_contributor.links) > 0:
                        href = pub_contributor.links[0].href
                        if href:
                            full_url = urljoin(base_url, href)
                            on_click = lambda u=full_url, t=pub_contributor.name: self.on_navigate(u, t)
                    
                    # Pill-style Publisher
                    badge = Badge(pub_contributor.name, on_click=on_click)
                    line_layout.addWidget(badge)
                    
                    if display_date:
                        sep = QLabel(" • ")
                        sep.setStyleSheet(f"font-size: 14px; color: {theme['text_dim']};")
                        line_layout.addWidget(sep)

                if display_date:
                    date_label = QLabel(display_date)
                    date_label.setStyleSheet(f"font-size: 14px; color: {theme['text_dim']};")
                    line_layout.addWidget(date_label)

                self.info_layout.addLayout(line_layout)

            # Action Buttons
            manifest_url = next((urljoin(base_url, l.href) for l in (pub.links or []) if l.type in ["application/webpub+json", "application/divina+json", "application/opds-publication+json"]), None)
            
            # Use FeedReconciler to find best download link
            download_url, _ = FeedReconciler._find_acquisition_link(pub, base_url)
            
            self.btn_read = self.create_action_button(
                "Read Now",
                lambda: self.on_read(pub, manifest_url or base_url, self._context_pubs),
                icon_name="book"
            )
            
            # Disable Read button if not Divina (image-based).
            # We also enable if the manifest link type is explicitly application/divina+json.
            is_divina_link = any(l.type == "application/divina+json" for l in (pub.links or []))
            self.btn_read.setEnabled(pub.is_divina or is_divina_link)
            
            btn_down = self.create_action_button(
                "Download",
                lambda: self.on_start_download(pub, download_url),
                icon_name="download"
            )
            btn_down.setEnabled(download_url is not None)
            
            if not hasattr(self, 'actions_layout'):
                self.actions_layout = QHBoxLayout()
                s = UIConstants.scale
                self.actions_layout.setSpacing(s(10))
                self.actions_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
                self.info_layout.addLayout(self.actions_layout)

            self.actions_layout.addWidget(self.btn_read)
            self.actions_layout.addWidget(btn_down)

            # Support Status Labels
            theme = ThemeManager.get_current_theme_colors()
            notes = []
            
            # 1. Streaming Support Hint
            if not (pub.is_divina or is_divina_link):
                notes.append("Page streaming not available")

            # 2. Detailed acquisition notes (Borrow, Purchase, Unsupported Formats)
            acq_note = FeedReconciler.get_acquisition_note(pub)
            if acq_note:
                notes.append(acq_note)
            
            if notes:
                full_note_text = "Note: " + " • ".join(notes)
                status_hint = QLabel(full_note_text)
                status_hint.setObjectName("meta_status_hint")
                status_hint.setWordWrap(True)
                self.info_layout.addWidget(status_hint)
            
            # Check if already downloaded (if link exists)
            self._file_size_str = None
            if download_url and self.db:
                asyncio.create_task(self._check_for_local_copy(pub, download_url))

            # Progression & Page Count
            self._add_progression_label()
            
            total_pages = m.numberOfPages or (len(pub.readingOrder) if pub.readingOrder else 0)
            
            # Format remote file size if available
            self._file_size_str = None
            if m.numberOfBytes:
                self._file_size_str = format_file_size(m.numberOfBytes)
                
            prog_parts = []
            if total_pages:
                prog_parts.append(f"Pages: {total_pages}")
            
            if self._file_size_str:
                theme = ThemeManager.get_current_theme_colors()
                dim_color = theme['text_dim']
                prog_parts.append(f"<span style='color: {dim_color};'>{self._file_size_str}</span>")

            if prog_parts:
                self.progression_label.setText(" • ".join(prog_parts))

            # Summary (Description)
            if m.description:
                self._add_description(m.description)
                
            # Cover
            img_url = self._get_image_url(pub)
            if img_url:
                asyncio.create_task(self._load_cover(urljoin(base_url, img_url)))

            # Metadata
            roles = {}
            roles_orig = {}
            role_map = {
                "author": "Author", "artist": "Artist", "penciler": "Penciller", 
                "inker": "Inker", "colorist": "Colorist", "letterer": "Letterer", 
                "editor": "Editor", "publisher": "Publisher", "imprint": "Imprint"
            }
            for attr, label in role_map.items():
                val = getattr(m, attr, None)
                if val: # Always a List[Contributor]
                    roles_orig[label] = val
                    names = [v.name for v in val]
                    roles[label] = ", ".join(names)
            
            final_creds = format_artist_credits(roles)
            for cred in final_creds:
                if ":" in cred:
                    label, val = cred.split(":", 1)
                    label = label.strip()
                    # Map combined roles back to original data for link extraction
                    source_role = label
                    if label == "Artist" and "Artist" not in roles_orig:
                        source_role = "Penciller"
                    
                    self._add_clickable_metadata(info_layout, label, roles_orig.get(source_role, []), base_url)
            
            # Subjects
            if m.subject:
                self._add_subjects(info_layout, m.subject, base_url)

            self.info_layout.addStretch()

            # carousels
            self._add_carousels(pub, base_url)
            
            # Initial margin adjustment
            self.update_header_margins()
        finally:
            self.setUpdatesEnabled(True)

    async def _load_cover(self, url: str):
        await self.image_manager.get_image_b64(url)
        full_path = self.image_manager._get_cache_path(url)
        if full_path.exists():
            pixmap = QPixmap(str(full_path))
            if not pixmap.isNull():
                self.set_cover_pixmap(pixmap)

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
            name = item.name
            href = None
            if item.links:
                for l in item.links:
                    if "opds" in (l.type or ""):
                        href = l.href
                        break
            
            if href:
                full_href = urljoin(base_url, href)
                badge = Badge(name, lambda u=full_href, t=name: self.on_navigate(u, t))
                flow_layout.addWidget(badge)
            else:
                badge = Badge(name)
                flow_layout.addWidget(badge)
        
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
        l_label.setFixedWidth(UIConstants.DETAIL_META_WIDTH)
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
                badge = Badge(name, lambda u=full_href, t=name: self.on_navigate(u, t))
                subj_layout.addWidget(badge)
            else:
                badge = Badge(name)
                subj_layout.addWidget(badge)
        
        row_layout.addWidget(subj_widget, 1)
        container = QWidget()
        container.setLayout(row_layout)
        layout.addWidget(container)

    def update_header_margins(self):
        """Extended helper to handle manual carousel layouts in FeedDetailView."""
        # 1. Base logic for standard children
        super().update_header_margins()

        # 2. Specialized logic for manual carousel layouts
        header_margin = UIConstants.scale(10)

        # Look for the QHBoxLayouts we created manually for carousels
        for i in range(self.content_layout.count()):
            item = self.content_layout.itemAt(i)
            if item and item.layout() and isinstance(item.layout(), QHBoxLayout):
                l = item.layout()
                has_header_label = False
                for j in range(l.count()):
                    w = l.itemAt(j).widget()
                    if w and w.objectName() == "carousel_header":
                        has_header_label = True
                        break
                if has_header_label:
                    l.setContentsMargins(0, 0, header_margin, 0)

    def _add_carousels(self, pub: Publication, base_url: str):
        belongs_to = pub.metadata.belongsTo if pub.metadata else pub.belongsTo
        if not belongs_to: return

        for rel_type in ["series", "collection"]:
            items = getattr(belongs_to, rel_type, []) or []
            for item in items:
                if not item.links: continue
                for link in item.links:
                    l_href = link.href
                    if not l_href: continue

                    label_text = item.name or rel_type.capitalize()

                    header = QHBoxLayout()
                    l_title = QLabel(label_text)
                    l_title.setObjectName("carousel_header")
                    header.addWidget(l_title)
                    header.addStretch()

                    full_href = urljoin(base_url, l_href)
                    label = "See All"
                    if item.numberOfItems:
                        label = f"See All ({item.numberOfItems})"
                        
                    btn_all = self.create_action_button(
                        label,
                        lambda _, u=full_href, t=label_text: self.on_navigate(u, t),
                        object_name="action_button"
                    )
                    header.addWidget(btn_all)
                    self.content_layout.insertLayout(self.content_layout.count() - 1, header)
                    
                    # Use a horizontal ribbon-style list view
                    model = FeedBrowserModel()
                    delegate = FeedCardDelegate(self, self.image_manager, show_labels=True)
                    
                    view = BaseCardRibbon(self, show_labels=True)
                    view.setModel(model)
                    model.cover_request_needed.connect(self._on_cover_request)
                    view.setItemDelegate(delegate)
                    view.update_ribbon_height()
                    view.clicked.connect(self._on_carousel_clicked)
                    
                    self.content_layout.insertWidget(self.content_layout.count() - 1, view)
                    self.reapply_theme()
                    
                    asyncio.create_task(self._load_carousel_data(full_href, model))

    def _on_carousel_clicked(self, index):
        model = index.model()
        item = model.data(index, FeedBrowserModel.ItemDataRole)
        if item and item.raw_pub:
            self.on_open_detail(item.raw_pub, None)

    async def _load_carousel_data(self, url, model):
        try:
            feed = await self.opds_client.get_feed(url)
            
            # Use FeedReconciler to get FeedItems
            base_feed_url = self.api_client.profile.get_base_url()
            feed_page = FeedReconciler.reconcile(feed, base_feed_url)
            
            # Only show cards from the root-level publications
            items = []
            for section in feed_page.sections:
                if section.source_element == "root:publications":
                    items.extend(section.items)
            
            if not items:
                return

            model.update_total_count(len(items[:15]))
            model.set_items_for_page(1, items[:15])
            
            # Seed visibility check once data is in the model
            QTimer.singleShot(300, self.ensure_visible_covers)
            
        except Exception as e:
            logger.error(f"Carousel error: {e}")
