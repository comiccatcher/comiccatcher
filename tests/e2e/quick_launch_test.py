#!/usr/bin/env python3

import sys
import asyncio
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from qasync import QEventLoop

# Add current dir to sys.path
current_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(current_dir))

from comiccatcher.config import ConfigManager
from comiccatcher.ui.app_layout import MainWindow

def main():
    print("🚀 Performing Quick Launch Test (5s)...")
    config = ConfigManager()
    
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    try:
        window = MainWindow(config)
        window.show()
        print("  ✅ MainWindow initialized and shown.")
        
        # Exit successfully after 5 seconds
        QTimer.singleShot(5000, lambda: (print("  ✅ Application stayed up for 5s. Success."), app.quit()))
        
        loop.run_forever()
    except Exception as e:
        print(f"❌ FATAL: Application crashed during launch: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        loop.close()

if __name__ == "__main__":
    main()
