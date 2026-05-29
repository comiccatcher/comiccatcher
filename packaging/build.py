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
    license_rtf = PACKAGING_DIR / "LICENSE.rtf"
    if license_rtf.exists():
        license_rtf.unlink()

def run_pyinstaller(icon_path, onedir=False):
    # Core boilerplate using PyInstaller for a clean distribution.
    # We use --collect-all for comicbox and --additional-hooks-dir for custom hooks 
    # to ensure standalone builds work correctly with internal comicbox dependencies.
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--windowed",
    ]
    if onedir:
        cmd.append("--onedir")
    else:
        cmd.append("--onefile")
        
    cmd.extend([
        "--name", APP_NAME,
        "--icon", str(icon_path),
        "--additional-hooks-dir", str(PACKAGING_DIR),
        "--collect-submodules", "comiccatcher",
        "--collect-all", "comicbox"
    ])
    
    if platform.system().lower() == "windows":
        cmd.extend(["--collect-all", "windows_trackpad_helper"])
        
    cmd.extend([
        "--add-data", f"src/comiccatcher/resources{os.pathsep}comiccatcher/resources",
        "src/comiccatcher/main.py"
    ])
    run(cmd)

def deduplicate_with_symlinks(target_internal_dir):
    """Finds duplicate libraries inside subfolders of _internal and replaces them with relative symlinks."""
    log(f"Deduplicating files in {target_internal_dir} using relative symbolic links...")
    root_files = {}
    for entry in target_internal_dir.iterdir():
        if entry.is_file() and not entry.is_symlink():
            root_files[entry.name] = entry
            
    for root, dirs, files in os.walk(target_internal_dir):
        if Path(root) == target_internal_dir:
            continue
        for f in files:
            file_path = Path(root) / f
            if f in root_files and not file_path.is_symlink():
                root_file_path = root_files[f]
                if file_path.stat().st_size == root_file_path.stat().st_size:
                    rel_depth = len(Path(root).relative_to(target_internal_dir).parts)
                    rel_target = ("../" * rel_depth) + f
                    file_path.unlink()
                    file_path.symlink_to(rel_target)

def build_deb(icon_png):
    log("Packaging Debian package (.deb)...")
    deb_dir = PROJECT_ROOT / "build/deb_stage"
    if deb_dir.exists():
        shutil.rmtree(deb_dir)
        
    (deb_dir / "DEBIAN").mkdir(parents=True)
    (deb_dir / "opt/comiccatcher").mkdir(parents=True)
    (deb_dir / "usr/bin").mkdir(parents=True)
    (deb_dir / "usr/share/applications").mkdir(parents=True)
    (deb_dir / "usr/share/pixmaps").mkdir(parents=True)
    
    # 1. Copy one-folder files
    src_folder = DIST_DIR / APP_NAME
    dest_folder = deb_dir / "opt/comiccatcher"
    for item in src_folder.iterdir():
        if item.is_dir():
            shutil.copytree(item, dest_folder / item.name)
        else:
            shutil.copy(item, dest_folder / item.name)
            
    # Deduplicate redundant library files in _internal folder using relative symlinks
    internal_dir = dest_folder / "_internal"
    if internal_dir.exists():
        deduplicate_with_symlinks(internal_dir)

    # Strip debugging symbols from all binary shared objects and the main executable to reduce file size dramatically
    log(f"Stripping debugging symbols from binaries in {dest_folder}...")
    for root, _, files in os.walk(dest_folder):
        for f in files:
            file_path = Path(root) / f
            if file_path.suffix == ".so" or (file_path.name == "ComicCatcher" and not file_path.is_symlink()):
                try:
                    subprocess.run(["strip", "--strip-unneeded", str(file_path)], check=False, capture_output=True)
                except Exception:
                    pass

    # 2. Copy metadata & icon
    shutil.copy(icon_png, deb_dir / "usr/share/pixmaps/comiccatcher.png")
    shutil.copy(PACKAGING_DIR / "linux/comiccatcher.desktop", deb_dir / "usr/share/applications/comiccatcher.desktop")
    
    # 3. Create launcher script
    launcher = deb_dir / "usr/bin/comiccatcher"
    launcher.write_text("#!/bin/sh\nexec /opt/comiccatcher/ComicCatcher \"$@\"\n")
    launcher.chmod(0o755)
    
    # 4. Create control file
    version = "0.7.1"
    try:
        init_path = PROJECT_ROOT / "src/comiccatcher/__init__.py"
        for line in init_path.read_text(encoding='utf-8').splitlines():
            if line.startswith("__version__"):
                version = line.split("=")[1].strip().strip('"').strip("'")
                break
    except Exception:
        pass
        
    control_content = f"""Package: comiccatcher
Version: {version}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: ComicCatcher Developers <info@comiccatcher.org>
Description: OPDS Comic Reader and Downloader
 A desktop OPDS 2.0/1.2 browser and comic downloader/streamer/reader.
"""
    (deb_dir / "DEBIAN/control").write_text(control_content, encoding='utf-8')
    
    # 5. Run dpkg-deb
    run(["dpkg-deb", "-Zxz", "-z9", "--build", str(deb_dir), str(DIST_DIR / f"{APP_NAME.lower()}-amd64.deb")])
    log(f"Debian packaging complete: {DIST_DIR}/{APP_NAME.lower()}-amd64.deb")

