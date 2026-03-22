# ComicCatcher TODO

## UI & UX
...
## Technical Debt & Refactoring
- [x] **Debt Audit**: Identified "band-aid" solutions and redundancy.
    - [!] **Silent Failures**: 20+ `except: pass` blocks found in `api/local_db.py`, `api/download_manager.py`, and views. Need proper logging or recovery.
    - [!] **Heuristic Sprawl**: Duplicate Artist grouping, Date formatting, and File Size logic in `LocalDetailView`, `FeedDetailView`, and `MiniDetailPopover`.
    - [!] **Hardcoded Server Hacks**: "komgaandroid" URL fix in `feed_management.py`.
    - [!] **SVG Hacks**: String-based color replacement in `ThemeManager` and `BaseCardDelegate` instead of CSS/proper SVG manipulation.
    - [ ] **Feed Data Model**: Bridge the gap between `Publication` (OPDS) and `dict` (Local) so views can share 100% of rendering logic.
- [ ] **Address Pixel-Crafted Fragility**: Transition from hardcoded pixel math (e.g., `y -= 12`) to metric-relative logic.
    - [ ] Use `QFontMetrics` to calculate offsets proportional to font size.
    - [ ] Replace `elidedText` heuristics with `QTextLayout` for robust multi-line elision.
    - [ ] Centralize remaining magic numbers into `UIConstants`.
- [ ] **High-DPI Validation**: Verify toolbar and card layouts on high-resolution displays with OS scaling.
- [ ] **Reader Polish**: Implement smooth transitions between pages or "manga mode" (RtL) enhancements, as well as scrolling mode (infinite comics)
- [ ] **Reader COntrols**: Better control for zooming and navitaing while zoomed. i.e. Ctrl+wheel.   or wheel acting different for higher zoom levels.   
- [ ] **Reader Image Display**: investigae higher quality re-scaling to avoid artifactsA

## Features
- [ ] **Advanced Filtering**: Add a search/filter bar to the Library view toolbar.


## Cross Platform Testing
- [ ] **Windows**: test on windows VM
- [ ] **MacOS**: how do this without a mac??

