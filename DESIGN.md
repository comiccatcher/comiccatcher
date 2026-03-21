# ComicCatcher — Design Document

**Status:** Active Development / Beta
**Framework:** Python 3.10+ · PyQt6 · qasync
**Objective:** A high-performance native desktop OPDS 2.0 comic reader optimised for self-hosted servers (Codex, Komga, Stump) with an integrated local library browser.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Project Structure](#2-project-structure)
3. [Entry Point & Startup](#3-entry-point--startup)
4. [Configuration](#4-configuration)
5. [Data Models](#5-data-models)
6. [API Layer](#6-api-layer)
7. [Local Library System](#7-local-library-system)
8. [UI Architecture](#8-ui-architecture)
9. [Views Reference](#9-views-reference)
10. [Base Components](#10-base-components)
11. [Theme System](#11-theme-system)
12. [Multi-Select & Selection Mode](#12-multi-select--selection-mode)
13. [Context Menus](#13-context-menus)
14. [Threading & Concurrency](#14-threading--concurrency)
15. [Caching Strategy](#15-caching-strategy)
16. [Data Flows](#16-data-flows)
17. [Navigation & History](#17-navigation--history)
18. [Testing](#18-testing)
19. [Known Issues & Future Enhancements](#19-known-issues--future-enhancements)

---

## 1. Architecture Overview

ComicCatcher is a native desktop application built with **PyQt6**, using **qasync** to integrate Qt's event loop with Python's `asyncio`. All network I/O is non-blocking via `httpx`; blocking work (comicbox metadata extraction, ZIP file reading, disk I/O) is offloaded to threads via `asyncio.to_thread`.

```
┌──────────────────────────────────────────────────────────────────┐
│  Qt Event Loop (qasync)                                          │
│                                                                  │
│  ┌─────────────┐   ┌─────────────────────────────────────────┐  │
│  │  Sidebar    │   │  Stacked Content Views (10 indices)     │  │
│  │  - Feeds    │   │  FeedList / Browser / Detail / Reader   │  │
│  │  - Library  │   │  Library / LocalDetail / LocalReader    │  │
│  │  - Settings │   │  Settings / SearchRoot / SearchBrowser  │  │
│  └─────────────┘   └─────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  API Layer (async)                                       │    │
│  │  APIClient → OPDS2Client → ImageManager → DownloadMgr   │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  Local Library (thread pool)                             │    │
│  │  LibraryScanner → LocalLibraryDB (SQLite) → comicbox     │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. Project Structure

```
main.py                      Entry point, QApplication + qasync loop, GNOME desktop entry
config.py                    Persistent config (feeds, settings, paths, device_id)
logger.py                    Dual-output logging (console + rotating file)

api/
  client.py                  httpx.AsyncClient with Bearer / Basic auth
  opds_v2.py                 OPDS 2.0 feed parser + in-memory JSON cache
  image_manager.py           3-tier image cache: memory → disk (SHA256) → network
  download_manager.py        Background CBZ streamer with progress & cancellation
  library_scanner.py         Async local directory scanner with comicbox integration
  local_db.py                SQLite library database (metadata, progress, grouping)
  progression.py             Readium Locator read-position sync with OPDS servers

models/
  feed.py                    FeedProfile (id, name, url, credentials, search history)
  opds.py                    OPDSFeed, Publication, Group, Link, Metadata (Pydantic v2)

ui/
  app_layout.py              MainWindow: sidebar, stacked views, tabbed history, breadcrumbs
  theme_manager.py           Theme tokens, SVG icon colorisation, global stylesheet generation
  base_reader.py             Shared reader widget (fit modes, overlays, spread layout)
  flow_layout.py             Wrapping QLayout for breadcrumb chips
  image_data.py              Image encoding utilities and MIME helpers
  local_archive.py           CBZ (ZIP) introspection and page extraction
  local_comicbox.py          comicbox wrapper: metadata extraction and flattening
  reader_logic.py            I/O-free reader state machine (fully unit tested)

  views/
    feed_list.py             Feed selection root view
    feed_management.py       Add / edit / delete feeds with connection testing
    browser.py               Feed browser (ReFit / Continuous / Traditional modes)
    detail.py                Publication detail view (metadata, cover, Read/Download)
    reader.py                OPDS streaming reader (extends BaseReaderView)
    library.py               Local library browser with thumbnails and grouping
    library_detail.py        Local comic detail / metadata / open to read
    local_reader.py          Offline CBZ reader (extends BaseReaderView)
    downloads.py             Download progress popover
    search_root.py           Search history + pinned search interface
    settings.py              App settings (theme, scroll mode, library dir, feeds)

resources/
  app.png                    Application icon
  icons/                     SVG icon set (back, book, download, feeds, folder,
                             library, refresh, settings)

tests/
  test_reader_logic_unit.py         ReaderSession state machine + fuzz (5 000 ops)
  test_viewport_paging_logic.py     ReFit virtual-page maths
  test_download_filename.py         Content-Disposition parsing + double-encoding
  test_reader_integration_manifest.py  Full manifest parsing
  test_local_archive_cbz.py         CBZ extraction
  test_local_comicbox_flatten.py    comicbox metadata flattening
  test_config_library_dir.py        Cross-platform path resolution

ui_flet_archive/             Archived legacy Flet implementation (reference only)
scripts/                     Developer diagnostics and E2E helpers
DESIGN.md                    This document
requirements.txt             Production dependencies
requirements-dev.txt         Development dependencies
pytest.ini                   pytest config (asyncio_mode = auto)
```

---

## 3. Entry Point & Startup

**`main.py`** contains two top-level functions:

### `main()`
1. Parses CLI arguments (`--debug`, `--auto-open-local`, `--timeout`).
2. Sets `DEBUG` / `DEBUG_LEVEL` env vars and calls `logger.setup_logging()`.
3. Creates `QApplication`, sets display name and window icon.
4. Calls `_ensure_desktop_entry()` (Linux only) to write/update `~/.local/share/applications/comiccatcher.desktop` so GNOME can match the running window (`StartupWMClass=comiccatcher`) to the correct icon.
5. Creates a `QEventLoop` via qasync and installs it as the running asyncio loop.
6. Installs a SIGINT handler and a 500 ms `QTimer` to allow Python to process signals while Qt is running.
7. Calls `loop.run_until_complete(async_main(args))`.

### `async_main(args)`
1. Creates `ConfigManager` and `MainWindow`.
2. Shows the window.
3. Spawns `_warmup_comicbox_sync()` in a background thread to pre-compile comicbox's marshmallow/glom schemas (cold-start cost: ~2.9 s; subsequent calls: ~0.1 s).
4. Waits on an `asyncio.Event` connected to `QApplication.aboutToQuit`.
5. Supports `--timeout N` for CI runs (automatically quits after N seconds).

### `_ensure_desktop_entry()` (Linux)
Writes a `.desktop` file with:
- `Icon=<absolute path to resources/app.png>` — avoids needing icon theme cache
- `StartupWMClass=comiccatcher` — matches the window Qt sets via `setDesktopFileName`
- Only re-writes if the `Exec=` line has changed
- Runs `update-desktop-database` silently afterwards

---

## 4. Configuration

**`ConfigManager`** stores all persistent state in platform-appropriate locations:

| Platform | Path |
|----------|------|
| Linux    | `$XDG_CONFIG_HOME/comiccatcher` (default: `~/.config/comiccatcher`) |
| macOS    | `~/Library/Application Support/comiccatcher` |
| Windows  | `%APPDATA%\comiccatcher` |

### Files

| File | Contents |
|------|----------|
| `feeds.json` | Array of serialised `FeedProfile` objects |
| `settings.json` | App preferences dict |
| `cache/` | Image disk cache (`<sha256[:2]>/<sha256>`) |
| `downloads/` | Default download destination |
| `library.db` | SQLite local library database |

### Settings Keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `scroll_method` | str | `"continuous"` | Feed browser paging: `refit` / `continuous` / `paging` |
| `library_dir` | str | `~/ComicCatcher` | Local library root path |
| `show_labels` | bool | `true` | Show title labels under library thumbnails |
| `library_view_mode` | str | `"series"` | Library grouping: `folders` / `series` / `alpha` |
| `last_view_type` | str | `"feed"` | Restore sidebar state on launch |
| `last_feed_id` | str | `""` | Restore last active feed on launch |
| `last_folder_path` | str | `""` | Restore last library folder on launch |
| `theme` | str | `"dark"` | UI theme: `light` / `dark` / `oled` / `blue` |
| `device_id` | str | (generated) | UUID for Readium progression sync |

---

## 5. Data Models

All models use **Pydantic v2** with `model_config = ConfigDict(extra='allow')` so unrecognised OPDS fields are preserved.

### `models/feed.py`

```
FeedProfile
  id             str            UUID (generated on creation)
  name           str
  url            str
  username       str            (empty if using bearer)
  password       str
  bearer_token   str
  icon_url       str
  search_history List[str]      last 50 queries, most recent first
  pinned_searches List[str]
  get_base_url() → str          strips trailing slash
```

### `models/opds.py`

```
Link
  href, type, rel (str | List[str]), title, templated, properties

Contributor
  name, sortAs, role

Metadata
  title, subtitle, identifier, description, publisher, published
  author / translator / editor / artist / illustrator / letterer
  penciler / colorist / inker / contributor  (str | Contributor | List)
  subject, language, modified, conformsTo, belongsTo

Publication
  metadata         Metadata
  links            List[Link]
  images           List[Link]   (covers)
  readingOrder     List[Link]   (pages, present in manifests)
  resources        List[Link]
  belongsTo        dict
  identifier       property     checks top-level id, then metadata.identifier

Group
  metadata, links, publications, navigation

OPDSFeed
  metadata, links, publications, navigation, groups, facets
```

---

## 6. API Layer

### `APIClient` (`api/client.py`)

Thin async HTTP wrapper:
- Built on `httpx.AsyncClient` with 30-second timeout and redirect following.
- Auth configured from `FeedProfile`: Bearer token via `Authorization: Bearer …` header, or Basic auth via `httpx.BasicAuth`.
- Exposes `async get(url, **kwargs)`, `async post(...)`, `async put(...)`.
- Context manager aware (`async with APIClient(profile) as client`).

### `OPDS2Client` (`api/opds_v2.py`)

High-level OPDS 2.0 parser:
- **`get_feed(url, force_refresh=False) → OPDSFeed`**: Fetches JSON, caches in-memory by URL, parses via `OPDSFeed.model_validate()`.
- **`get_publication(url, force_refresh=False) → Publication`**: Same for individual publication manifests.
- **`clear_cache()`**: Flushes the in-memory URL→dict cache.
- `force_refresh=True` bypasses cache for manual refresh actions.

### `ImageManager` (`api/image_manager.py`)

Three-tier image cache:

```
Request (URL)
     │
     ▼
[1] Memory cache (URL → base64 str)
     │ miss
     ▼
[2] Disk cache  (CACHE_DIR / hash[:2] / hash)
     │ miss
     ▼
[3] Network fetch (APIClient.get)
     └─ write to disk → write to memory → return base64
```

- Disk paths are `SHA256(url)` split into 2-char prefix subdirectory to avoid OS inode limits.
- Thumbnails for local CBZ covers are saved at 240×360px (JPEG, quality 85) to avoid loading 1–13 MB originals at startup.
- `_get_cache_path(url) → Path`: Returns the disk path for any URL, including the local `local-cbz://…/_cover_thumb` convention used by the library.

### `DownloadManager` (`api/download_manager.py`)

Streams `.cbz` files from OPDS servers:
- **`start_download(book_id, title, url)`**: Creates a `DownloadTask`, streams via `httpx` with `Content-Length` progress tracking.
- **`cancel_download(book_id)`**: Cancels the asyncio task and removes the partial file.
- Filename resolution chain:
  1. `Content-Disposition: attachment; filename*=UTF-8''…` (RFC 5987)
  2. `Content-Disposition: filename="…"` (with `_iterative_unquote_plus` for double-encoding)
  3. Last URL path segment
  4. Sanitised title + `.cbz`
- Filename constraints: max 180 chars, `.cbz` enforced, collision detection with `(N)` suffixes.
- Callback system: `set_callback(fn)` — called on any task state change for badge/popover updates.
- Completed downloads trigger `LocalLibraryView.set_dirty()` via `MainWindow._on_downloads_updated`.
- **Sequential Queue:** Bulk downloads are queued and processed one at a time to prevent server bans and local network congestion.

### `ProgressionSync` (`api/progression.py`)

Syncs reading position with Readium-compatible servers:
- **`get_progression(endpoint_url) → dict | None`**: Fetches current locator.
- **`update_progression(endpoint_url, locator_data)`**: PUT with Readium Locator JSON payload.
- Locator structure:
  ```json
  {
    "device": {"id": "urn:uuid:…", "name": "ComicCatcher"},
    "locations": {"progression": 0.42, "totalProgression": 0.42, "position": 5},
    "title": "…", "href": "…", "type": "…",
    "modified": "2024-01-01T12:00:00Z"
  }
  ```

---

## 7. Local Library System

### `LibraryScanner` (`api/library_scanner.py`)

Async directory scanner with comicbox integration:

- **Supported formats:** `.cbz`, `.cbr`, `.cb7`, `.pdf`
- **Scan algorithm:**
  1. Walk the library directory recursively.
  2. For each file, compare `mtime` against the DB record.
  3. If new or changed: call `read_comicbox_dict_and_cover(path)` in a thread (single combined call to avoid opening the archive twice).
  4. `flatten_comicbox()` converts the nested comicbox output to a flat dict.
  5. Upsert into `LocalLibraryDB`.
  6. If `on_cover` callback is set: save a resized thumbnail to the image cache.
  7. Process files in batches of 5 to avoid thread pool starvation.
  8. After scanning, delete DB rows for files no longer on disk.
- **Cancellation:** `_cancel_flag` checked between batches.
- **Returns:** `bool` — `True` if any changes were detected (used to skip UI refresh if nothing changed).
- **Callbacks:**
  - `on_progress(current: int, total: int, message: str)` — progress reporting
  - `on_finished(has_changes: bool)` — completion signal
  - `on_cover(path: Path, cover_bytes: bytes)` — sync cover save (runs in scanner thread)

### `LocalLibraryDB` (`api/local_db.py`)

SQLite database for library metadata and reading progress:

**Schema (`comics` table):**

| Column | Type | Notes |
|--------|------|-------|
| `file_path` | TEXT UNIQUE | Absolute path, primary key |
| `file_mtime` | REAL | For change detection |
| `title` | TEXT | |
| `series` | TEXT | Indexed |
| `issue` | TEXT | Sorted numerically via `CAST(issue AS REAL)` |
| `volume` | TEXT | |
| `year` | TEXT | |
| `publisher` | TEXT | Indexed |
| `summary` | TEXT | |
| `page_count` | INTEGER | |
| `writer`, `penciller`, `inker`, `colorist`, `letterer`, `editor`, `cover_artist` | TEXT | |
| `current_page` | INTEGER | Reading progress |
| `last_read` | TEXT | ISO 8601 timestamp |
| `_status` | TEXT | (`unread` / `started` / `completed`) |
| `source_url` | TEXT | Original OPDS acquisition URL (for sync) |

**Key methods:**
- `upsert_comic(path, mtime, meta_dict)` — INSERT … ON CONFLICT DO UPDATE
- `get_comics_in_dir(dir_path)` — single `LIKE` query (`WHERE file_path LIKE '/dir/%'`) for directory-scoped loads; scales to 20 000+ books without batching issues
- `get_comics_grouped_by_series()` — grouped + issue-sorted for the library series view
- `get_comics_grouped_by_field(field)` — generic grouping (publisher, year, etc.)
- `remove_missing_comics(known_paths)` — chunked DELETE (500 at a time to respect SQLite variable limits)
- `mark_as_read` / `mark_as_unread` — Bulk progress management
- Thread-safety via `RLock` with `check_same_thread=False` connection

### `local_comicbox.py` (`ui/local_comicbox.py`)

Wrapper around the `comicbox` library:

- **`read_comicbox_dict_and_cover(path)`** — opens the archive once, calls `cb.to_dict()` and `cb.get_cover_page()`, returns `(metadata_dict, cover_bytes)`. Single open eliminates the double-parse overhead of earlier separate calls.
- **`flatten_comicbox(d)`** — converts comicbox's nested output to a flat metadata dict with standard field names (`title`, `series`, `issue`, `writer`, etc.). Handles credits dict extraction for each role.
- **`subtitle_from_flat(flat)`** — formats `"Series #Issue (Year)"` for display.
- Graceful degradation: returns `{"_comicbox_status": "error"|"empty"|"missing"}` on failure.

**comicbox cold-start:** The first `Comicbox()` call compiles marshmallow/glom schemas (~2.9 s). `_warmup_comicbox_sync()` in `main.py` pre-triggers this at startup in a background thread so the first library scan is fast.

---

## 8. UI Architecture

### `MainWindow` (`ui/app_layout.py`)

The root window (`QMainWindow`) containing:

```
QMainWindow
└── central_widget (QWidget, QHBoxLayout)
    ├── sidebar (QFrame#sidebar, 85px)
    │   └── nav_list (QListWidget#nav_list, IconMode, TopToBottom)
    │       ├── [0] Feeds
    │       ├── [1] Library
    │       └── [2] Settings
    └── main_area (QWidget, QVBoxLayout)
        ├── debug_bar (QFrame#debug_bar, 25px, visible if DEBUG=1)
        │   └── history counter, URL display, Copy/Logs buttons
        ├── top_header (QFrame#top_header)
        │   ├── Row 1: Unified Back button, feed icon, feed name, Browse/Search tabs, Downloads button
        │   └── Row 2: Breadcrumb FlowLayout + Refresh button
        └── content_stack (QStackedWidget)
            ├── [0] FeedListView
            ├── [1] LocalLibraryView
            ├── [2] SettingsView
            ├── [3] BrowserView (feed)
            ├── [4] LocalComicDetailView
            ├── [5] LocalReaderView
            ├── [6] DetailView
            ├── [7] ReaderView
            ├── [8] SearchRootView
            └── [9] BrowserView (search)
```

**Unified Navigation:**
- A single global **Back** button in the top header handles all navigation history and internal view transitions.
- **Breadcrumbs** provide smart context navigation, using a `>` separator to distinguish the feed identity from the navigation path.
- Internal "Back" buttons in detail and library views are hidden to ensure a unified navigation flow.

**State management:**
- `active_tab`: `"feed"` | `"search"` — which tab is active
- `feed_history` / `search_history`: independent `List[dict]` stacks
- `feed_index` / `search_index`: current position in respective stack
- Each history entry: `{type, title, url, offset, pub, feed_id}`

**Download badge:**
- `download_badge` is a `QLabel` overlaid on `btn_downloads` at offset (16, 0)
- Shows count of `Downloading` + `Pending` tasks; hidden at zero
- On completion: calls `local_library_view.set_dirty()` to queue a rescan

**Download popover (`DownloadPopover`):**
- `QFrame` with `Qt.WindowType.Popup | FramelessWindowHint`
- Positioned below the download button via `show_at(pos)`
- Contains `DownloadsView`

### `_apply_theme()`

Called at startup and on theme change:
1. Calls `ThemeManager.apply_theme(app, theme_name)` — rebuilds the global stylesheet.
2. Forces stylesheet reparse on library and feed list views.
3. Refreshes all nav list item icons and toolbar button icons with recoloured SVGs.

---

## 9. Views Reference

### FeedListView (`views/feed_list.py`)

Root screen for the Feeds sidebar section. Displays the configured feeds as a list with icons and URLs. Double-click selects a feed. The `+ Add Feed` button (objectName `primary_button`) opens `FeedManagementView` in a dialog. Icon loading is async; icons are cached on the `FeedProfile._cached_icon` attribute and emit `icon_loaded(feed_id, pixmap)` for the main window header.

### FeedManagementView / FeedEditDialog (`views/feed_management.py`)

Embedded CRUD panel for feeds (used inside SettingsView and as a standalone dialog). `FeedEditDialog` provides fields for name, URL, auth (username/password or bearer token), and icon URL. The "Test Connection" button creates a temporary `APIClient`, fetches the base URL, and shows a `ConnectionTestResultDialog` with the result.

### BrowserView (`views/browser.py`)

The primary content browsing widget. Supports three rendering modes selectable via a `QComboBox`:

#### A. ReFit Mode (`refit`)
- Computes how many items fit the visible viewport (based on `PublicationCard` size 160×260, nav button height 40px, 10px spacing).
- Fills the window with exactly one "screen" of items at a time.
- Arrow keys, Page Up/Down, Home/End, and mouse wheel navigate screens.
- Bidirectional pre-fetching: fetches the next server page when near the end of the buffer, and the previous page when near the start.
- Virtual page counter: tracks absolute global offset for "Screen X of Y" display.

#### B. Continuous Mode (`continuous`)
- Allocates a virtual canvas sized to `total_items × item_height`.
- Items are rendered only in the visible viewport (plus a 3-row lookahead buffer).
- `_rendered_widgets: Dict[global_index → QWidget]` tracks live widgets; widgets outside the viewport are deleted.
- Missing indices trigger `_fetch_missing_indices()` which predicts the server page URL via `_predict_page_url()` (three patterns: `page=X` query param, path segment replacement, fallback append).
- Scroll debounce (300 ms) then `_on_scroll_settled` for background fetch.

#### C. Traditional Mode (`paging`)
- Standard OPDS `first` / `prev` / `next` / `last` links.
- `PagingBar` widget shows `<<`, `<`, page status, `>`, `>>` buttons.

**Dashboard rendering:**
If the feed contains `groups` with `publications`, each group renders as a horizontally scrollable `QScrollArea` strip of `PublicationCard` widgets. **"See All"** buttons provide quick navigation to full group feeds.

**Facet / filter menu:**
Built from `feed.facets` or group navigation links with `rel` containing `facet`. Populates a `QMenu` on the Filters button.

**`PublicationCard`:**
- Fixed 160×260 px `QFrame` (objectName `publication_card`).
- Async thumbnail load via `ImageManager.get_image_b64`.
- Click emits `(pub, self_url)` signal.
- Context menu support for quick downloading.
- Multi-select support via click interception in selection mode.

### DetailView (`views/detail.py`)

Displays full publication metadata: cover, title, author, publisher, description, series/group links, contributors, and read status. Actions: **Read** (opens ReaderView), **Download** (triggers DownloadManager). Lazy manifest fetch if `publication.readingOrder` is absent. Syncs progression via `ProgressionSync` on load.

### ReaderView (`views/reader.py`)

Extends `BaseReaderView` for online publications:
- Page images fetched via `ImageManager.get_image_b64(url)`.
- Pre-fetches PREFETCH_AHEAD=3 pages ahead and PREFETCH_BEHIND=1 behind.
- `_prefetch_set` tracks in-flight fetches to avoid duplicates.
- On page change: updates Readium Locator via `ProgressionSync`.

### LocalLibraryView (`views/library.py`)

Local comic library with three grouping modes:

| Mode | Description |
|------|-------------|
| `folders` | Directory tree navigation |
| `series` | Grouped by `series` field, horizontally scrollable strips |
| `alpha` | All comics alphabetically |

**`SeriesSection` widget** (used in `series` mode):
- `QPushButton#section_toggle` — collapsible section header.
- `QListWidget` — horizontal or grid layout of comic thumbnails.
- `ComicDelegate` — custom item delegate drawing cover image + progress bar overlay + optional title label.
- **Dimming:** Read comics are dimmed to 0.5 opacity for a clean "archived" appearance.

**Thumbnail loading:**
1. Check image cache for `local-cbz://<abs_path>/_cover_thumb`.
2. If missing: load `QImage` in a thread, create `QPixmap` on main thread.
3. Thumbnails are saved to disk at 240×360px, JPEG quality 85 (~34 KB avg vs 1.7 MB raw — 50× smaller, 35× faster to load).

**Scanner integration:**
- `_save_cover_to_cache(path, cover_bytes)` is passed as `on_cover` callback to `LibraryScanner` — saves thumbnails synchronously in the scanner thread while scanning, so covers are ready before the UI renders.
- `_on_scan_finished_ui(has_changes)` only triggers a UI reload if `has_changes=True`.
- `set_dirty()` queues a rescan (called after download completes).

### LocalComicDetailView (`views/library_detail.py`)

Detail view for local comics. Shows cover, metadata from DB, progress (Page X of Y). **Read** button opens `LocalReaderView`. Metadata is enriched from `LocalLibraryDB`; cover is extracted from the first CBZ image.

### LocalReaderView (`views/local_reader.py`)

Extends `BaseReaderView` for offline CBZ files:
- `list_cbz_pages(path)` enumerates pages sorted by filename.
- Pages extracted via `read_cbz_entry_bytes()` in a thread, then stored in the image cache keyed by `local-cbz://<abs_path>/<entry_name>`.
- `Semaphore(2)` limits concurrent extraction threads.
- Reading progress saved to `LocalLibraryDB` on page change.
- Progress restored from DB on open.

### DownloadsView (`views/downloads.py`)

Compact download monitor embedded in `DownloadPopover`:
- One `DownloadTaskWidget` per active/recent task (newest at top).
- Each widget: title label, status text, `QProgressBar`, action button (Cancel / Remove).
- Colour coding: green for completed, red for failed/cancelled.
- "Clear Completed" button removes all finished tasks.
- Updates via `DownloadManager` callback.

### SearchRootView (`views/search_root.py`)

Search interface showing two columns: **History** and **Favorites** (pinned searches). Each entry is a `SearchItemWidget` with a clickable label, a pin/star button, and a remove button. Submitting a query calls `_execute_search()` in the main window, which resolves the server's OpenSearch description and navigates to the results URL. **Loading indicators** provide visual feedback during search execution.

### SettingsView (`views/settings.py`)

Settings form with:
- **Theme** group: radio buttons for Light / Dark / OLED / Deep Blue — emits `theme_changed` signal on change.
- **Feeds** group: embeds `FeedManagementView` inline.
- **Browsing Method** group: radio buttons for Continuous / Traditional / ReFit modes.
- **Library** group: directory picker and show-labels toggle.

---

## 10. Base Components

### `BaseReaderView` (`ui/base_reader.py`)

Shared reader widget inherited by both `ReaderView` and `LocalReaderView`.

**Layout:**
```
QWidget (BaseReaderView)
└── QGraphicsView (self.graphics_view)
    └── QGraphicsScene
        └── QGraphicsPixmapItem (self.page_item)
        (overlays drawn as widgets over the view)
```

**Overlays:**
- **Header** (top): Back button, book title, page counter (`N / Total`), fullscreen toggle. Auto-hides after 3 s.
- **Footer** (bottom): Thumbnail-enabled page slider, Prev/Next buttons, Fit/Direction/Layout mode toggles, Thumbnail strip toggle. Auto-hides after 3 s.
- Mouse movement resets the hide timer and shows overlays.

**Fit modes** (`FitMode` enum):
- `FIT_PAGE` — scale to fit both dimensions
- `FIT_WIDTH` — scale to viewport width
- `FIT_HEIGHT` — scale to viewport height
- `ORIGINAL` — 1:1 pixel display

**Page layout** (`PageLayout` enum):
- `SINGLE` — one page
- `DOUBLE` — side-by-side spread
- `AUTO` — double if viewport is wider than it is tall

**Page spread compositing (`_compose_spread`):**
- Creates a black canvas wide enough for both pages.
- Left page: left-aligned (or right if RTL).
- Right page: right-aligned.
- Pages vertically centred on the canvas.

**Click zones:**
- Left third of viewport → previous page
- Right third → next page
- Centre third → toggle overlay visibility

**Keyboard shortcuts:**

| Key | Action |
|-----|--------|
| ←/→ or PgUp/PgDn | Prev/Next page |
| Home/End | First/Last page |
| Space | Next page |
| Escape | Back |
| F | Cycle fit mode |
| R | Toggle reading direction (LTR/RTL) |
| L | Cycle page layout |
| F11 | Toggle fullscreen |

**Thumbnail slider (`ThumbnailSlider`):**
- Extends `QSlider` with a floating `QLabel` popup showing a small cover preview.
- Event filter detects mouse-over on the slider handle.
- Thumbnails loaded async via `_do_load_thumbnail()` (virtual, implemented by subclass).

**Virtual interface (subclasses must implement):**
```python
async def _load_page_pixmap(idx: int) -> Optional[QPixmap]: ...
async def _do_prefetch(idx: int) -> None: ...          # optional
def _on_page_changed(idx: int) -> None: ...            # optional
```

### `FlowLayout` (`ui/flow_layout.py`)

Custom `QLayout` that wraps child widgets to the next line when the available width is exceeded. Used in the breadcrumb row. Implements `heightForWidth()` for proper resize behaviour.

### `ReaderSession` (`ui/reader_logic.py`)

Pure Python dataclass representing reader state:
- `base_url`: Feed base URL for resolving relative hrefs.
- `reading_order`: `List[Dict]` of page entries.
- `index`: current page index.
- Methods: `next()`, `prev()`, `jump(n)`, `set_progression(0..1)`, `current_url()`, `can_next()`, `can_prev()`.
- `index_from_progression(progress, total)`: converts a 0..1 float to an integer index.
- Completely I/O-free — all async work happens in the view layer.

### `local_archive.py` (`ui/local_archive.py`)

ZIP (CBZ) utilities:
- `list_cbz_pages(path) → List[LocalPage]`: returns image entries sorted by `name.lower()`.
- `read_cbz_entry_bytes(path, name) → bytes`: reads a single ZIP entry.
- `read_first_image(path) → (name, bytes)`: returns the first image (for cover extraction).
- Recognised image extensions: `.jpg`, `.jpeg`, `.png`, `.webp`.

### `image_data.py` (`ui/image_data.py`)

Image encoding helpers:
- `data_url_from_b64(b64, mime)` / `data_url_from_bytes(data, mime)`: build `data:` URLs.
- `guess_mime_from_url(url, default)`: infers MIME type from file extension.
- `TRANSPARENT_DATA_URL`: 1×1 transparent PNG for use as a placeholder.

---

## 11. Theme System

**`ThemeManager`** (`ui/theme_manager.py`)

### "Thin-Bar" Aesthetic
ComicCatcher employs a modern "thin-bar" design language:
- **Progress Bars:** All progress indicators (Loading, Cover Reading Progress, Search, Downloads) are standardized to a **4px height** with a 2px border radius.
- **Scrollbars:** Custom transparent scrollbars with themed, rounded handles and hover states.
- **Structural Borders:** 1px borders define the sidebar, header, and debug bar, ensuring visual hierarchy across all themes.

### Colour Tokens

| Token | Light | Dark | OLED | Blue |
|-------|-------|------|------|------|
| `bg_main` | `#f5f6f8` | `#1e1e1e` | `#000000` | `#0f172a` |
| `bg_sidebar` | `#e8ecf0` | `#2d2d2d` | `#000000` | `#1e293b` |
| `bg_header` | `#ffffff` | `#252526` | `#000000` | `#1e293b` |
| `bg_item_hover` | `#dde3ea` | `#3e3e42` | `#1a1a1a` | `#334155` |
| `bg_item_selected` | `#c8ddf8` | `#264f78` | `#007fd4` | `#0ea5e9` |
| `text_main` | `#1a1d21` | `#e1e1e1` | `#ffffff` | `#f1f5f9` |
| `text_dim` | `#5a6270` | `#969696` | `#aaaaaa` | `#94a3b8` |
| `accent` | `#0066cc` | `#007fd4` | `#007fd4` | `#0ea5e9` |
| `border` | `#c8cdd4` | `#333333` | `#222222` | `#334155` |
| `card_bg` | `#ffffff` | `#252526` | `#000000` | `#1e293b` |

### SVG Icon Colorisation

`ThemeManager.get_icon(name)` rewrites the SVG at load time:
1. Reads the SVG bytes from `resources/icons/{name}.svg`.
2. Replaces `stroke="white"` and `fill="white"` with the current theme's `text_main` colour.
3. Loads via `QPixmap.loadFromData(bytes, "SVG")`.
4. Falls back to `QIcon(str(path))` if the SVG plugin is unavailable.

---

## 12. Multi-Select & Selection Mode

ComicCatcher supports **Explicit Selection Mode** for safe bulk operations.

### Key Components:
- **`selection_mode`:** A state toggle in `BrowserView` and `LibraryView` that changes click behavior from opening a book to selecting it.
- **`Tiered Identity Keys`:** Uses a fallback chain (Self URL → Identifier → Hash) to ensure stable selection tracking even in feeds without unique IDs.
- **`SelectionActionBar`:** A contextual toolbar that appears when items are selected, providing actions like "Download All" or "Delete Selected".

### Bulk Actions:
- **Sequential Download:** Browser items are queued for sequential download to respect server limits.
- **Bulk Progress:** Mark multiple local items as Read or Unread simultaneously.
- **Bulk Deletion:** Securely delete multiple local files with a unified confirmation dialog.

---

## 13. Context Menus

Right-click context menus are integrated throughout the application for efficiency:

- **Browser:** Quick "Download" without entering the detail view.
- **Library Items:** Toggle "Read / Unread" status or "Delete" individual comics.
- **Library Groups:** "Expand All", "Collapse All", or bulk "Mark Group as Read" actions on series sections.

---

## 14. Threading & Concurrency

```
Main thread (Qt + asyncio via qasync)
│
├── asyncio.to_thread(read_comicbox_dict_and_cover)   ← library scan metadata
├── asyncio.to_thread(save_thumbnail)                 ← cover resize/save
├── asyncio.to_thread(db.upsert_comic)                ← DB writes
├── asyncio.to_thread(db.get_comics_in_dir)           ← DB reads
├── asyncio.to_thread(read_cbz_entry_bytes)           ← page extraction
│   └── guarded by Semaphore(2)
├── asyncio.to_thread(_warmup_comicbox_sync)          ← startup pre-warm
│
└── httpx.AsyncClient (event loop, non-blocking)
    ├── opds_client.get_feed                          ← feed fetches
    ├── image_manager.get_image_b64                  ← image loads
    └── download_manager.start_download              ← file streaming
```

---

## 15. Caching Strategy

### Image Cache (three tiers)

| Tier | Storage | Key | Lifetime |
|------|---------|-----|----------|
| Memory | `Dict[url, base64_str]` | URL string | Process lifetime |
| Disk | `CACHE_DIR/<hash[:2]>/<hash>` | SHA256 of URL | Persistent (manual clear) |
| Network | httpx async GET | — | One request |

### Thumbnail Cache

Local library cover images are resized to 240×360px JPEG (quality 85) before disk storage. URL convention: `local-cbz://<abs_path>/_cover_thumb`. This reduces average per-cover load time from ~256 ms (13 MB raw TIFF/PNG) to ~2.5 ms (34 KB JPEG).

---

## 16. Data Flows

### Opening a Feed

```
User clicks feed in FeedListView
  → MainWindow.on_feed_selected(feed)
      → APIClient(feed), OPDS2Client, ImageManager constructed
      → feed_browser_view.set_feed_context(feed)
      → asyncio.create_task(feed_browser_view.load_feed(start_url))
          → opds_client.get_feed(url)  [cache miss → httpx GET]
          → _render_dashboard / _render_grid / _render_navigation
          → PublicationCard._load_thumb (async per-card)
      → MainWindow.update_header()  [breadcrumbs built]
```

### Reading an Online Publication

```
User clicks PublicationCard
  → on_open_detail(pub, self_url)
      → DetailView.load_publication(pub, url, ...)
          → opds_client.get_publication(url)  [if readingOrder absent]
          → progression_sync.get_progression(endpoint)
          → render metadata, cover

User clicks Read
  → on_read_book(pub, manifest_url)
      → ReaderView.load_manifest(pub, manifest_url)
          → parse reading_order from manifest
          → _load_page_pixmap(0)
              → image_manager.get_image_b64(page_url)
          → _do_prefetch (3 ahead, 1 behind)

On page change
  → _on_page_changed(idx)
      → progression_sync.update_progression(endpoint, locator)
      → _do_prefetch(new_idx)
```

---

## 17. Navigation & History

### History Stack

Two independent stacks are maintained: `feed_history` and `search_history`, each indexed by `feed_index` / `search_index`.

### Navigation operations

| Action | Effect |
|--------|--------|
| **Back Button** | Global handler that traverses history or returns to feed list. |
| **Breadcrumbs** | Deep-link jumping between history steps or feed levels. |
| **Tab Switch** | Browse ↔ Search toggle with independent history preservation. |
| **Escape Key** | Exits selection mode or returns from detail views. |

---

## 18. Testing

Test suite uses `pytest` with `pytest-asyncio` (`asyncio_mode = auto`).

| Test file | Coverage |
|-----------|----------|
| `test_reader_logic_unit.py` | `ReaderSession` state machine; 5 000-op fuzz test |
| `test_viewport_paging_logic.py` | ReFit virtual-page index maths |
| `test_download_filename.py` | Content-Disposition parsing, double/triple URL encoding |
| `test_reader_integration_manifest.py` | Full OPDS manifest parsing via Pydantic models |
| `test_local_archive_cbz.py` | CBZ page listing and extraction |
| `test_local_comicbox_flatten.py` | comicbox metadata flattening for all role types |
| `test_config_library_dir.py` | Platform-specific config path resolution |

---

## 19. Known Issues & Future Enhancements

### ReFit Mode

- **Non-aligned buffer start:** Edge case where the first loaded server page doesn't align with the ReFit virtual-page boundary. Partially mitigated by snapping the initial offset to the nearest page boundary.
- **Bidirectional prefetch race:** Minor race condition when forward and backward pre-fetch fire simultaneously; deduplicated by ID checking but can produce a brief double-render.

### UI & UX

- **Feed browser grid columns:** `_render_grid` uses a hardcoded `cols = 5`; should adapt to viewport width like continuous mode.
- **macOS / Windows testing:** Primary development target is Linux/GNOME. Stylesheet behaviour on macOS (native style engine) and Windows may need platform-specific tweaks.

### Performance

- **comicbox cold-start:** Mitigated by warmup at startup, but the first scan after a fresh install will still pause briefly on the first file.
- **Large libraries (1 000+ books):** The `get_comics_in_dir` LIKE query scales well, but initial thumbnail grid render may be slow; a lazy/virtual list widget would improve this.
