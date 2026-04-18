#!/bin/bash
set -e

# This is the most basic of tests.  Launch the app for 5 seconds, to make sure it doesn't crash!
# !! This is not a substitue for true unit testing, but a quick validation

# Base directory for the project
BASE_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
VENV_PYTHON="/home/tony/cc/test/venv/bin/python"

# Ensure we're running main.py from the project root
cd "$BASE_DIR"

# 1, First do the launch test to find any quick errors
echo "🚀 Launching ComicCatcher Smoke Test (5s timeout)..."

# Execute in headless/offscreen mode
export QT_QPA_PLATFORM=offscreen
# Ensure package namespace is findable
export PYTHONPATH="$BASE_DIR/src:$PYTHONPATH"

# Execute the application with a 5 second timeout
# If the app crashes or fails to start, exit code will be non-zero (set -e)
$VENV_PYTHON src/comiccatcher/main.py --timeout 5

# 2. Then run the integrity script to catch missing imports and undefined symbols
echo "🔍 Running Integrity Check..."
$VENV_PYTHON scripts/validate_integrity.py

echo "✅ Smoke Test: App launched and exited cleanly."
