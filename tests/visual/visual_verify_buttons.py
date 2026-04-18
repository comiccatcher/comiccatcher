#!/usr/bin/env python3
import os
import sys
import asyncio
import time
from pathlib import Path

# Force offscreen rendering
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Add project root to sys.path
current_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(current_dir / "src"))

from PyQt6.QtWidgets import QApplication
from qasync import QEventLoop

from comiccatcher.config import ConfigManager
from comiccatcher.ui.app_layout import MainWindow, ViewIndex
from comiccatcher.models.feed_page import ItemType

async def run_visual_verification():
    print("🚀 Starting Visual Verification Driver...")
    
    app = QApplication.instance() or QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    config = ConfigManager()
    config.set_theme("light")
    
    window = MainWindow(config)
    window.resize(1280, 900)
    window.show()
    
    target_feed = next((f for f in config.feeds if "stump local" in f.name.lower()), None)
    if not target_feed:
        print("❌ FAILED: 'Stump Local' feed not found in config.")
        app.quit()
        return
        
    window.on_feed_selected(target_feed)
    
    # Wait for content
    found_item = None
    timeout = 15
    start_time = time.time()
    while time.time() - start_time < timeout:
        QApplication.processEvents()
        if hasattr(window.feed_browser, '_last_page') and window.feed_browser._last_page:
            for section in window.feed_browser._last_page.sections:
                for item in section.items:
                    if item.type == ItemType.BOOK and item.raw_pub:
                        found_item = item
                        break
                if found_item: break
        if found_item: break
        await asyncio.sleep(0.5)
        
    if not found_item:
        print("❌ FAILED: No books found.")
        app.quit()
        return
        
    # Open Detail View
    window.on_open_detail(found_item.raw_pub, found_item.identifier)
    
    # Wait for render
    print("[*] Waiting for Detail View render...")
    for _ in range(10):
        await asyncio.sleep(0.5)
        QApplication.processEvents()
    
    # Capture
    output_path = "verify_light_theme_buttons.png"
    pixmap = window.grab()
    pixmap.save(output_path)
    print(f"✅ SUCCESS: Screenshot saved to {output_path}")
    app.quit()

if __name__ == "__main__":
    asyncio.run(run_visual_verification())
