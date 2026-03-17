from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QLineEdit, QRadioButton, QGroupBox, QFileDialog, QFrame
)
from PyQt6.QtCore import Qt
from config import ConfigManager

class SettingsView(QWidget):
    def __init__(self, config_manager: ConfigManager):
        super().__init__()
        self.config_manager = config_manager

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(20)

        self.title = QLabel("App Settings")
        self.title.setStyleSheet("font-size: 24px; font-weight: bold;")
        self.layout.addWidget(self.title)

        # Browsing Method
        self.method_group = QGroupBox("Browsing Method")
        self.method_layout = QVBoxLayout(self.method_group)
        
        self.radio_infinite = QRadioButton("Infinite Scroll (Sequential)")
        self.radio_paging = QRadioButton("Traditional Paging (Standard Buttons)")
        self.radio_viewport = QRadioButton("Viewport Paging (Fit to Window)")
        
        self.method_layout.addWidget(self.radio_infinite)
        self.method_layout.addWidget(self.radio_paging)
        self.method_layout.addWidget(self.radio_viewport)
        
        # Set initial value
        method = self.config_manager.get_scroll_method()
        if method == "infinite": self.radio_infinite.setChecked(True)
        elif method == "paging": self.radio_paging.setChecked(True)
        elif method == "viewport": self.radio_viewport.setChecked(True)
        
        self.radio_infinite.toggled.connect(lambda: self._on_method_changed("infinite"))
        self.radio_paging.toggled.connect(lambda: self._on_method_changed("paging"))
        self.radio_viewport.toggled.connect(lambda: self._on_method_changed("viewport"))
        
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
        self.about_layout.addWidget(QLabel("ComicCatcher v0.1.0"))
        self.about_layout.addWidget(QLabel("PyQt6 Native Edition"))
        self.layout.addWidget(self.about_group)

        self.layout.addStretch()

    def _on_method_changed(self, method):
        # Radio button toggle emits for both uncheck and check
        if self.sender().isChecked():
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
