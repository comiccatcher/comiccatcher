import sys
import asyncio
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QPushButton
from PyQt6.QtTest import QTest
from PyQt6.QtCore import Qt
from qasync import QEventLoop

from config import ConfigManager
from ui.app_layout import MainWindow

async def drive_gui():
    config_manager = ConfigManager()
    config_manager.set_scroll_method("viewport")
    
    window = MainWindow(config_manager)
    window.show()
    browser = window.browser_view
    
    if config_manager.profiles:
        profile = config_manager.profiles[0]
        print(f"Driving GUI for profile: {profile.name}")
        window.on_profile_selected(profile)
        await asyncio.sleep(2) 
        
        # Navigate to "Series" - look for the button in the dashboard
        print("Action: Looking for Series link...")
        series_btn = None
        for i in range(browser.content_layout.count()):
            w = browser.content_layout.itemAt(i).widget()
            if w:
                # Groups or nav buttons
                btns = w.findChildren(QPushButton)
                for b in btns:
                    if "Series" in b.text():
                        series_btn = b
                        break
            if series_btn: break
            
        if series_btn:
            print(f"Clicking: {series_btn.text()}")
            series_btn.click()
            await asyncio.sleep(3) # Wait for Series feed
        else:
            print("Could not find Series link, staying on current.")

        print(f"Feed Loaded: {browser.status_label.text()}")
        print(f"Buffer size: {len(browser.items_buffer)}, Total items: {browser.total_items}, Items per screen: {browser.items_per_screen}")
        print(f"Initial UI: {browser.viewport_paging_bar.label_status.text()}")
        
        browser.setFocus()
        
        # 2. Simulate Arrow Right (Next)
        print("Action: Press Right Arrow")
        QTest.keyClick(browser, Qt.Key.Key_Right)
        await asyncio.sleep(1)
        print(f"After Right: {browser.viewport_paging_bar.label_status.text()} (Offset: {browser.viewport_offset})")
        
        # 3. Simulate End (Jump to last)
        print("Action: Press End Key")
        QTest.keyClick(browser, Qt.Key.Key_End)
        await asyncio.sleep(4) 
        print(f"After End: {browser.viewport_paging_bar.label_status.text()} (Offset: {browser.viewport_offset}, Absolute: {browser.buffer_absolute_offset})")
        
        # 4. Simulate Arrow Left (Previous)
        print("Action: Press Left Arrow")
        QTest.keyClick(browser, Qt.Key.Key_Left)
        await asyncio.sleep(1)
        print(f"After Left: {browser.viewport_paging_bar.label_status.text()} (Offset: {browser.viewport_offset})")

    else:
        print("No profiles found to test.")

    print("Driving finished.")
    QApplication.instance().quit()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    with loop:
        loop.run_until_complete(drive_gui())
