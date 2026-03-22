
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen" 

import sys
import asyncio
import time
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSize
from qasync import QEventLoop

# Add project root to sys.path
base_dir = Path(__file__).parent.parent
sys.path.insert(0, str(base_dir))

from config import ConfigManager
from ui.app_layout import MainWindow

async def capture_themes():
    print("🚀 Starting Theme Screenshot Capture (Fast Mode)...")
    
    # Ensure screenshot directory exists
    screenshot_dir = base_dir / "screenshots"
    screenshot_dir.mkdir(exist_ok=True)
    
    themes = ["light", "dark", "oled", "blue", "light_blue"]
    views = [
        {"name": "feeds", "index": 0},
        {"name": "library", "index": 1},
        {"name": "settings", "index": 2}
    ]
    
    # Setup App
    app = QApplication.instance() or QApplication(sys.argv)
    config = ConfigManager()
    window = MainWindow(config)
    window.resize(1200, 800)
    window.show()
    
    # Process initial events
    await asyncio.sleep(1)
    
    for theme in themes:
        print(f"🎨 Theme: {theme}")
        config.set_theme(theme)
        window._apply_theme()
        await asyncio.sleep(1) # Let theme propagate
        
        for view in views:
            print(f"  📸 Capturing {view['name']}...")
            window.content_stack.setCurrentIndex(view['index'])
            # Specific logic for Library to ensure it loads something if possible
            if view['name'] == "library":
                window.local_library_view.refresh()
            
            await asyncio.sleep(1) # Settle layout
            
            # Take screenshot
            pixmap = window.grab()
            save_path = screenshot_dir / f"{theme}_{view['name']}.png"
            pixmap.save(str(save_path))
            print(f"     Saved: {save_path.name}")

    print("✅ Capture Complete.")
    app.quit()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    with loop:
        try:
            loop.run_until_complete(capture_themes())
        except Exception as e:
            print(f"❌ Error: {e}")
            sys.exit(1)
