#!/usr/bin/env python3
import sys
import asyncio
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPoint, QTimer

# Add current dir to sys.path
current_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(current_dir))

from comiccatcher.config import ConfigManager
from comiccatcher.ui.app_layout import MainWindow
from comiccatcher.ui.theme_manager import UIConstants, ThemeManager
from comiccatcher.ui.components.collapsible_section import CollapsibleSection
from comiccatcher.ui.components.section_header import SectionHeader
import comiccatcher.logger as logger

def wait_for_widgets(parent, widget_class, callback, timeout=30):
    """Polls the widget tree until at least one widget of widget_class is found."""
    start = asyncio.get_event_loop().time()
    def check():
        widgets = parent.findChildren(widget_class)
        if widgets and any(w.isVisible() for w in widgets):
            callback(True)
            return
        if (asyncio.get_event_loop().time() - start) > timeout:
            callback(False)
            return
        QTimer.singleShot(500, check)
    check()

class Verifier:
    def __init__(self, app, window, config):
        self.app = app
        self.window = window
        self.config = config
        self.loop = asyncio.get_event_loop()

    def run(self):
        print("🧪 Starting Visual Layout Verification (Manual Event Loop)...")
        self.step_1_library()

    def step_1_library(self):
        print("📸 Loading Library View...")
        self.window.nav_list.setCurrentRow(1)
        wait_for_widgets(self.window, CollapsibleSection, self.after_library_visible)

    def after_library_visible(self, success):
        if success:
            print("✅ Library content detected.")
            QTimer.singleShot(2000, self.snap_library)
        else:
            print("❌ Timeout waiting for Library content.")
            self.step_2_paged()

    def snap_library(self):
        pix = self.window.grab()
        pix.save('screenshots/verify_align_library.png')
        self.step_2_paged()

    def step_2_paged(self):
        print("📸 Loading Paged Feed View...")
        codex_feed = next((f for f in self.config.feeds if "codex" in f.name.lower()), self.config.feeds[0])
        # Force paged mode for this test
        self.window.on_feed_selected(codex_feed)
        # Ensure we are in paged mode (manual toggle if necessary)
        self.window.feed_browser.btn_mode_paged.click()
        
        wait_for_widgets(self.window.feed_browser, CollapsibleSection, self.after_paged_visible)

    def after_paged_visible(self, success):
        if success:
            print("✅ Paged content detected.")
            QTimer.singleShot(2000, self.snap_paged)
        else:
            print("❌ Timeout waiting for Paged content.")
            self.step_3_scrolled()

    def snap_paged(self):
        pix = self.window.grab()
        pix.save('screenshots/verify_align_paged.png')
        self.step_3_scrolled()

    def step_3_scrolled(self):
        print("📸 Switching to Scrolled Mode...")
        self.window.feed_browser.btn_mode_scrolled.click()
        wait_for_widgets(self.window.feed_browser, SectionHeader, self.after_scrolled_visible)

    def after_scrolled_visible(self, success):
        if success:
            print("✅ Scrolled content detected.")
            QTimer.singleShot(2000, self.snap_scrolled)
        else:
            print("❌ Timeout waiting for Scrolled content.")
            self.finish()

    def snap_scrolled(self):
        pix = self.window.grab()
        pix.save('screenshots/verify_align_scrolled.png')
        self.finish()

    def finish(self):
        print("🏁 Verification Complete.")
        self.app.quit()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    logger.setup_logging(debug=True)
    UIConstants.init_scale()
    
    config = ConfigManager()
    window = MainWindow(config)
    window.resize(1024, 768)
    window.show()
    
    ThemeManager.apply_theme(app, "dark")
    Path("screenshots").mkdir(exist_ok=True)
    
    # We need a dummy loop to satisfy the async parts of the app if any
    # but we will drive the test via QTimers
    verifier = Verifier(app, window, config)
    QTimer.singleShot(500, verifier.run)
    
    sys.exit(app.exec())
