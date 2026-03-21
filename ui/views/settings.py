from __future__ import annotations
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QLineEdit, QRadioButton, QGroupBox, QFileDialog, QFrame, QScrollArea,
    QComboBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from config import ConfigManager
from api.image_manager import ImageManager
from ui.views.feed_management import FeedManagementView

class SettingsView(QWidget):
    theme_changed = pyqtSignal()
    
    def __init__(self, config_manager: ConfigManager, image_manager: ImageManager):
        super().__init__()
        self.config_manager = config_manager
        self.image_manager = image_manager

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # Use a scroll area for settings
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; }")
        
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(20)

        self.title = QLabel("App Settings")
        self.title.setStyleSheet("font-size: 24px; font-weight: bold;")
        self.layout.addWidget(self.title)

        # Theme
        self.theme_group = QGroupBox("Theme")
        self.theme_layout = QHBoxLayout(self.theme_group)
        
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
        
        self.theme_layout.addWidget(QLabel("Select Theme: "))
        self.theme_layout.addWidget(self.theme_combo)
        self.theme_layout.addStretch()
        
        self.layout.addWidget(self.theme_group)

        # Feeds Management
        self.feeds_group = QGroupBox("Feeds")
        self.feeds_layout = QVBoxLayout(self.feeds_group)
        self.feed_management = FeedManagementView(self.config_manager, self.image_manager)
        self.feeds_layout.addWidget(self.feed_management)
        self.layout.addWidget(self.feeds_group)

        # Browsing Method
        self.method_group = QGroupBox("Browsing Method")
        self.method_layout = QHBoxLayout(self.method_group)
        
        self.method_combo = QComboBox()
        self.method_combo.addItem("Continuous Mode (Sequential)", "continuous")
        self.method_combo.addItem("Traditional Paging (Standard Buttons)", "paging")
        self.method_combo.addItem("ReFit Mode (Fixed height, fast)", "refit")
        
        current_method = self.config_manager.get_scroll_method()
        idx = self.method_combo.findData(current_method)
        if idx >= 0:
            self.method_combo.setCurrentIndex(idx)
            
        self.method_combo.currentIndexChanged.connect(self._on_method_combo_changed)
        
        self.method_layout.addWidget(QLabel("Select Mode: "))
        self.method_layout.addWidget(self.method_combo)
        self.method_layout.addStretch()
        
        self.layout.addWidget(self.method_group)

        # Library Folder
        self.library_group = QGroupBox("Library")
        self.library_layout = QVBoxLayout(self.library_group)
        
        self.library_layout.addWidget(QLabel("Local folder for downloaded and imported comics:"))
        
        path_layout = QHBoxLayout()
        self.library_path_input = QLineEdit(str(self.config_manager.get_library_dir()))
        self.btn_browse_path = QPushButton("Browse...")
        self.btn_browse_path.clicked.connect(self._on_browse_clicked)
        
        path_layout.addWidget(self.library_path_input)
        path_layout.addWidget(self.btn_browse_path)
        self.library_layout.addLayout(path_layout)
        
        self.btn_save_path = QPushButton("Save Library Folder")
        self.btn_save_path.clicked.connect(self._on_save_path_clicked)
        self.library_layout.addWidget(self.btn_save_path)
        
        self.layout.addWidget(self.library_group)

        # About
        self.about_group = QGroupBox("About")
        self.about_layout = QVBoxLayout(self.about_group)
        
        about_header = QHBoxLayout()
        
        # App Icon
        self.icon_label = QLabel()
        # Use smaller version for better scaling
        icon_path = Path(__file__).parent.parent.parent / "resources" / "app_64.png"
        if not icon_path.exists():
             icon_path = Path(__file__).parent.parent.parent / "resources" / "app.png"
             
        if icon_path.exists():
            pixmap = QPixmap(str(icon_path))
            self.icon_label.setPixmap(pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        
        about_header.addWidget(self.icon_label)
        
        text_layout = QVBoxLayout()
        text_layout.addWidget(QLabel("<b>ComicCatcher v0.1.0</b>"))
        text_layout.addWidget(QLabel("PyQt6 Native Edition"))
        about_header.addLayout(text_layout)
        about_header.addStretch()
        
        self.about_layout.addLayout(about_header)
        self.layout.addWidget(self.about_group)

        self.layout.addStretch()
        
        self.scroll.setWidget(self.container)
        self.main_layout.addWidget(self.scroll)

    def _on_theme_combo_changed(self, index):
        theme = self.theme_combo.itemData(index)
        self.config_manager.set_theme(theme)
        self.theme_changed.emit()

    def _on_theme_changed(self):
        # Triggered when theme changes from sidebar or other sources
        # We need to refresh icons if any
        pass

    def _on_method_combo_changed(self, index):
        method = self.method_combo.itemData(index)
        self.config_manager.set_scroll_method(method)

    def _on_browse_clicked(self):
        path = QFileDialog.getExistingDirectory(self, "Select Library Directory", self.library_path_input.text())
        if path:
            self.library_path_input.setText(path)

    def _on_save_path_clicked(self):
        path_str = self.library_path_input.text().strip()
        self.config_manager.set_library_dir(path_str)
        # Normalize display
        self.library_path_input.setText(str(self.config_manager.get_library_dir()))