def build_linux():
    log("Building Linux Targets (via PyInstaller)...")
    clean_build()
    icon_png = PROJECT_ROOT / "src/comiccatcher/resources/app_256.png"
    
    # 1. Build unpacked folder layout first
    run_pyinstaller(icon_png, onedir=True)
    
    # 2. Package into DEB
    build_deb(icon_png)
    
    # 3. Wrap the stripped, deduplicated binary folder in an AppImage structure
    appdir = PROJECT_ROOT / "AppDir"
    if appdir.exists(): shutil.rmtree(appdir)
    appdir.mkdir()
    
    # Copy the pre-built, stripped, deduplicated folder directly to AppDir/usr/bin
    shutil.copytree(PROJECT_ROOT / "build/deb_stage/opt/comiccatcher", appdir / "usr/bin")
    
    # Metadata
    shutil.copy(PACKAGING_DIR / "linux/comiccatcher.desktop", appdir / "comiccatcher.desktop")
    shutil.copy(icon_png, appdir / "comiccatcher.png")
    
    # Custom AppRun that launches our binary
    with open(appdir / "AppRun", "w") as f:
        f.write(f'#!/bin/sh\nexec "$(dirname "$0")/usr/bin/{APP_NAME}" "$@"\n')
    (appdir / "AppRun").chmod(0o755)

    # 4. Pack with appimagetool
    appimagetool = PACKAGING_DIR / "appimagetool"
    if not appimagetool.exists():
        url = "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
        run(["curl", "-L", url, "-o", str(appimagetool)])
        appimagetool.chmod(0o755)
    
    env = os.environ.copy()
    env["ARCH"] = "x86_64"
    run([str(appimagetool), "-n", str(appdir), str(DIST_DIR / f"{APP_NAME}-x86_64.AppImage")], env=env)
    
    # Clean up temporary staging directories
    shutil.rmtree(appdir)
    deb_stage = PROJECT_ROOT / "build/deb_stage"
    if deb_stage.exists():
        shutil.rmtree(deb_stage)
        
    log(f"Linux build complete: {DIST_DIR}/{APP_NAME}-x86_64.AppImage")

def generate_license_rtf():
    license_txt_path = PROJECT_ROOT / "LICENSE"
    license_rtf_path = PACKAGING_DIR / "LICENSE.rtf"
    if not license_txt_path.exists():
        log("LICENSE file not found, skipping RTF generation")
        return
    
    text = license_txt_path.read_text(encoding="utf-8")
    
    # Escape RTF special characters
    escaped = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
    
    # Format newlines as RTF paragraph breaks
    rtf_paragraphs = []
    for line in escaped.splitlines():
        rtf_paragraphs.append(line + "\\par")
        
    rtf_content = "{\\rtf1\\ansi\\deff0\n{\\fonttbl{\\f0\\fnil\\fcharset0 Arial;}}\n\\f0\\fs20\n" + "\n".join(rtf_paragraphs) + "\n}"
    
    license_rtf_path.write_text(rtf_content, encoding="ascii", errors="ignore")
    log("Generated packaging/LICENSE.rtf from LICENSE")

def build_windows():
    log("Building Windows Targets (via PyInstaller)...")
    clean_build()
    
    # Generate the license RTF for the WiX installer UI
    generate_license_rtf()
    
    from PIL import Image
    
    # Ensure build directory exists for temporary icon
    build_dir = PROJECT_ROOT / "build"
    build_dir.mkdir(exist_ok=True)
    
    icon_ico = build_dir / "comiccatcher.ico"
    img = Image.open(PROJECT_ROOT / "src/comiccatcher/resources/app_256.png")
    # Set bitmap_format=True to write standard raw BMP format inside the ICO file (instead of PNG compression).
    # Windows Installer's legacy extraction does not support PNG-compressed icons (which is default for 256x256 in Pillow).
    img.save(icon_ico, format='ICO', bitmap_format=True, sizes=[(16,16), (32,32), (48,48), (64,64), (128,128), (256,256)])
    
    # 1. Build unpacked folder layout (for WiX MSI packaging)
    run_pyinstaller(icon_ico, onedir=True)
    
    # 2. Build standalone single-file layout
    run_pyinstaller(icon_ico, onedir=False)
    
    log(f"Windows build complete: both {DIST_DIR}/{APP_NAME} folder and {DIST_DIR}/{APP_NAME}.exe created.")

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
