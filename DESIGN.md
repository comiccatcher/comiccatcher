# ComicCatcher Design Document

**Status:** Active Development / Beta
**Framework:** Python 3.10+ with Flet v0.82.2 (Upgraded from v0.21.2)
**Objective:** A high-performance, cross-platform OPDS 2.0 comic reader optimized for self-hosted servers (Codex, Komga, Stump).

---

## 1. Core Architecture

The application is built as a Single Page Application (SPA) within the Flet framework.

### Project Structure
- `main.py`: Entry point, global error handling, and CLI argument parsing (`--debug`).
- `config.py`: Persistent storage manager (Profiles and App Settings).
- `api/`: 
    - `opds_v2.py`: Pydantic-based OPDS 2.0 parser with JSON caching.
    - `image_manager.py`: Disk-backed Base64 image cache to minimize network overhead.
    - `download_manager.py`: Background worker for streaming/downloading `.cbz` files.
    - `progression.py`: Syncs reading status via OPDS progression APIs.
- `ui/`:
    - `app_layout.py`: The master controller. Manages navigation history (breadcrumbs) and view transitions.
    - `views/browser.py`: Handles browsing/paging paradigms (Infinite, Traditional, Viewport).
    - `views/detail.py`: "Smart Merge" metadata view (upgrades basic feed data to rich manifest data).
    - `views/reader.py`: Image-based streaming reader with pre-fetching.
    - `views/library.py`: Local library browser for downloaded or local `.cbz` files.
    - `views/downloads.py`: UI for monitoring background download tasks.
    - `views/local_reader.py`: Optimized reader for local files using `comicbox`.

---

## 2. Browser Implementation (The Paging Engine)

The browser supports three distinct methods for navigating large collections:

### A. Infinite Scroll (Sequential)
- **Behavior:** Standard "modern" web behavior. Follows `rel="next"` links.
- **Implementation:** Appends items to a `ListView`.

### B. Traditional Paging
- **Behavior:** Random access via server-provided links (`first`, `last`, `prev`, `next`).
- **Implementation:** Re-renders the entire view on page change.

### C. Viewport Paging (Re-paged)
- **Behavior:** "Window-fitted" browsing. Eliminates internal scrolling by calculating capacity based on window height.
- **Logic:** Proactively fetches the next 100 items from the server when the local buffer is nearly exhausted.

---

## 3. Features Implemented

- [x] **Multi-Server Support:** Save and edit server profiles with Auth/Tokens.
- [x] **Breadcrumb Navigation:** A history trail that allows clicking back to any previous level.
- [x] **Smart Metadata Merge:** Transitions from a "minimal" feed entry to a "rich" manifest without UI flashing.
- [x] **Streaming Reader:** Displays WebP/JPG streams with a hideable UI overlay.
- [x] **Local Library & Downloads:** Browser for local files and background download manager with dedicated UI.
- [x] **Disk Caching:** Aggressive caching of thumbnails and reader pages.
- [x] **Facet Filtering:** Supports OPDS 2.0 facets via a Popup Menu.

---

## 4. Known Issues & Technical Debt

### Flet Version Regression / Bugs (CRITICAL)
- **Symptom:** The application logs frequent `NoSuchMethodError: Class 'Control' has no instance method '[]'. Tried calling: []("src")`.
- **Root Cause:** Likely due to the migration from v0.21.2 to v0.82.2 where some property access patterns or internal Flet messaging changed. This often results in "Black Screens" or UI stalls.
- **Status:** Investigating.

### Viewport Logic Stability
- **Symptom:** Jumping to the "End" of a 3,000+ item list can stall or fail.
- **Root Cause:** The sequential nature of OPDS 2.0 makes random access difficult. Regex-based URL "guessing" for pages is still brittle.

### Dashboard vs. List Transitions
- **Issue:** Switching between "Dashboard" mode (grouped feeds) and "List" mode (flat feeds) can sometimes lead to layout conflicts or duplicated controls if the `main_content` is not cleared correctly.

---

## 5. Next Steps for Development

1.  **Resolve "src" NoSuchMethodError:** Identify and fix the invalid property access that causes client-side crashes in Flet v0.82.2.
2.  **Refactor Browser State:** Decouple the three browsing modes into cleaner, separate handler classes to avoid the current "megamorphic" `browser.py`.
3.  **Enhance Local Reader:** Add support for bookmarks and reading progression for local files (currently only synced for remote OPDS).
