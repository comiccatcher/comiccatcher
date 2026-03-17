# ComicCatcher Design Document

**Status:** Active Development / Beta
**Framework:** Python 3.10+ with PyQt6 and qasync (Migrated from Flet)
**Objective:** A high-performance, native cross-platform OPDS 2.0 comic reader optimized for self-hosted servers (Codex, Komga, Stump).

---

## 1. Core Architecture

The application is built as a native desktop application using PyQt6, leveraging `qasync` to integrate the Qt event loop with Python's `asyncio`.

### Project Structure
- `main.py`: Entry point, application loop initialization, and CLI parsing.
- `config.py`: Persistent storage manager (Profiles and App Settings).
- `api/`: 
    - `opds_v2.py`: Pydantic-based OPDS 2.0 parser with JSON caching.
    - `image_manager.py`: Disk-backed image cache serving local assets.
    - `download_manager.py`: Background worker for streaming/downloading `.cbz` files.
    - `progression.py`: Syncs reading status via OPDS progression APIs.
- `ui/`:
    - `app_layout.py`: `QMainWindow` controller. Manages navigation history (breadcrumbs) and view transitions.
    - `views/browser.py`: Handles browsing/paging paradigms (Traditional, Viewport).
    - `views/detail.py`: Metadata view with carousels and hotlink navigation.
    - `views/reader.py`: `QGraphicsView` based streaming reader with pre-fetching.
    - `views/library.py`: Local library browser with `comicbox` enrichment.
    - `views/downloads.py`: UI for monitoring background download tasks.
    - `views/local_reader.py`: Native reader for local `.cbz` files.

---

## 2. Browser Implementation (The Paging Engine)

### A. Traditional Paging
- **Behavior:** Standard random access via server-provided links (`first`, `last`, `prev`, `next`).
- **Implementation:** Re-renders the entire grid/list on page change.

### B. Viewport Paging (Fit to Window)
- **Behavior:** "Window-fitted" browsing. Eliminates internal scrolling by calculating capacity based on window height.
- **Logic:** Buffers items from the server and slices the buffer into virtual "screens".

---

## 3. Features Implemented

- [x] **Native Multi-Server UI:** native PyQt forms for server profile management.
- [x] **Breadcrumb Navigation:** History trail with server branding/icons.
- [x] **OPDS Auth Protocol:** Automatic server logo discovery via Auth Documents.
- [x] **High-Performance Reader:** `QGraphicsView` implementation for smooth scaling and instant page turns.
- [x] **Facet Filtering:** Full support for OPDS 2.0 facet sorting and filtering.
- [x] **Local Library:** Native browser with thumbnails and `comicbox` metadata.

---

## 4. Known Issues & TODOs

### Viewport Paging Improvements (TODO)
- **Sync/Count Accuracy:** Investigate remaining "off-by-one" issues in the global screen counter, especially at feed boundaries.
- **Aggressive Pre-fetching:** Implement pre-fetching for the next (or previous) server-side page as soon as the *first* constituent virtual page of the current buffer is loaded, rather than waiting for the buffer to be nearly exhausted.
- **Math Stabilization:** Further refine capacity math to handle varied DPI and system-specific layout margins.

---

## 5. Next Steps for Development

1.  **Port Infinite Scroll:** Re-implement the infinite scroll method from the Flet implementation into the PyQt architecture.
2.  **Refactor Reader Overlays:** Implement hideable UI overlays for the reader (page counts, exit buttons) using floating widgets or a HUD layer.
3.  **Keyboard Customization:** Allow users to remap navigation keys via the Settings tab.
