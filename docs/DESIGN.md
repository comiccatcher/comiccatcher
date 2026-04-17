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
│  │  Sidebar    │   │  Stacked Content Views (9 indices)      │  │
│  │  - Feeds    │   │  FeedList / Browser / FeedDetail / ...  │  │
│  │  - Library  │   │  LocalLibrary / LocalDetail / ...       │  │
│  │  - Settings │   │  Settings / SearchRoot / ...            │  │
│  └─────────────┘   └─────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  API Layer (async)                                       │    │
│  │  APIClient → OPDS2Client → FeedReconciler → ImageMgr    │    │
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
pdffile.py                  Shared PDF helper (MuPDF backend)

api/
  client.py                  httpx.AsyncClient with Bearer / Basic auth
  opds_v2.py                 OPDS 2.0 feed parser + in-memory JSON cache
  feed_reconciler.py         Transforms raw OPDS feeds into unified FeedPage models
  image_manager.py           3-tier image cache: memory → disk (SHA256) → network
  download_manager.py        Background CBZ streamer with progress & cancellation
  library_scanner.py         Async local directory scanner with comicbox integration
  local_db.py                SQLite library database (metadata, progress, grouping)
  progression.py             Readium Locator read-position sync with OPDS servers

models/
  feed.py                    FeedProfile (id, name, url, credentials, search history)
  opds.py                    OPDSFeed, Publication, Group, Link, Metadata (Pydantic v2)
  feed_page.py               Unified FeedPage, FeedSection, and FeedItem models
  opds_auth.py               OPDS Authentication document models

ui/
  app_layout.py              MainWindow: sidebar, stacked views, tabbed history, breadcrumbs
  theme_manager.py           Theme tokens, SVG icon colorisation, global stylesheet generation
  base_reader.py             Shared reader widget (fit modes, overlays, spread layout)
  debug_overlay.py           Real-time layout and performance diagnostic overlay
  flow_layout.py             Wrapping QLayout for breadcrumb chips
  image_data.py              Image encoding utilities and MIME helpers
  image_utils.py             Async pixmap loading and scaling helpers
  local_archive.py           CBZ (ZIP) introspection and page extraction
  local_comicbox.py          comicbox wrapper: metadata extraction and flattening
  reader_logic.py            I/O-free reader state machine (fully unit tested)
  utils.py                   Formatting and date parsing utilities
  view_helpers.py            Viewport visibility and async cover fetch helpers

  components/                Reusable UI building blocks
    auth_dialog.py           OAuth2 / Basic Auth credential entry dialog
    base_card_delegate.py    Base class for card rendering (paints titles, frames)
    feed_card_delegate.py    OPDS-specific card rendering with badge support
    library_card_delegate.py Local-specific card rendering with progress bars
    base_ribbon.py           Horizontal carousel for RIBBON sections
    collapsible_section.py   Expandable section container with header
    feed_browser_model.py    Virtualized QAbstractListModel for grid data
    mini_detail_popover.py   Bubble-style metadata summary popover
    paging_control.py        Pagination controls for paged views
    popover_mixin.py         Mixin for standardized popup/popover positioning
    section_header.py        Themed header for feed sections
    loading_spinner.py       Indeterminate async progress indicator

  views/
    feed_list.py             Feed selection root view
    feed_management.py       Add / edit / delete feeds with connection testing
    feed_browser.py          FeedBrowser coordinator (switches between paged/scrolled)
    base_browser.py          Standardized header/status/selection logic for browsers
    base_detail.py           Shared metadata and action layout for detail views
    base_feed_subview.py     Shared base for PagedFeedView and ScrolledFeedView
    paged_feed_view.py       Dashboard layout: CollapsibleSections in QScrollArea
    scrolled_feed_view.py    Virtual scroll view: section-level QAbstractScrollArea
    feed_detail.py           Online publication detail view (metadata, cover, Read/Download)
    feed_reader.py           OPDS streaming reader (extends BaseReaderView)
    local_library.py         Local library browser with thumbnails and grouping
    local_detail.py          Local comic detail / metadata / open to read
    local_reader.py          Offline CBZ reader (extends BaseReaderView)
    downloads.py             Download progress popover
    search_root.py           Search history + pinned search interface
    settings.py              App settings (theme, scroll mode, library dir, feeds)

resources/
  app.png                    Application icon
  icons/                     Expanded SVG icon set (40+ actions and navigational symbols)

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

**`main.py`** contains the application entry point, setting up the `qasync` event loop and managing the application lifecycle.

---

## 4. Configuration

**`ConfigManager`** stores all persistent state in platform-appropriate locations.

---

## 5. Data Models

All models use **Pydantic v2** with `model_config = ConfigDict(extra='allow')` so unrecognised OPDS fields are preserved.

### Unified Feed Models (`models/feed_page.py`)

Raw OPDS data is reconciled into a unified hierarchy for UI rendering:

