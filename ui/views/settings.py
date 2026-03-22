from __future__ import annotations
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QLineEdit, QGroupBox, QFileDialog, QFrame, QScrollArea,
    QComboBox, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from ui.theme_manager import ThemeManager, UIConstants
from config import ConfigManager, CACHE_DIR
from api.image_manager import ImageManager
from api.opds_v2 import OPDS2Client
from api.local_db import LocalLibraryDB
from ui.views.feed_management import FeedManagementView

from ui.views.base_browser import BaseBrowserView

class SettingsView(BaseBrowserView):
    theme_changed = pyqtSignal()
    library_reset = pyqtSignal()
    
    def __init__(self, config_manager: ConfigManager, image_manager: ImageManager, opds_client: OPDS2Client, local_db: LocalLibraryDB):
        super().__init__()
        self.config_manager = config_manager
        self.image_manager = image_manager
        self.opds_client = opds_client
        self.local_db = local_db
        
        s = UIConstants.scale

        # 1. Header Configuration
        self.status_label.setText("App Settings")
        self.status_label.setStyleSheet(f"font-size: {s(14)}px; font-weight: bold;")

        # 2. Main Content Area (Scroll Area)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(s(40), s(20), s(40), s(40))
        self.container_layout.setSpacing(s(30))

        # --- SECTIONS ---

        # Appearance Section
        self.theme_group = QGroupBox("Appearance")
        self.theme_layout = QVBoxLayout(self.theme_group)
        self.theme_layout.setContentsMargins(s(15), s(25), s(15), s(15))
        
        theme_row = QHBoxLayout()
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.addItem("Dark", "dark")
        self.theme_combo.addItem("OLED (Black)", "oled")
        self.theme_combo.addItem("Deep Blue", "blue")
        self.theme_combo.addItem("Light Blue (Fresh)", "light_blue")
        
        current_theme = self.config_manager.get_theme()
        index = self.theme_combo.findData(current_theme)
        if index >= 0:
            self.theme_combo.setCurrentIndex(index)
        
        self.theme_combo.currentIndexChanged.connect(self._on_theme_combo_changed)
        
        theme_row.addWidget(QLabel("Interface Theme:"))
        theme_row.addWidget(self.theme_combo)
        theme_row.addStretch()
        self.theme_layout.addLayout(theme_row)
        self.container_layout.addWidget(self.theme_group)

        # Feeds Management
        self.feeds_group = QGroupBox("Content Feeds (OPDS)")
        self.feeds_layout = QVBoxLayout(self.feeds_group)
        self.feeds_layout.setContentsMargins(s(15), s(25), s(15), s(15))
        self.feed_management = FeedManagementView(self.config_manager, self.image_manager)
        self.feeds_layout.addWidget(self.feed_management)
        self.container_layout.addWidget(self.feeds_group)

        # Library Folder
        self.library_group = QGroupBox("Local Library Storage")
        self.library_layout = QVBoxLayout(self.library_group)
        self.library_layout.setContentsMargins(s(15), s(25), s(15), s(15))
        self.library_layout.setSpacing(s(10))
        
        self.library_layout.addWidget(QLabel("Base folder for downloaded comics and local scans:"))
        
        path_layout = QHBoxLayout()
        self.library_path_input = QLineEdit(str(self.config_manager.get_library_dir()))
        self.library_path_input.setReadOnly(True)
        self.btn_browse_path = QPushButton("Change Folder...")
        self.btn_browse_path.setObjectName("secondary_button")
        self.btn_browse_path.clicked.connect(self._on_browse_clicked)
        
        path_layout.addWidget(self.library_path_input)
        path_layout.addWidget(self.btn_browse_path)
        self.library_layout.addLayout(path_layout)
        self.container_layout.addWidget(self.library_group)

        # Maintenance (Caches)
        self.maintenance_group = QGroupBox("System Maintenance")
        self.maintenance_layout = QVBoxLayout(self.maintenance_group)
        self.maintenance_layout.setContentsMargins(s(15), s(25), s(15), s(15))
        self.maintenance_layout.setSpacing(s(15))
        
        self.maintenance_layout.addWidget(QLabel("Perform maintenance tasks to free up space or fix database issues:"))
        
        cache_buttons = QHBoxLayout()
        self.btn_clear_thumbnails = QPushButton("Clear Image Cache")
        self.btn_clear_thumbnails.setObjectName("secondary_button")
        self.btn_clear_thumbnails.clicked.connect(self._on_clear_thumbnails_clicked)
        
        self.btn_clear_metadata = QPushButton("Clear Data Cache")
        self.btn_clear_metadata.setObjectName("secondary_button")
        self.btn_clear_metadata.clicked.connect(self._on_clear_metadata_clicked)
        
        self.btn_reset_library = QPushButton("Wipe Library DB")
        self.btn_reset_library.clicked.connect(self._on_reset_library_clicked)
        self.btn_reset_library.setObjectName("danger_button")
        
        cache_buttons.addWidget(self.btn_clear_thumbnails)
        cache_buttons.addWidget(self.btn_clear_metadata)
        cache_buttons.addWidget(self.btn_reset_library)
        self.maintenance_layout.addLayout(cache_buttons)
        self.container_layout.addWidget(self.maintenance_group)

        # About
        self.about_group = QGroupBox("About ComicCatcher")
        self.about_layout = QVBoxLayout(self.about_group)
        self.about_layout.setContentsMargins(s(15), s(25), s(15), s(15))
        
        about_header = QHBoxLayout()
        self.icon_label = QLabel()
        icon_path = Path(__file__).parent.parent.parent / "resources" / "app_64.png"
        if not icon_path.exists():
             icon_path = Path(__file__).parent.parent.parent / "resources" / "app.png"
             
        if icon_path.exists():
            pixmap = QPixmap(str(icon_path))
            self.icon_label.setPixmap(pixmap.scaled(s(64), s(64), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        
        about_header.addWidget(self.icon_label)
        
        text_layout = QVBoxLayout()
        v_label = QLabel("<b>ComicCatcher v0.1.0</b>")
        v_label.setStyleSheet(f"font-size: {s(16)}px;")
        text_layout.addWidget(v_label)
        text_layout.addWidget(QLabel("A comic browser/streamer/downloader/reader for OPDS v2 feeds"))
        about_header.addLayout(text_layout)
        about_header.addStretch()
        self.about_layout.addLayout(about_header)
        self.container_layout.addWidget(self.about_group)

        self.container_layout.addStretch()
        
        # 3. Final Assembly
        self.scroll.setWidget(self.container)
        self.add_content_widget(self.scroll)

    def reapply_theme(self):
        super().reapply_theme()
        theme = ThemeManager.get_current_theme_colors()
        s = UIConstants.scale
        
        self.container.setStyleSheet(f"background-color: {theme['bg_main']};")
        self.scroll.setStyleSheet(f"QScrollArea {{ border: none; background-color: {theme['bg_main']}; }}")
        
        # Propagation to sub-widgets
        self.feed_management.reapply_theme()
        
        for group in self.findChildren(QGroupBox):
            group.setStyleSheet(f"""
                QGroupBox {{
                    font-weight: bold;
                    border: {max(1, s(1))}px solid {theme['border']};
                    border-radius: {s(8)}px;
                    margin-top: {s(20)}px;
                    background-color: {theme['card_bg']};
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    left: {s(15)}px;
                    padding: 0 {s(5)}px;
                    color: {theme['accent']};
                }}
                QLabel {{
                    background-color: transparent;
                }}
            """)

    def _on_theme_combo_changed(self, index):
        theme = self.theme_combo.itemData(index)
        self.config_manager.set_theme(theme)
        self.theme_changed.emit()

    def _on_theme_changed(self):
        # Triggered when theme changes from sidebar or other sources
        pass

    def _on_browse_clicked(self):
        path = QFileDialog.getExistingDirectory(self, "Select Library Directory", self.library_path_input.text())
        if path:
            self.library_path_input.setText(path)

    def _on_save_path_clicked(self):
        path_str = self.library_path_input.text().strip()
        self.config_manager.set_library_dir(path_str)
        self.library_path_input.setText(str(self.config_manager.get_library_dir()))

    def _on_clear_thumbnails_clicked(self):
        reply = QMessageBox.question(
            self, "Clear Thumbnail Cache",
            "Are you sure you want to clear all cached thumbnails? This will free up disk space but covers will need to be re-downloaded as you scroll.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.image_manager.clear_disk_cache()
            self.image_manager.clear_memory_cache()
            QMessageBox.information(self, "Cache Cleared", "Thumbnail cache has been cleared.")

    def _on_clear_metadata_clicked(self):
        reply = QMessageBox.question(
            self, "Clear Metadata Cache",
            "Are you sure you want to clear the in-memory metadata cache? This will force a refresh of all feed data.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.opds_client.clear_cache()
            QMessageBox.information(self, "Cache Cleared", "Metadata cache has been cleared.")

    def _on_reset_library_clicked(self):
        reply = QMessageBox.question(
            self, "Reset Local Library Database",
            "Are you sure you want to reset the local library database?\n\n<b>WARNING:</b> This will permanently wipe all reading progress for local comics. The database will be rebuilt automatically next time you visit the Library.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.local_db.clear_all()
            self.library_reset.emit()
            QMessageBox.information(self, "Library Reset", "Local library database has been cleared.")
