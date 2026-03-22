import sys
import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt
from qasync import QEventLoop

# Ensure offscreen platform for headless environments
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Add project roots to path
sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), "comiccatcher"))

from comiccatcher.config import ConfigManager
from comiccatcher.ui.app_layout import MainWindow
from comiccatcher.ui.views.local_library import LocalLibraryView, SeriesSection

def create_mock_comic(path: Path):
    import zipfile
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('ComicInfo.xml', b'<?xml version="1.0"?><ComicInfo><Title>Test</Title></ComicInfo>')

async def verify_library_stability():
    """
    E2E Layout Verification:
    Ensures that collapsed library groups do not shift vertically when the window is resized.
    """
    print("🚀 Launching Library Stability Verification...")
    
    app = QApplication.instance() or QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    # Create temp library
    tmp_dir = Path(tempfile.mkdtemp())
    try:
        (tmp_dir / "Series A").mkdir()
        (tmp_dir / "Series B").mkdir()
        create_mock_comic(tmp_dir / "Series A" / "Issue 1.cbz")
        create_mock_comic(tmp_dir / "Series A" / "Issue 2.cbz")
        create_mock_comic(tmp_dir / "Series B" / "Issue 1.cbz")
        create_mock_comic(tmp_dir / "Series B" / "Issue 2.cbz")

        config = ConfigManager()
        config.set_library_dir(str(tmp_dir))
        config.set_library_view_mode(1) # Force Series/Grouped
        
        window = MainWindow(config)
        window.show()
        
        # Wait for initial scan to populate
        print("Waiting for scan to complete...")
        for _ in range(40):
            if not window.local_library_view.scanner.is_scanning:
                break
            await asyncio.sleep(0.5)
        
        # Navigate to Library
        print("Navigating to Library via Sidebar...")
        window.nav_list.setCurrentRow(1)
        await asyncio.sleep(3)
        
        view = window.local_library_view
        
        # Reproduction steps: Collapse all but the first
        print("Finding sections...")
        sections = []
        for _ in range(20):
            sections = view.grouped_container.findChildren(SeriesSection)
            if sections: break
            # Try triggering a load if empty
            await view._load_grouped()
            await asyncio.sleep(1)
            
        if not sections:
            print("❌ Error: No library sections found to measure.")
            app.quit()
            return

        sections.sort(key=lambda s: s.mapToGlobal(s.rect().topLeft()).y())
        print(f"Found {len(sections)} sections. Collapsing all but the first...")
        
        for s in sections[1:]:
            s.set_expanded(False)
        await asyncio.sleep(1)

        def get_y_positions():
            sects = view.grouped_container.findChildren(SeriesSection)
            sects.sort(key=lambda s: s.mapToGlobal(s.rect().topLeft()).y())
            return [s.mapTo(view.grouped_container, s.rect().topLeft()).y() for s in sects]

        initial_y = get_y_positions()
        print(f"Initial positions: {initial_y}")
        
        success = True
        for h in [1000, 1400, 1800]:
            window.resize(window.width(), h)
            await asyncio.sleep(0.5)
            current_y = get_y_positions()
            print(f"Height {h} positions: {current_y}")
            
            if current_y != initial_y:
                print(f"⚠️ SHIFT DETECTED at height {h}!")
                success = False

        if success:
            print("\n✅ SUCCESS: Library groups remained stable during resize.")
        else:
            print("\n❌ FAILURE: Library groups shifted vertically.")
            sys.exit(1)

        app.quit()
    finally:
        shutil.rmtree(tmp_dir)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    with loop:
        loop.run_until_complete(verify_library_stability())
