# ComicCatcher TODO

## Final Changes


## deployment

* settle on version style

* set up github actions for
  * pypi package and deployment
  * appimage creation
  * standalone windows exe
  * unsigned macos app 

## testing

* windows and mac testing

## bug reports:

* Stump -
  * pub date format in feed not standard iso
  * position is the index of the item in the personal collection, not the issue number,  I;m not sure
  * Latest Books / Keep Reading preview groups on start feed aren't getting updated even though the linked feeds are up-to-date
  * Same problem for <library-name>/Library Books - Latest preview group
  * crash stump page 4 - need to collect logs

* Komga:
  * Writer credit (visible in Komga UI) is not in iOPDS feed or manifest

* Codex
  * Ask about facets
  * Progression total_progress is not standard.
  * Broach statelessness w/r/t search

  

## Misc Lower
  
* keystrokes for feed and library

* dynamic grid scrolling flakes out with cervantes, where even though there are marked 9000 items in the feed, last page only goes to 1000 items
  * maybe transient?

* refactoring opportunities:
  * check for any buttons, margins, sizes, font sizes, etc that aren't scaled
  * centralize all style setting, and have everything respect themes
  * more consolidation/deduplcation of code
  * less magic numbers everywhee. Too many literal constants.
  * maybe more  `QFontMetrics`etc to calculate offsets proportional to font size.
  * better text eliding via QTextLayout, maybe, if not a performace hit

* readino space opera incorrectly decided as infinite sections and NOT infinite grid. App needs more robust "main section" selection. It may not be possible to be perfect
* bug with scrolled feeds or codex giving wrong series count.
  * manifests as extra cards at end of seroes scroll in codex (think codex is culprit when counts aren't updated when files are removed/added)

* why are subtiles be parsed from titles with colons? (maybe this is gone?)

## Future Enhancments
* OPDS 1.2 
* Search/filter in library
* Different sized cards: small/medium/large
* Save server metadata in local DB, or in files themselves

