import asyncio
from pathlib import Path
from PyQt6.QtWidgets import QStyledItemDelegate
from PyQt6.QtCore import Qt, QRect, QSize
from PyQt6.QtGui import QPainter, QIcon, QPixmap
from ui.components.base_card_delegate import BaseCardDelegate
from ui.theme_manager import ThemeManager, UIConstants
from ui.components.mini_detail_popover import MiniDetailPopover

class LibraryCardDelegate(BaseCardDelegate):
    def __init__(self, parent=None, show_labels=True, image_manager=None, folder_icon="folder"):
        super().__init__(parent, show_labels=show_labels)
        self.image_manager = image_manager
        self.folder_icon = folder_icon

    def reapply_theme(self):
        """No-op as paint() fetches theme on every call, but here for consistency."""
        pass

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        theme = ThemeManager.get_current_theme_colors()
        
        # 1. Get data
        file_path = index.data(Qt.ItemDataRole.UserRole)
        is_dir = False
        if isinstance(file_path, Path):
            is_dir = file_path.is_dir()
            
        pixmap = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(pixmap, QIcon):
            pixmap = pixmap.pixmap(option.decorationSize)
            
        progress_data = index.data(Qt.ItemDataRole.UserRole + 1) # (current, total)
        curr_page, total_pages = 0, 0
        if isinstance(progress_data, (list, tuple)) and len(progress_data) >= 2:
            curr_page = progress_data[0] or 0
            total_pages = progress_data[1] or 0
        
        rect = option.rect

        # 2. Draw standard card background
        content_rect = self.draw_card_background(painter, rect, option, theme)

        # 3. Cover / Folder Art Area
        if not self.show_labels:
            # If labels are hidden, fill the whole available card background
            cover_area_rect = content_rect
        else:
            cover_area_rect = QRect(content_rect.left(), content_rect.top(), content_rect.width(), self.cover_height)
        
        if is_dir:
            text = index.data(Qt.ItemDataRole.DisplayRole)
            self.draw_folder_stack(painter, cover_area_rect, theme, image_manager=self.image_manager, label=text, icon_name=self.folder_icon, badge_icon_name="library")
        elif pixmap and not pixmap.isNull():
            opacity = 0.5 if (total_pages > 0 and curr_page >= total_pages - 1) else 1.0
            
            # Scale and draw cover image
            self.draw_cover_pixmap(painter, cover_area_rect, pixmap, opacity)
            
        # 4. Progress bar (BELOW the cover)
        s = UIConstants.scale
        prog_bar_y = cover_area_rect.bottom() + s(2)
        progress_rect = QRect(content_rect.left(), prog_bar_y, content_rect.width(), UIConstants.PROGRESS_BAR_TOTAL_HEIGHT)
        if not is_dir and total_pages > 0 and curr_page > 0 and curr_page < total_pages - 1:
            prog_pct = curr_page / total_pages
            self.draw_progress_bar(painter, progress_rect, prog_pct, option.palette.highlight().color())

        # 5. Label Text
        if self.show_labels:
            label_data = index.data(Qt.ItemDataRole.UserRole + 2) # (primary, secondary)
            if isinstance(label_data, (list, tuple)) and len(label_data) >= 1:
                primary = label_data[0]
            else:
                primary = index.data(Qt.ItemDataRole.DisplayRole)
                
            # Label starts after progress bar area
            text_y = progress_rect.bottom() + s(2)
            text_rect = QRect(content_rect.left() + s(5), text_y, content_rect.width() - s(10), self.label_height)
            self.draw_label(painter, text_rect, primary, theme)
        else:
            # Internal label as a backup when covers are missing
            # is_dir (folders) handles its own internal label in draw_folder_stack
            if not is_dir and (not pixmap or pixmap.isNull()):
                primary = index.data(Qt.ItemDataRole.DisplayRole)
                self.draw_internal_label(painter, cover_area_rect, primary, theme)

        painter.restore()
