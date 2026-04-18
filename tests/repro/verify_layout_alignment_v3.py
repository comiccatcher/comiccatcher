#!/usr/bin/env python3
import sys
import asyncio
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer
from qasync import QEventLoop

# Add current dir to sys.path
current_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(current_dir))

from comiccatcher.config import ConfigManager
from comiccatcher.ui.app_layout import MainWindow
from comiccatcher.ui.theme_manager import UIConstants, ThemeManager
from comiccatcher.ui.components.collapsible_section import CollapsibleSection
from comiccatcher.ui.components.section_header import SectionHeader
import comiccatcher.logger as logger

async def wait_for_widgets(parent, widget_class, timeout=30):
    """Polls the widget tree until at least one widget of widget_class is found."""
    start = asyncio.get_event_loop().time()
    while (asyncio.get_event_loop().time() - start) < timeout:
        widgets = parent.findChildren(widget_class)
        if widgets and any(w.isVisible() for w in widgets):
            return True
        await asyncio.sleep(0.5)
    return False

async def run_verification(app):
    print("🧪 Starting Robust Visual Layout Verification (qasync)...")
    logger.setup_logging(debug=True)
    UIConstants.init_scale()
    
    config = ConfigManager()
    window = MainWindow(config)
    window.resize(1024, 768)
    window.show()
    
    ThemeManager.apply_theme(app, "dark")
    Path("screenshots").mkdir(exist_ok=True)
    
    # 1. Library View
    print("📸 Loading Library View...")
    window.nav_list.setCurrentRow(1)
    if await wait_for_widgets(window, CollapsibleSection):
        print("✅ Library content detected.")
        await asyncio.sleep(2)
        window.grab().save('screenshots/verify_align_library.png')
    else:
        print("❌ Timeout waiting for Library content.")

    # 2. Paged Feed View
    print("📸 Loading Paged Feed View...")
    if config.feeds:
        codex_feed = next((f for f in config.feeds if "codex" in f.name.lower()), config.feeds[0])
        window.on_feed_selected(codex_feed)
        window.feed_browser.btn_mode_paged.click()
        
        if await wait_for_widgets(window.feed_browser, CollapsibleSection):
            print("✅ Paged content detected.")
            await asyncio.sleep(2)
            window.grab().save('screenshots/verify_align_paged.png')
        else:
            print("❌ Timeout waiting for Paged content.")

    # 3. Scrolled Feed View
    print("📸 Switching to Scrolled Mode...")
    window.feed_browser.btn_mode_scrolled.click()
    if await wait_for_widgets(window.feed_browser, SectionHeader):
        print("✅ Scrolled content detected.")
        await asyncio.sleep(2)
        window.grab().save('screenshots/verify_align_scrolled.png')
    else:
        print("❌ Timeout waiting for Scrolled content.")
    
    print("🏁 Verification Complete.")
    app.quit()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(run_verification(app))
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
