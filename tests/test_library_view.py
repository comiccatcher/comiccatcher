import sys
import os
import asyncio
from pathlib import Path

# Add project to path
PROJECT_ROOT = Path("/home/tony/cc").absolute()
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "comiccatcher"))
os.chdir(str(PROJECT_ROOT))

# Patch asyncio.create_task for headless testing
_orig = asyncio.create_task
def _safe(coro, **kw):
    try:
        return _orig(coro, **kw)
    except RuntimeError:
        if hasattr(coro, "close"):
            coro.close()
        return None
asyncio.create_task = _safe

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, Qt
from ui.theme_manager import ThemeManager, UIConstants
from ui.views.local_library import LocalLibraryView
from config import ConfigManager, CONFIG_DIR
from api.image_manager import ImageManager
from api.local_db import LocalLibraryDB

app = QApplication(sys.argv)
UIConstants.init_scale()

config = ConfigManager()
image_manager = ImageManager(None)
local_db = LocalLibraryDB(CONFIG_DIR / "library.db")

themes = ['light', 'dark', 'oled', 'blue', 'light_blue']
idx = [0]
win = [None]

def next_theme():
    if idx[0] >= len(themes):
        print("Capture complete.")
        app.quit()
        return
    
    t = themes[idx[0]]
    print(f"Capturing Library - Theme: {t}")
    
    if win[0]:
        win[0].close()
        win[0].deleteLater()
    
    ThemeManager.apply_theme(app, t)
    
    # Create fresh view
    w = LocalLibraryView(config, image_manager, local_db)
    
    # MOCK DATA for visual testing
    from ui.views.local_library import LibrarySection
    for i in range(3):
        section = LibrarySection(f"Test Section {i+1}", [], lambda x: None)
        w.dash_layout.addWidget(section)
    
    win[0] = w
    w.resize(1200, 800)
    w.setWindowTitle(f"Library - {t}")
    w.show()
    
    # Force a refresh to show structure
    w.refresh()
    
    # Defer capture to allow layout and theme to settle
    QTimer.singleShot(800, lambda: capture(t))

def capture(t):
    save_path = f"screenshots/test_library_{t}.png"
    os.makedirs("screenshots", exist_ok=True)
    
    # Grab the window
    pixmap = win[0].grab()
    pixmap.save(save_path)
    print(f"Saved {save_path}")
    
    idx[0] += 1
    QTimer.singleShot(100, next_theme)

if __name__ == "__main__":
    QTimer.singleShot(100, next_theme)
    sys.exit(app.exec())
