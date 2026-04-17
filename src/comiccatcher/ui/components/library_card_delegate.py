# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

import asyncio
from pathlib import Path
from PyQt6.QtWidgets import QStyledItemDelegate, QStyle
from PyQt6.QtCore import Qt, QRect, QSize
from PyQt6.QtGui import QPainter, QIcon, QPixmap
from comiccatcher.ui.components.base_card_delegate import BaseCardDelegate, CardConfig
from comiccatcher.ui.theme_manager import ThemeManager, UIConstants
from comiccatcher.ui.components.mini_detail_popover import MiniDetailPopover

class LibraryCardDelegate(BaseCardDelegate):
    def __init__(self, parent=None, show_labels=True, image_manager=None, folder_icon="folder"):
        super().__init__(parent, show_labels=show_labels)
        self.image_manager = image_manager
        self.folder_icon = folder_icon

    def reapply_theme(self):
        """No-op as paint() fetches theme on every call, but here for consistency."""
        pass

    def paint(self, painter, option, index):
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

        label_data = index.data(Qt.ItemDataRole.UserRole + 2) # (primary, secondary)
        if isinstance(label_data, (list, tuple)) and len(label_data) >= 1:
            primary = label_data[0]
        else:
            primary = index.data(Qt.ItemDataRole.DisplayRole)

        # 2. Calculate progress and dimming
        prog_pct = 0.0
        if not is_dir and total_pages > 0 and curr_page > 0:
            prog_pct = curr_page / total_pages
            
        dim_cover = (total_pages > 0 and curr_page >= total_pages - 1)

        # 3. Create config and paint
        config = CardConfig(
            primary_text=primary,
            secondary_text=None, # Explicitly disabled
            cover_pixmap=pixmap,
            is_folder=is_dir,
            folder_icon_name=self.folder_icon,
            badge_icon_name="library" if is_dir else None,
            progress_pct=prog_pct,
            progress_color=option.palette.highlight().color(),
            image_manager=self.image_manager,
            dim_cover=dim_cover,
            reserve_progress_space=self.reserve_progress_space
        )
        
        self.paint_card(painter, option, theme, config)
