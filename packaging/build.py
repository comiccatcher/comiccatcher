#!/usr/bin/env python3
import os
import sys
import shutil
import subprocess
import platform
import argparse
from pathlib import Path

# Configuration
APP_NAME = "ComicCatcher"
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DIST_DIR = PROJECT_ROOT / "dist"
PACKAGING_DIR = PROJECT_ROOT / "packaging"

def log(msg):
    print(f"[*] {msg}")

def run(cmd, cwd=PROJECT_ROOT, env=None):
    log(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, env=env or os.environ, check=True)
    return result

def clean_build():
    for d in ["build", "dist", "comiccatcher.spec"]:
        p = PROJECT_ROOT / d
        if p.exists():
            if p.is_dir(): shutil.rmtree(p)
            else: p.unlink()

def run_pyinstaller(icon_path):
    # Core boilerplate using --onefile for a clean distribution.
    # We use --collect-all for comicbox and --additional-hooks-dir for custom hooks 
    # to ensure standalone builds work correctly with internal comicbox dependencies.
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--windowed",
        "--onefile",
        "--name", APP_NAME,
        "--icon", str(icon_path),
        "--additional-hooks-dir", str(PACKAGING_DIR),
        "--collect-submodules", "comiccatcher",
        "--collect-all", "comicbox",
        "--add-data", f"src/comiccatcher/resources{os.pathsep}comiccatcher/resources",
        "src/comiccatcher/main.py"
    ]
    run(cmd)

def build_linux():
    log("Building Linux AppImage (via PyInstaller)...")
    clean_build()
    
    # 1. Run PyInstaller to get a standalone binary
    icon_png = PROJECT_ROOT / "src/comiccatcher/resources/app_256.png"
    run_pyinstaller(icon_png)
    
    # 2. Wrap the binary in an AppImage structure
    appdir = PROJECT_ROOT / "AppDir"
    if appdir.exists(): shutil.rmtree(appdir)
    appdir.mkdir()
    (appdir / "usr/bin").mkdir(parents=True)
    
    # Copy the PyInstaller binary
    shutil.copy(DIST_DIR / APP_NAME, appdir / "usr/bin" / APP_NAME)
    
    # Metadata
    shutil.copy(PACKAGING_DIR / "linux/comiccatcher.desktop", appdir / "comiccatcher.desktop")
    shutil.copy(icon_png, appdir / "comiccatcher.png")
    
    # Custom AppRun that launches our binary
    with open(appdir / "AppRun", "w") as f:
        f.write(f'#!/bin/sh\nexec "$(dirname "$0")/usr/bin/{APP_NAME}" "$@"\n')
    (appdir / "AppRun").chmod(0o755)

    # 3. Pack with appimagetool
    appimagetool = PACKAGING_DIR / "appimagetool"
    if not appimagetool.exists():
        url = "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
        run(["curl", "-L", url, "-o", str(appimagetool)])
        appimagetool.chmod(0o755)
    
    env = os.environ.copy()
    env["ARCH"] = "x86_64"
    run([str(appimagetool), "-n", str(appdir), str(DIST_DIR / f"{APP_NAME}-x86_64.AppImage")], env=env)
    
    shutil.rmtree(appdir)
    log(f"Linux build complete: {DIST_DIR}/{APP_NAME}-x86_64.AppImage")

def build_windows():
    log("Building Windows EXE (via PyInstaller)...")
    clean_build()
    
    from PIL import Image
    
    # Ensure build directory exists for temporary icon
    build_dir = PROJECT_ROOT / "build"
    build_dir.mkdir(exist_ok=True)
    
    icon_ico = build_dir / "comiccatcher.ico"
    img = Image.open(PROJECT_ROOT / "src/comiccatcher/resources/app_256.png")
    img.save(icon_ico, format='ICO', sizes=[(16,16), (32,32), (48,48), (64,64), (128,128), (256,256)])
    
    run_pyinstaller(icon_ico)
    log(f"Windows build complete: {DIST_DIR}/{APP_NAME}.exe")

def build_macos():
    log("Building macOS DMG (via PyInstaller)...")
    clean_build()
    
    icon_icns = PROJECT_ROOT / "src/comiccatcher/resources/app_256.icns"
    if not icon_icns.exists():
        log("No .icns found, falling back to png for icon...")
        icon_arg = PROJECT_ROOT / "src/comiccatcher/resources/app_256.png"
    else:
        icon_arg = icon_icns

    run_pyinstaller(icon_arg)
    
    # Pack into dmg using hdiutil
    app_path = DIST_DIR / f"{APP_NAME}.app"
    dmg_path = DIST_DIR / f"{APP_NAME}-macOS.dmg"
    log(f"Creating DMG at {dmg_path}...")
    run(["hdiutil", "create", "-volname", APP_NAME, "-srcfolder", str(app_path), "-ov", "-format", "UDZO", str(dmg_path)])
    
    log(f"macOS build complete: {dmg_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--linux", action="store_true")
    parser.add_argument("--windows", action="store_true")
    parser.add_argument("--macos", action="store_true")
    args = parser.parse_args()

    OS = platform.system().lower()
    if args.linux or (not args.windows and not args.macos and OS == "linux"):
        build_linux()
    elif args.windows or (not args.linux and not args.macos and OS == "windows"):
        build_windows()
    elif args.macos or (not args.linux and not args.windows and OS == "darwin"):
        build_macos()
