# E2E Driver Reference

This folder contains Python scripts designed to be used with the `--e2e-driver` argument in `main.py`.

## Purpose
These are "True E2E" tests that drive the full application instance (not just a single widget). They interact with real user settings and live feeds.

## Architectural Stability Note
These scripts rely on the internal widget structure of the `MainWindow` and its sub-views (e.g., `_impl` in `ScrolledFeedView` or `scroll_area` in `PagedFeedView`).

As the application architecture evolves, these paths may change. If a driver fails with an `AttributeError` (e.g., "object has no attribute 'verticalScrollBar'"), update the driver to use the new widget hierarchy.

## Available Drivers

| Driver | Description |
|---|---|
| `scroll_validation.py` | Verifies that 'Down' arrow keys scroll exactly one card row (Step = CardHeight + Gutter). |
