#!/usr/bin/env python3
import sys
from PyQt6.QtWidgets import QApplication, QWidget

def check_deps():
    try:
        app = QApplication(sys.argv)
        w = QWidget()
        w.setWindowTitle("Dependency Check")
        print("SUCCESS: PyQt6 initialized successfully.")
        return 0
    except Exception as e:
        print(f"FAILURE: Could not initialize PyQt6: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(check_deps())
