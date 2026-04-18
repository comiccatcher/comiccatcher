#!/usr/bin/env python3
import os
import sys
import asyncio
import subprocess
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from qasync import QEventLoop

# Add project to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))

from config import ConfigManager
from ui.app_layout import MainWindow

async def capture(name):
    await asyncio.sleep(2) # Wait for UI to settle
    path = f"screenshots/{name}.png"
    print(f"Capturing {path}...")
    subprocess.run(["scrot", "-u", path])

async def run_exercise():
    os.makedirs("screenshots", exist_ok=True)
    
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    config = ConfigManager()
    window = MainWindow(config)
    window.resize(1200, 800)
    window.show()
    
    themes = ["light", "dark", "oled", "blue"]
    views = [
        (1, "library"),
        (0, "feeds"),
        (2, "settings")
    ]
    
    for theme in themes:
        print(f"Testing theme: {theme}")
        config.set_theme(theme)
        window._apply_theme()
        
        for view_idx, view_name in views:
            window.nav_list.setCurrentRow(view_idx)
            window._on_sidebar_changed(view_idx)
            await capture(f"{theme}_{view_name}")
            
    print("Exercise complete.")
    app.quit()

if __name__ == "__main__":
    loop = QEventLoop(QApplication(sys.argv))
    asyncio.set_event_loop(loop)
    with loop:
        loop.run_until_complete(run_exercise())
