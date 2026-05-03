# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

import asyncio
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QFrame, QSizePolicy, QProgressBar
)
from PyQt6.QtCore import Qt, QSize, QUrl
from PyQt6.QtGui import QPixmap, QFont, QDesktopServices

from comiccatcher.config import ConfigManager
from comiccatcher.logger import get_logger
from comiccatcher.api.image_manager import ImageManager
from comiccatcher.api.local_db import LocalLibraryDB
from comiccatcher.ui.local_archive import read_archive_first_image
from comiccatcher.ui.local_comicbox import flatten_comicbox, read_comicbox_dict, read_comicbox_cover, generate_comic_labels
from comiccatcher.ui.theme_manager import ThemeManager, UIConstants, Keys
from comiccatcher.ui.flow_layout import FlowLayout
from comiccatcher.ui.components.badge import Badge
from comiccatcher.ui.views.base_detail import BaseDetailView
from comiccatcher.ui.view_helpers import HelpPopoverMixin
from comiccatcher.ui.utils import format_artist_credits, format_publication_date, format_file_size

logger = get_logger("ui.local_detail")

def _read_comicbox_meta(path: Path) -> Dict[str, Any]:
    raw = read_comicbox_dict(path)
    return flatten_comicbox(raw)

class LocalDetailView(BaseDetailView, HelpPopoverMixin):
    def __init__(self, config_manager: ConfigManager, on_back, image_manager: ImageManager, on_read_local=None, local_db: Optional[LocalLibraryDB] = None):
        super().__init__(on_back, image_manager)
        self.config_manager = config_manager
        self.on_read_local = on_read_local
        self.db = local_db
        self._path: Optional[Path] = None
        self.init_help_popover()

    def reapply_theme(self):
        super().reapply_theme()

    def load_path(self, path: Path, context_paths=None):
        self._path = Path(path)
        self._context_paths = context_paths
        
        # 1. Read metadata SYNCHRONOUSLY so we can populate the view in one go
        # Reading a small XML/JSON from disk is very fast (<10ms typically)
        meta = {}
        try:
            meta = _read_comicbox_meta(self._path)
        except Exception as e:
            logger.error(f"Error reading meta: {e}")

        self.setUpdatesEnabled(False)
        try:
            info_layout = self._setup_main_info_layout()
            
            # Show relative file path under cover
            lib_root = self.config_manager.get_library_dir()
            try:
                rel_path = self._path.relative_to(lib_root)
                self.cover_footer.setText(str(rel_path))
            except ValueError:
                # Fallback if not within lib_root
                self.cover_footer.setText(str(self._path))
            
            # Reset cover while loading new one asynchronously
            self.cover_label.clear()
            self.cover_label.setText("Loading Cover...")
            
            # Use focus-aware label logic
            label_focus = self.config_manager.get_library_label_focus()
            primary, secondary = generate_comic_labels(meta, label_focus)
            
            # Use primary label as title if we have meta, else filename
            display_title = primary if meta.get("series") or meta.get("title") else self._path.stem
            self._add_title(display_title, subtitle_text=secondary)
            
            # Publisher and Pub Date line
            pub = meta.get("publisher")
            year = meta.get("year")
            month = meta.get("month")
            
            pub_parts = []
            if pub:
                pub_parts.append(pub)
            
            s = UIConstants.scale
            date_str = format_publication_date(month, year)
            if date_str:
                pub_parts.append(date_str)
                
            if pub_parts:
                line_layout = QHBoxLayout()
                line_layout.setContentsMargins(0, 0, 0, 0)
                line_layout.setSpacing(s(5))
                line_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
                
                line_text = " • ".join(pub_parts)
                pub_label = QLabel(line_text)
                theme = ThemeManager.get_current_theme_colors()
                pub_label.setStyleSheet(f"font-size: {s(14)}px; color: {theme['text_dim']}; margin-top: {s(2)}px;")
                line_layout.addWidget(pub_label)
                
                self.info_layout.addLayout(line_layout)

            # Action Buttons
            self.btn_read = self.create_action_button("Read", self._on_read_clicked, icon_name="book")
            # Support all comic formats
            COMIC_EXTS = {".cbz", ".cbr", ".cb7", ".cbt", ".pdf"}
            is_comic = self._path.suffix.lower() in COMIC_EXTS
            self.btn_read.setEnabled(is_comic)
            
            if not hasattr(self, 'actions_layout'):
                self.actions_layout = QHBoxLayout()
                s = UIConstants.scale
                self.actions_layout.setSpacing(s(10))
                self.actions_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
                self.info_layout.addLayout(self.actions_layout)

            self.actions_layout.addWidget(self.btn_read)
            
            # File Size
            size_bytes = 0
            if self._path.exists():
                try:
                    size_bytes = self._path.stat().st_size
                except:
                    pass
            
            self._file_size_str = format_file_size(size_bytes) if size_bytes > 0 else None
            
            # Progression
            self._add_progression_label()

            # Render metadata IMMEDIATELY (no async jumping)
            self._render_meta(meta)

            # Summary (Description)
            summary = meta.get("summary")
            if summary:
                self._add_description(summary)
            
            info_layout.addStretch()
            
            # Async tasks for heavy things (Cover image and DB progress)
            if is_comic:
                asyncio.create_task(self._load_cover(self._path))
                if self.db:
                    asyncio.create_task(self._load_progress(self._path))
            else:
                self.progression_label.hide()
        finally:
            self.setUpdatesEnabled(True)

    async def _load_meta(self, path: Path):
        # Deprecated: replaced by synchronous load in load_path to avoid UI jumping
        pass

    async def _load_cover(self, path: Path):
        # Use a high-res cover URL suffix for details
        url = f"local-archive://{path.absolute()}/_cover_full"
        cache_path = self.image_manager._get_cache_path(url)
        
        if not cache_path.exists():
            try:
                # Use the standard comicbox cover (which is a high-res page image)
                data = await asyncio.to_thread(read_comicbox_cover, path)
                
                if not data:
                    # Last resort fallback to first image
                    res = await asyncio.to_thread(read_archive_first_image, path)
                    if res: _, data = res
                    
                if data:
                    # Scale and write to disk
                    scaled_data = await asyncio.to_thread(self.image_manager._scale_image, data, 1200)
                    with open(cache_path, "wb") as f:
                        f.write(scaled_data)
            except Exception:
                pass
        
        if cache_path.exists() and path == self._path:
            pixmap = QPixmap(str(cache_path))
            if not pixmap.isNull():
                self.set_cover_pixmap(pixmap)

    def refresh_progress(self):
        """Public method to re-fetch and update the progression UI."""
        if self._path and self.db:
            asyncio.create_task(self._load_progress(self._path))

    async def _load_progress(self, path: Path):
        try:
            row = await asyncio.to_thread(self.db.get_comic, str(path.absolute()))
            if row and path == self._path:
                r = dict(row)
                curr = r.get("current_page", 0)
                total = r.get("page_count", 0)
                
                theme = ThemeManager.get_current_theme_colors()
                dim_color = theme['text_dim']
                
                if total > 0:
                    if curr > 0:
                        prog_text = f"Page {curr + 1} of {total}"
                    else:
                        prog_text = f"{total} Pages"
                        
                    if self._file_size_str:
                        prog_text += f"&nbsp;&nbsp;&nbsp;•&nbsp;&nbsp;&nbsp;<span style='color: {dim_color};'>{self._file_size_str}</span>"
                    self.progression_label.setText(prog_text)
                    self.progression_label.show()
                    self._update_cover_progress(curr, total)
                    
                    if curr >= total - 1:
                        # Special case for 1-page comics or exactly at the end
                        if total == 1 and curr == 0:
                             # Still unread-ish or just one page
                             pass
                        else:
                            finished_text = f"Finished: {total} pages read"
                            if self._file_size_str:
                                finished_text += f"&nbsp;&nbsp;&nbsp;•&nbsp;&nbsp;&nbsp;<span style='color: {dim_color};'>{self._file_size_str}</span>"
                            self.progression_label.setText(finished_text)
                        self.btn_read.setText("Read Again")
                    elif curr > 0:
                        self.btn_read.setText("Resume")
                    else:
                        self.btn_read.setText("Read")
                else:
                    if self._file_size_str:
                        self.progression_label.setText(f"<span style='color: {dim_color};'>{self._file_size_str}</span>")
                        self.progression_label.show()
                    else:
                        self.progression_label.hide()
                    self.btn_read.setText("Read")
            else:
                if self._file_size_str:
                    theme = ThemeManager.get_current_theme_colors()
                    dim_color = theme['text_dim']
                    self.progression_label.setText(f"<span style='color: {dim_color};'>{self._file_size_str}</span>")
                    self.progression_label.show()
                else:
                    self.progression_label.hide()
                self.btn_read.setText("Read")
        except Exception as e:
            logger.error(f"Error loading progress: {e}")
            self.progression_label.hide()

    def _render_meta(self, meta: Dict[str, Any]):
        roles = {
            "Writer": meta.get("writer"),
            "Penciller": meta.get("penciller"),
            "Inker": meta.get("inker"),
            "Colorist": meta.get("colorist"),
            "Letterer": meta.get("letterer"),
            "Editor": meta.get("editor")
        }
        # Filter out empty roles
        roles = {k: v for k, v in roles.items() if v}
        
        final_creds = format_artist_credits(roles)
        
        for cred in final_creds:
            if ":" in cred:
                label, val = cred.split(":", 1)
                self._add_metadata_row(label.strip(), val.strip())

        # Genre / Subjects row
        genre_data = meta.get("genre")
        if genre_data:
            genres = [g.strip() for g in genre_data.split(",") if g.strip()]
            if genres:
                row = QWidget()
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                s = UIConstants.scale
                
                l = QLabel("<b>Genre:</b>")
                l.setFixedWidth(s(100))
                l.setObjectName("meta_label")
                row_layout.addWidget(l)
                
                flow = FlowLayout(spacing=5)
                for g in genres:
                    flow.addWidget(Badge(g))
                
                flow_widget = QWidget()
                flow_widget.setLayout(flow)
                row_layout.addWidget(flow_widget, 1)
                
                self.info_layout.addWidget(row)
                self._metadata_rows.append((l, flow_widget))

        # Web Links row
        web_data = meta.get("web")
        if web_data:
            urls = [u.strip() for u in web_data.split(",") if u.strip()]
            if urls:
                row = QWidget()
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                s = UIConstants.scale
                
                l = QLabel("<b>Links:</b>")
                l.setFixedWidth(s(100))
                l.setObjectName("meta_label")
                row_layout.addWidget(l)
                
                flow = FlowLayout(spacing=5)
                
                for url in urls:
                    parsed = urlparse(url)
                    host = parsed.netloc or url
                    if host.startswith("www."): host = host[4:]
                    
                    btn = Badge(host, lambda u=url: QDesktopServices.openUrl(QUrl(u)))
                    flow.addWidget(btn)
                
                flow_widget = QWidget()
                flow_widget.setLayout(flow)
                row_layout.addWidget(flow_widget, 1)
                
                self.info_layout.addWidget(row)
                self._metadata_rows.append((l, flow_widget))
            
    def _on_delete_clicked(self):
        if not self._path: return
        
        try:
            p = self._path.absolute()
            if p.exists():
                p.unlink()
                logger.info(f"Deleted file: {p}")
            
            if self.db:
                self.db.remove_comic(str(p))
                logger.info(f"Removed from DB: {p}")
                
            self.on_back()
        except Exception as e:
            logger.error(f"Error during delete: {e}")

    def _on_read_clicked(self):
        if self.on_read_local and self._path:
            self.on_read_local(self._path, self._context_paths)

    def keyPressEvent(self, event):
        if event.key() in (Keys.READ, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.btn_read and self.btn_read.isEnabled():
                self.btn_read.click()
                return
        elif event.key() == Qt.Key.Key_H:
            self.toggle_help_popover()
            return
        super().keyPressEvent(event)

    def get_help_popover_title(self):
        return "Library Details Controls"

    def get_help_popover_sections(self):
        sections = self.get_common_help_sections()
        sections.insert(0, ("DETAIL CONTROLS", [
            ("R / Enter", "Read this comic"),
            ("Arrows", "Scroll details"),
        ]))
        return sections
