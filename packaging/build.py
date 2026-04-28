import os
import sys
import subprocess
import argparse
from pathlib import Path

def build_windows():
    print("[*] Building Windows EXE (via PyInstaller)...")
    
    # Path setup
    root = Path(__file__).parent.parent.resolve()
    src = root / "src"
    hooks = root / "packaging"
    ico = root / "build" / "comiccatcher.ico"
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--windowed",
        "--onefile",
        "--name", "ComicCatcher",
        "--icon", str(ico),
        "--additional-hooks-dir", str(hooks),
        "--collect-submodules", "comiccatcher",
        "--collect-all", "comicbox",
        "--add-data", f"src/comiccatcher/resources;comiccatcher/resources",
        "src/comiccatcher/main.py"
    ]
    
    print(f"[*] Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=str(root))
    print(f"[*] Windows build complete: {root}/dist/ComicCatcher.exe")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows", action="store_true")
    args = parser.parse_args()
    
    if args.windows or sys.platform == "win32":
        build_windows()
    else:
        print("Unsupported platform for this script (Windows focus).")
