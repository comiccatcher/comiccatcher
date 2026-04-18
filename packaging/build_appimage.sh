#!/bin/bash
set -e

# Project root
BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$BASE_DIR"

# 1. Build the wheel
echo "📦 Building wheel..."
rm -rf dist/*.whl
python3 -m build --wheel --outdir dist/
WHEEL_FILE=$(ls dist/*.whl | head -n 1)

# 2. Prepare Metadata
echo "📂 Preparing metadata..."
METADATA_DIR="packaging/metadata"
rm -rf "$METADATA_DIR"
mkdir -p "$METADATA_DIR/usr/share/applications"
mkdir -p "$METADATA_DIR/usr/share/icons/hicolor/256x256/apps"

cp packaging/comiccatcher.desktop "$METADATA_DIR/usr/share/applications/"
cp src/comiccatcher/resources/app_256.png "$METADATA_DIR/usr/share/icons/hicolor/256x256/apps/comiccatcher.png"

# Custom AppRun to ensure entry point execution
cat > "$METADATA_DIR/AppRun" << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
export PATH="${HERE}/opt/python3.12/bin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/opt/python3.12/lib:${LD_LIBRARY_PATH}"
export PYTHONPATH="${HERE}/opt/python3.12/lib/python3.12/site-packages:${PYTHONPATH}"
# Launch the application entry point
exec "${HERE}/opt/python3.12/bin/comiccatcher" "$@"
EOF
chmod +x "$METADATA_DIR/AppRun"

# 3. Build AppImage
echo "🚀 Building AppImage..."
# We use the python-appimage module installed via pip
python3 -m python_appimage build app . \
    --python-version 3.12 \
    --name ComicCatcher \
    -x "$METADATA_DIR"

# 4. Finalize
echo "🧹 Finalizing..."
mkdir -p dist
mv ComicCatcher-x86_64.AppImage dist/
rm -rf "$METADATA_DIR"
echo "✅ AppImage build complete: dist/ComicCatcher-x86_64.AppImage"
