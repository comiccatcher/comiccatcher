# ComicCatcher TODO

## Feed Stuff

* bug with scrolled feeds or codex giving wrong series count.
    manifests as extra cards at end of seroes scroll in codex (think codex is culprit when counts aren't updated when files are removed/added)

* handle pagination metadata that may be corrupt or buggy.  Might need an "unknown" concept for itemsperpage, and number of items if the first page data doesn't match those numbers
   See: https://www.lirtuel.be/v1/bundles.opds2

* Bad OPDS pages to maybe work around:
   komga > Latest Series See All, somehow goes to publications

## Reader & UI

* add mini-details in feed view -  download in place of delete button
* mini-details - add read, select buttons.
* new "read" svg, maybe also "mark as read", "mark as unread"

* keystrokes for feed and library
* reader keystrokes and controls fixing

* better feedback on failed connection to server

* Warning about logo fetch fail.  Is that always happing in the background?
2026-04-10 23:12:55,230 - httpx - INFO - HTTP Request: GET https://test.opds.io/favicon.ico "HTTP/1.1 404 Not Found"
2026-04-10 23:12:55,233 - comiccatcher.api.image_manager - WARNING - Failed to fetch image https://test.opds.io/favicon.ico - Status: 404

* paging nav buttons should update before fetch??


## deployment
* upload to pypi account

## testing

* windows and mac testing

## Misc

* fix  "komgaandroid" URL hack in `feed_management.py`.
* Duplicate Artist grouping, Date formatting, and File Size logic in `LocalDetailView`, `FeedDetailView`, and `MiniDetailPopover`.
* String-based color replacement in `ThemeManager` and `BaseCardDelegate` instead of CSS/proper SVG manipulation.
* more consolidation/deduplcation of code
* less magic numbers
* maybe more  `QFontMetrics` to calculate offsets proportional to font size.
* better text eliding via QTextLayout, maybe

## Future
* OPDS 1.2 
* Search/filter in library
* Inifinite scroll even if no main axis data found