- **`FeedPage`**: The root container for a single "screen" of a feed, containing sections, facets, search templates, and breadcrumbs.
- **`FeedSection`**: A logical grouping (e.g., "Newest", "All Series") with its own items, pagination metadata, and layout type (RIBBON or GRID).
- **`FeedItem`**: A single visual card representing a publication or a navigation folder.

---

## 6. API Layer

### `APIClient` (`api/client.py`)

Thin async HTTP wrapper built on `httpx.AsyncClient`.

### `OPDS2Client` (`api/opds_v2.py`)

High-level OPDS 2.0 parser with in-memory JSON caching.

### `FeedReconciler` (`api/feed_reconciler.py`)

The transformation engine that converts raw `OPDSFeed` objects into `FeedPage` structures. It handles:
- Detecting "Main" sections for infinite scroll.
- Normalizing pagination patterns across different server types.
- **Section Identity**: Generates unique, stable `section_id` strings, appending current page numbers when necessary to prevent collisions in "Infinite Sections" mode.
- Heuristic-based extraction of series names and issue numbers.
- Pruning redundant server-side nesting.

### `ImageManager` (`api/image_manager.py`)

Three-tier image cache: memory → disk (SHA256) → network.

### `DownloadManager` (`api/download_manager.py`)

Background CBZ streamer with sequential task queueing.

---

## 7. Local Library System

### `LibraryScanner` (`api/library_scanner.py`)

Async directory scanner with comicbox integration for metadata extraction.

### `LocalLibraryDB` (`api/local_db.py`)

SQLite database for library metadata and reading progress.

---

## 8. UI Architecture

### 8.1 Class Hierarchies

The UI is structured around a centralized orchestrator (`AppLayout`) and a set of specialized sub-views.

#### Feed Browser View Hierarchy
Supports both "Paged" (Dashboard-style) and "Scrolled" (Virtualized continuous) rendering.

```text
QWidget (Qt)
└── BaseFeedSubView (Shared signals, configure_list_view, gather_context_pubs)
    ├── PagedFeedView   (Dashboard mode: CollapsibleSections in QScrollArea)
    └── ScrolledFeedView (Continuous mode: section-level virtual scroll)

QWidget (Qt)
└── FeedBrowser (Traffic Cop coordinator)
    ├── Instantiates PagedFeedView
    └── Instantiates ScrolledFeedView
```

**ScrolledFeedView virtual scroll architecture**

Rather than one giant composite `QListView`, `ScrolledFeedView` uses a
`QAbstractScrollArea` (`_impl`) whose viewport (`_vp`) holds real per-section
widget pairs positioned by a single vertical `QScrollBar`. This avoids Qt's
16 777 215 px (`QWIDGETSIZE_MAX`) content-widget limit entirely.

```
ScrolledFeedView (QWidget / BaseFeedSubView)
└── _impl (_ScrollImpl : QAbstractScrollArea)   ← provides clipping viewport
    └── _vp (viewport QWidget)
        ├── SectionHeader  ─┐ one pair per section,
        ├── BaseCardRibbon  ─┘ repositioned on every scroll event (RIBBON sections)
        ├── SectionHeader  ─┐
        └── QListView       ─┘ height = visible slice only (large GRID section)
```

Key design points:

- **Section-level virtualisation**: only widgets whose section overlaps the
  viewport are shown; others are hidden.
- **Large GRID sections** (up to 30 k items): the `QListView` widget height is
  capped to the visible slice height. Its internal `verticalScrollBar` is
  synced to `outer_scroll − section.y − header_height`, preserving full
  QListView item-level virtualisation without creating a tall widget.
- **Height estimation**: `_grid_content_height` approximates content height
  from column count and row height; `_calibrate_grid_heights` corrects this
  from the QListView's actual scroll range after first layout.
- **Wheel forwarding**: an `eventFilter` on each grid view's viewport
  redirects vertical wheel events to `_sb` (the outer scrollbar).
- **Page fetching / debouncing / cover loading**: logic is identical to the
  previous implementation, operating on the main grid section's
  `FeedBrowserModel`.

#### Main Application Structure
The top-level shell managing navigation and primary workspaces.

```text
QMainWindow (Qt)
└── ComicCatcherApp (main.py)

QWidget (Qt)
└── AppLayout (Central orchestrator: sidebar, header, stacked views)
    └── QStackedWidget (View switching)
        ├── FeedBrowser (OPDS browser)
        ├── LocalLibraryView (Local files)
        ├── SettingsView
        └── ReaderView (Online/Local viewer)
```

#### Component Hierarchy (Shared UI)
Reusable building blocks across different view modes.

```text
QStyledItemDelegate (Qt)
└── BaseCardDelegate
    ├── FeedCardDelegate     (OPDS publication card)
    └── LibraryCardDelegate  (Local file card with progress)

QAbstractListModel (Qt)
└── FeedBrowserModel (Virtualized grid data source)

QWidget (Qt)
├── CollapsibleSection (Expandable section container)
├── SectionHeader (Themed header with "See All" support)
├── MiniDetailPopover (Bubble-style metadata summary)
└── QListView (Qt)
    └── BaseCardRibbon (Horizontal carousel)
```

