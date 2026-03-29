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
│  │  - Feeds    │   │  FeedList / Browser / FeedDetail / ...  │  │
│  │  - Library  │   │  LocalLibrary / LocalDetail / ...       │  │
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
    feed_browser.py          FeedBrowser coordinator (switches between paged/scrolled)
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

**`main.py`** contains the application entry point, setting up the `qasync` event loop and managing the application lifecycle.

---

## 4. Configuration

**`ConfigManager`** stores all persistent state in platform-appropriate locations.

---

## 5. Data Models

All models use **Pydantic v2** with `model_config = ConfigDict(extra='allow')` so unrecognised OPDS fields are preserved.

---

## 6. API Layer

### `APIClient` (`api/client.py`)

Thin async HTTP wrapper built on `httpx.AsyncClient`.

### `OPDS2Client` (`api/opds_v2.py`)

High-level OPDS 2.0 parser with in-memory JSON caching.

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
        ├── LibraryView (Local files)
        ├── SettingsView
        └── ReaderView (Comic viewer)
```

#### Component Hierarchy (Shared UI)
Reusable building blocks across different view modes.

```text
QStyledItemDelegate (Qt)
└── FeedCardDelegate (Paints cards, titles, and covers)

QWidget (Qt)
├── CollapsibleSection (Expandable section container)
└── QListView (Qt)
    └── BaseCardRibbon (Horizontal carousel with "See All" support)
```

### 8.2 MainWindow (`ui/app_layout.py`)

The root window containing the sidebar and stacked content views. Uses the `ViewIndex` enum for reliable navigation.

```
Stack Index (ViewIndex):
- FEED_LIST: 0
- LIBRARY: 1
- SETTINGS: 2
- FEED_BROWSER: 3
- LOCAL_DETAIL: 4
- LOCAL_READER: 5
- DETAIL: 6
- READER_ONLINE: 7
- SEARCH_ROOT: 8
- SEARCH_BROWSER: 9
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
- **ScrolledFeedView**: High-performance continuous scroll using a section-level virtual scroll area (`QAbstractScrollArea`). Each `FeedSection` becomes a real `SectionHeader` + content widget pair positioned directly in the viewport. Large GRID sections (up to 30 k items) use an internal `QListView` whose height is capped to the visible slice and whose scroll position is synced to the outer scrollbar — avoiding Qt's `QWIDGETSIZE_MAX` content-widget limit. Supports sparse page fetching, debounced scrubbing, and lazy thumbnail loading.

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

Modern "thin-bar" design language with 4px progress bars and themed scrollbars. Supports Light, Dark, OLED, and Blue presets.

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

Uses `pytest` with `pytest-asyncio` for core logic and integration testing.

---

## 19. Known Issues & Future Enhancements

### ReFit Mode
- **Non-aligned buffer start:** Edge case where the first loaded server page doesn't align with the ReFit virtual-page boundary.

### UI & UX
- **Feed browser grid columns:** Grid should adapt to viewport width.

### Performance
- **Large libraries:** Initial thumbnail grid render may be slow; needs a virtual list widget.
