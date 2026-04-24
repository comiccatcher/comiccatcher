# ComicCatcher — Agent Testing Guide

A practical reference for agents running visual, behavioural, and unit tests against the ComicCatcher PyQt6 UI in a headless environment.

---

## Table of Contents

1. [Quick Start](#1-quick-start)
2. [Environment](#2-environment)
3. [Standard Mock Objects](#3-standard-mock-objects)
4. [Standard Test Data](#4-standard-test-data)
5. [Screenshot Testing](#5-screenshot-testing)
6. [Behavioural / Signal Testing](#6-behavioural--signal-testing)
7. [Widget Coordinate & Alignment Testing](#7-widget-coordinate--alignment-testing)
8. [Unit Tests (pytest)](#8-unit-tests-pytest)
9. [Common Issues](#9-common-issues)

---

## 1. Quick Start

Copy-paste to verify the environment is ready before writing any test:

```bash
# Check Xvfb is running (start it if not)
pgrep Xvfb || Xvfb :99 -screen 0 1280x800x24 &

# Smoke-test: render the settings view and save a screenshot
DISPLAY=:99 /home/tony/cc/test/venv/bin/python - <<'EOF'
import sys, os
sys.path.insert(0, '/home/tony/cc/comiccatcher')
os.chdir('/home/tony/cc/comiccatcher')
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from ui.theme_manager import ThemeManager, UIConstants
app = QApplication(sys.argv)
UIConstants.init_scale()
ThemeManager.apply_theme(app, 'dark')
from ui.views.settings import SettingsView
from config import ConfigManager
v = SettingsView(ConfigManager())
v.resize(800, 600)
v.show()
QTimer.singleShot(400, lambda: (app.primaryScreen().grabWindow(v.winId()).save('/tmp/smoke.png'), app.quit()))
app.exec()
EOF
```

Then `Read /tmp/smoke.png` to confirm rendering worked.

---

## 2. Environment

### Paths

| Resource | Path |
|---|---|
| Project root | `/home/tony/cc/comiccatcher` |
| Test venv | `/home/tony/cc/test/venv` |
| Python binary | `/home/tony/cc/test/venv/bin/python` |
| Screenshots (convention) | `/tmp/*.png` |
| Log files (convention) | `/tmp/*.log` |

Always use the **absolute Python path** — do not rely on `python` or `python3`
from `PATH`, and do not use `source activate` (shell state does not persist
between tool calls in most agent environments).

### Every test script must start with

```python
import sys, os
sys.path.insert(0, '/home/tony/cc/comiccatcher')
os.chdir('/home/tony/cc/comiccatcher')
```

### Virtual display

All PyQt6 code requires a display. Use Xvfb on the headless machine:

```bash
pgrep Xvfb || Xvfb :99 -screen 0 1280x800x24 &
DISPLAY=:99 /home/tony/cc/test/venv/bin/python /tmp/my_script.py
```

### Async patch (required for most views)

Many widgets call `asyncio.create_task` during `__init__`. Without a running
qasync loop this raises `RuntimeError`. Patch it **before any project imports**:

```python
import asyncio
_orig = asyncio.create_task
def _safe(coro, **kw):
    try:
        return _orig(coro, **kw)
    except RuntimeError:
        coro.close()
        return None
asyncio.create_task = _safe
```

### UIConstants initialisation

Always call `UIConstants.init_scale()` before creating any widget — it
initialises all pixel constants (card sizes, spacing, font sizes, etc.).

```python
from ui.theme_manager import ThemeManager, UIConstants
app = QApplication(sys.argv)
UIConstants.init_scale()
ThemeManager.apply_theme(app, 'dark')
```

---

## 3. Standard Mock Objects

Copy these verbatim — they satisfy the constructor requirements of all feed
views without any network access.

```python
class MockImageManager:
    api_client = None
    def get_image_sync(self, url): return None
    async def get_image_b64(self, url): pass

class MockOPDSClient:
    async def get_feed(self, url, **kw):
        raise RuntimeError("no network")
```

---

## 4. Standard Test Data

### Minimal FeedPage (RIBBON sections only)

Use this for dashboard-style views and anything that doesn't need pagination.

```python
from models.feed_page import FeedPage, FeedSection, FeedItem, ItemType, SectionLayout

def make_page():
    sections = []
    for i, (title, n) in enumerate([("Keep Reading", 8), ("Latest Unread", 6), ("Oldest Unread", 5)]):
        items = [
            FeedItem(identifier=f"s{i}_i{j}", title=f"Comic {j+1}", type=ItemType.BOOK)
            for j in range(n)
        ]
        sections.append(FeedSection(
            section_id=f"sec_{i}",
            title=title,
            items=items,
            layout=SectionLayout.RIBBON,
            items_per_page=n,
            current_page=1,
        ))
    return FeedPage(title="Test Feed", sections=sections)
```

### Large GRID section (for scrolled-view pagination testing)

```python
def make_large_page(total=500):
    # First page of items — the model fills in the rest sparsely
    first_page = [
        FeedItem(identifier=f"item_{j}", title=f"Issue {j+1}", type=ItemType.BOOK)
        for j in range(50)
    ]
    grid_section = FeedSection(
        section_id="all_issues",
        title="All Issues",
        items=first_page,
        layout=SectionLayout.RIBBON,   # server default; render() promotes to GRID
        total_items=total,
        items_per_page=50,
        current_page=1,
    )
    ribbon = FeedSection(
        section_id="keep_reading",
        title="Keep Reading",
        items=[FeedItem(identifier=f"kr_{j}", title=f"Comic {j+1}", type=ItemType.BOOK) for j in range(8)],
        layout=SectionLayout.RIBBON,
        items_per_page=8,
        current_page=1,
    )
    return FeedPage(title="Library", sections=[ribbon, grid_section])
```

> **Note:** `ScrolledFeedView.render()` promotes the largest section to GRID
> regardless of its `layout` attribute — the server's default is RIBBON.

---

## 5. Screenshot Testing

### Pattern 1: Single widget

```python
import sys, os, asyncio
# async patch here ...
sys.path.insert(0, '/home/tony/cc/comiccatcher')
os.chdir('/home/tony/cc/comiccatcher')

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from ui.theme_manager import ThemeManager, UIConstants

app = QApplication(sys.argv)
UIConstants.init_scale()
ThemeManager.apply_theme(app, 'dark')

from ui.views.paged_feed_view import PagedFeedView

img = MockImageManager()
view = PagedFeedView(img, set())
view.resize(1100, 700)
view.show()
view.render(make_page())

QTimer.singleShot(500, lambda: (
    app.primaryScreen().grabWindow(view.winId()).save('/tmp/paged.png'),
    app.quit()
))
app.exec()
```

Key rules:
- Apply theme **before** creating widgets (icons colour at init time)
- `QTimer.singleShot` delay: 400–600 ms is enough for synchronous views;
  use 1 000+ ms if the view triggers async cover loading
- `UIConstants.init_scale()` must come before any widget creation

### Pattern 2: Stepped sequence

Use a `step` counter when you need to render multiple states in order
(e.g. render → interact → capture).

```python
step = [0]

def run():
    s = step[0]; step[0] += 1
    if s == 0:
        view.render(make_page())
        QTimer.singleShot(500, run)
    elif s == 1:
        app.primaryScreen().grabWindow(view.winId()).save('/tmp/state1.png')
        # change state ...
        QTimer.singleShot(300, run)
    elif s == 2:
        app.primaryScreen().grabWindow(view.winId()).save('/tmp/state2.png')
        app.quit()

QTimer.singleShot(200, run)
app.exec()
```

### Pattern 3: Per-theme comparison

Most accurate — applies theme before creating each fresh widget.

```python
themes = ['light', 'dark', 'oled', 'blue']
idx = [0]; win = [None]

def next_theme():
    if idx[0] >= len(themes):
        app.quit(); return
    t = themes[idx[0]]
    if win[0]: win[0].close()
    ThemeManager.apply_theme(app, t)
    w = MyView(...)
    win[0] = w
    w.resize(800, 600); w.show()
    QTimer.singleShot(400, lambda: capture(t))

def capture(t):
    app.primaryScreen().grabWindow(win[0].winId()).save(f'/tmp/view_{t}.png')
    idx[0] += 1
    QTimer.singleShot(100, next_theme)

QTimer.singleShot(200, next_theme)
app.exec()
```

### Reading screenshots

Use the `Read` tool directly on the saved path — screenshots render inline:

```
Read /tmp/paged.png
Read /tmp/scrolled.png
```

---

## 6. Behavioural / Signal Testing

Test that signals fire correctly and that clicks propagate through the full
chain without running a full application.

### Signal capture pattern

```python
received = []
view.item_clicked.connect(lambda item, ctx: received.append(item.title))

# ... trigger the action ...

# Assert after a short delay
QTimer.singleShot(200, lambda: (
    print(f"received: {received}"),
    assert received == ["Expected Title"],
    app.quit()
))
```

### Simulating a click via the model index

When you need to trigger a `clicked` signal without a real mouse event:

```python
ribbon = list(scrolled._ribbons.values())[0]
idx = ribbon.model().index(0)       # first item
ribbon.clicked.emit(idx)            # fires _on_ribbon_clicked
```

For grid views:

```python
view = scrolled._grids['all_issues']
view.clicked.emit(view.model().index(0))
```

### Verifying model state

After `render()`, check that models are populated correctly:

```python
# Ribbon section
ribbon = scrolled._ribbons['keep_reading']
model = ribbon.model()
print(f"rowCount={model.rowCount()}")
print(f"get_item(0)={model.get_item(0)}")

# Grid section
grid_model = scrolled._models['all_issues']
print(f"grid rows={grid_model.rowCount()}")
print(f"sparse_items keys={sorted(grid_model._sparse_items.keys())}")
```

### Full end-to-end signal test example

```python
def check():
    # Verify render populated the models
    assert len(scrolled._ribbons) == 1
    assert len(scrolled._grids) == 1

    # Verify clicking a ribbon item emits item_clicked
    clicked = []
    scrolled.item_clicked.connect(lambda item, ctx: clicked.append(item))
    ribbon = list(scrolled._ribbons.values())[0]
    ribbon.clicked.emit(ribbon.model().index(0))
    assert len(clicked) == 1
    assert clicked[0].type != ItemType.EMPTY

    print("All assertions passed")
    app.quit()

QTimer.singleShot(400, check)
```

---

## 7. Widget Coordinate & Alignment Testing

Use `DebugOverlay` to dump every widget's position in global coordinates.
This is the primary tool for diagnosing alignment and spacing issues.

### Activating at runtime

Press **Ctrl+Shift+D** in the running application to toggle the debug overlay.
Outlines are drawn on-screen and coordinates are logged to the `ui.debug_overlay`
logger.

### Programmatic coordinate dump

```python
import logging
logging.basicConfig(level=logging.INFO, handlers=[
    logging.FileHandler('/tmp/align.log', mode='w'),
    logging.StreamHandler(),
])

from ui.debug_overlay import DebugOverlay

overlay = DebugOverlay(my_widget)
overlay.show()

def dump():
    overlay._log_coords()   # writes to ui.debug_overlay logger
    overlay.deleteLater()
    app.quit()

QTimer.singleShot(400, dump)
```

### Reading the log

```
ui.debug_overlay   SectionHeader    x=    0  y=    0  w= 1090  h=   29
ui.debug_overlay   BaseCardRibbon   x=    0  y=   29  w= 1090  h=  260
```

- All coordinates are **in the parent widget's coordinate space** (not screen).
- `x=0, y=0` for the first section header means flush alignment — no leading gap.
- Gap between `SectionHeader` bottom and `BaseCardRibbon` top should be 0 for
  both paged and scrolled views.

### Reference: expected coordinates at 1100×700

| Widget | x | y | Notes |
|---|---|---|---|
| First SectionHeader | 0 | 0 | Flush top |
| BaseCardRibbon (same section) | 0 | 29 | Immediately below header |
| Second SectionHeader | 0 | 296 | After ribbon height (260) + 2px section spacing |
| QScrollBar (vertical) | 1090 | 0 | Right edge |

---

## 8. Unit Tests (pytest)

Run the current test suite:

```bash
cd /home/tony/cc/comiccatcher
8. [Unit Tests (pytest)](#8-unit-tests-pytest)
9. [Common Issues](#9-common-issues)
10. [Full Application E2E Testing (The Driver Pattern)](#10-full-application-e2e-testing-the-driver-pattern)
11. [Keyboard Scrolling Validation](#11-keyboard-scrolling-validation)

---

## 8. Unit Tests (pytest)
...
| `tests/scrolling/repro_fast_scroll_drift.py` | Grid scroll positioning stability |

---

## 9. Common Issues
...
| `UIConstants` values are 0 or default | `init_scale()` not called | Call `UIConstants.init_scale()` before creating any widget |

---

## 10. Full Application E2E Testing (The Driver Pattern)

This is the **gold standard** for replicating user-reported bugs and validating complex features (like scrolling, navigation, or network-dependent UI) in a "true" application environment.

### Why it is powerful
- **Internal State Access:** Drivers can inspect live runtime properties (like `visualRect`, `stride`, or layout coordinates) that aren't visible in logs.
- **Environment Preservation:** It uses the user's real `feeds.json` and credentials, removing the need to mock complex OPDS structures.
- **Headless & Fast:** Using `QT_QPA_PLATFORM=offscreen` allows it to run in CI or agent environments without a real display or Xvfb.

### How it works
The `main.py` entry point supports an `--e2e-driver <path.py>` argument. When provided, the app starts normally and then dynamically loads the script, executing an `async def drive(window)` function.

### Example Driver Script (`repro_bug.py`)

```python
import asyncio
import os
from PyQt6.QtCore import Qt, QEvent, QRect
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication

async def drive(window):
    print("🚀 Bug Replication Driver Started!")
    
    # 1. Select a specific feed by name
    feed = next((f for f in window.config_manager.feeds if "codex" in f.name.lower()), None)
    if feed:
        window.on_feed_selected(feed)
    
    # 2. Wait for async load to finish
    browser = window.feed_browser
    while browser.stack.currentWidget() == browser.loading_view:
        await asyncio.sleep(0.5)

    # 3. Inspect internal layout logic
    view = browser.stack.currentWidget()
    # Check what the navigator thinks is visible
    nav = browser._keyboard_nav
    candidates = nav._visible_candidates_for_view(view.get_keyboard_nav_views()[0])
    print(f"Navigator sees {len(candidates)} items.")

    # 4. Debug coordinate clipping (Standard Navigation Fix Pattern)
    idx = view.model().index(4, 0)
    rect = view.visualRect(idx)
    item_tl = view.viewport().mapTo(window, rect.topLeft())
    print(f"Item 5 Screen Pos: {item_tl} | Window Size: {window.size()}")

    # 5. Exit cleanly
    QApplication.instance().quit()
```

### Running the E2E Test (Headless)

```bash
export QT_QPA_PLATFORM=offscreen
/home/tony/cc/test/venv/bin/python \
    /home/tony/cc/comiccatcher/src/comiccatcher/main.py \
    --e2e-driver repro_bug.py \
    --debug nav
```

---

## 11. Keyboard Scrolling & Navigation Validation

Keyboard scrolling logic is centralized in `comiccatcher.ui.view_helpers.ScrollHelper`. It uses physical UI card heights to ensure "clean" increments (rows aren't cut off).

### Verification Logic
To verify scrolling via an E2E driver, simulate `QKeyEvent` and filter them through the view's `eventFilter`.

```python
def send_key(view, key):
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import QEvent, Qt
    event = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
    # The filter is usually installed on the viewport of the scroll area
    view.eventFilter(view.list_widget.viewport(), event)

# Test sequence
start = sb.value()
send_key(lib_view, Qt.Key.Key_Down)
# Expected: sb.value() == start + (card_height + spacing)
```

### Key Bindings
| Key | Action | Implementation |
|---|---|---|
| `Down` / `Up` | Scroll one row | `ScrollHelper.scroll_by_step(1)` |
| `PageDown` / `PageUp` | Scroll one viewport | `sb.pageStep()` |
| `Home` / `End` | Top / Bottom | `sb.setSliderPosition()` |