### 8.2 MainWindow (`ui/app_layout.py`)

The root window containing the sidebar and stacked content views. Uses the `ViewIndex` enum for reliable navigation.

```
Stack Index (ViewIndex):
- FEED_LIST: 0
- LIBRARY: 1
- SETTINGS: 2
- LOCAL_DETAIL: 3
- LOCAL_READER: 4
- DETAIL: 5
- READER_ONLINE: 6
- SEARCH_ROOT: 7
- FEED_BROWSER: 8
```

**Standard Navigation:**
- Single global **Back** button in the header.
- Smart **Breadcrumbs** distinguishing feed identity from path.

---

## 9. Views Reference

### FeedListView (`views/feed_list.py`)

Root screen for feed selection.

### 9.2 FeedBrowser (`ui/views/feed_browser.py`)

A high-level "Traffic Cop" that coordinates feed rendering. It does not perform rendering directly; instead, it delegates to specialized sub-views based on the active feed profile's `paging_mode`.

- **PagedFeedView**: Traditional dashboard layout with stacked `CollapsibleSection` widgets in a `QScrollArea`. Used for highly structured, mixed-content feeds.
- **ScrolledFeedView**: High-performance continuous scroll using a section-level virtual scroll area (`QAbstractScrollArea`).

#### ScrolledFeedView Scroll Modes

`ScrolledFeedView` dynamically selects a strategy based on the `FeedPage` structure:

1. **Virtualized Grid**: Used when a primary content section (`main_section`) is identified with a known `total_items`. The view pre-allocates the entire vertical scroll range, fetching items sparsely as they enter the viewport.
2. **Infinite Grid**: Used when a `main_section` is identified but its total length is unknown. New items are fetched from the `next_url` and appended to the existing grid as the user scrolls.
3. **Infinite Sections**: Used for feeds that lack a single primary grid but provide a `next_url` (e.g., a dashboard that continues to add new categorical groups). New pages are fetched and their sections (headers + content) are appended to the view.
4. **Static Mode**: The fallback for feeds without pagination metadata or those that do not qualify for the automated scrolling modes. Only the first page is rendered.

- **Search Integration**: Redirects search queries to the relevant OPDS search template, rendering results via the standard paged/scrolled sub-views.

### FeedDetailView (`views/feed_detail.py`)

Full publication metadata and actions (Read/Download) for online comics. Opens **FeedReaderView**.

### FeedReaderView (`views/feed_reader.py`)

OPDS streaming reader (extends BaseReaderView).

### LocalLibraryView (`views/local_library.py`)

Local comic library browser with grouping support.

### LocalDetailView (`views/local_detail.py`)

Detail view for local comics. Opens **LocalReaderView**.

### LocalReaderView (`views/local_reader.py`)

Offline CBZ reader (extends BaseReaderView).

---

## 10. Base Components

### `BaseReaderView` (`ui/base_reader.py`)

Shared engine for online and local readers. Handles UI overlays, hotkeys, page compositing, and context-aware book transitions.

---

## 11. Theme System

**`ThemeManager`** (`ui/theme_manager.py`)

Modern "thin-bar" design language with 4px progress bars and themed scrollbars. Supports Light, Dark, OLED, Blue, and Light Blue presets.

---

## 12. Multi-Select & Selection Mode

Supports explicit selection mode for bulk downloads and deletions with tiered identity keys.

---

## 13. Context Menus

Right-click shortcuts for quick actions (Download, Mark Read/Unread, Delete) across the application.

---

## 14. Threading & Concurrency

Leverages `asyncio.to_thread` for blocking I/O and `qasync` for event loop integration.

---

## 15. Caching Strategy

Persistent JSON and image caches maintained for the duration of the application session.

---

## 16. Data Flows

### Opening an Online Publication

```
User clicks PublicationCard
  → on_open_detail(pub, self_url, context_pubs)
      → FeedDetailView.load_publication(pub, url, ..., context_pubs)
          → progression_sync.get_progression(endpoint)

User clicks Read
  → on_read_book(pub, manifest_url, context_pubs)
      → FeedReaderView.load_manifest(pub, manifest_url, ..., context_pubs)
```

### Opening a Local Comic

```
User double-clicks comic in LocalLibraryView
  → on_open_local_comic(path, context_paths)
      → LocalDetailView.load_path(path, context_paths)

User clicks Read
  → on_read_local_comic(path, context_paths)
      → LocalReaderView.load_cbz(path, context_paths)
```

---

## 17. Navigation & History

Independent `feed_history` and `search_history` stacks with support for deep-link breadcrumb jumping.

---

## 18. Testing

See TESTING.md

---

