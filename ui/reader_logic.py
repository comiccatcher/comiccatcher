from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin


def parse_reading_order(manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract reading order entries from an OPDS/Readium-ish manifest JSON.

    Returns a list of dicts (each typically includes at least "href" and optionally "type"/"mediaType").
    """
    if not isinstance(manifest, dict):
        return []
    ro = manifest.get("readingOrder") or manifest.get("spine") or []
    if not isinstance(ro, list):
        return []

    out: List[Dict[str, Any]] = []
    for item in ro:
        if isinstance(item, dict) and item.get("href"):
            out.append(item)
    return out


def resolve_href(base_url: str, href: str) -> str:
    """Resolve possibly-relative href against base_url."""
    if not href:
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return urljoin((base_url or "").rstrip("/") + "/", href)


def guess_mime(item: Dict[str, Any], default: str = "image/jpeg") -> str:
    """Best-effort mime guess for a readingOrder item."""
    if not isinstance(item, dict):
        return default
    mime = item.get("type") or item.get("mediaType") or default
    if not isinstance(mime, str) or not mime:
        return default
    return mime


def make_data_url(mime: str, b64: str) -> str:
    """Create a data URL from a mime type and base64 payload (no validation beyond basic shape)."""
    mime = (mime or "application/octet-stream").strip()
    b64 = (b64 or "").strip()
    return f"data:{mime};base64,{b64}"


def clamp_index(idx: int, total: int) -> int:
    if total <= 0:
        return 0
    if idx < 0:
        return 0
    if idx >= total:
        return total - 1
    return idx


def index_from_progression(progress_pct: float, total: int) -> int:
    """
    Convert progression (0..1) to a page index.

    Matches the app's current behavior: int(progress * total), clamped to [0, total-1].
    """
    if total <= 0:
        return 0
    try:
        pct = float(progress_pct)
    except Exception:
        pct = 0.0
    # Treat NaN as 0.0 without importing math.
    if pct != pct:
        pct = 0.0
    return clamp_index(int(pct * total), total)


@dataclass
class ReaderSession:
    """
    UI-agnostic reader state machine.

    This is intentionally I/O-free so it can be exercised in unit tests.
    """

    base_url: str
    reading_order: List[Dict[str, Any]]
    index: int = 0

    @property
    def total(self) -> int:
        return len(self.reading_order or [])

    def set_index(self, idx: int) -> int:
        self.index = clamp_index(int(idx), self.total)
        return self.index

    def set_progression(self, progress_pct: float) -> int:
        self.index = index_from_progression(progress_pct, self.total)
        return self.index

    def current_item(self) -> Optional[Dict[str, Any]]:
        if self.total <= 0:
            return None
        if self.index < 0 or self.index >= self.total:
            return None
        return self.reading_order[self.index]

    def current_href(self) -> str:
        item = self.current_item()
        if not item:
            return ""
        href = item.get("href") if isinstance(item, dict) else ""
        return href or ""

    def current_url(self) -> str:
        return resolve_href(self.base_url, self.current_href())

    def can_next(self) -> bool:
        return self.total > 0 and self.index < self.total - 1

    def can_prev(self) -> bool:
        return self.total > 0 and self.index > 0

    def next(self) -> int:
        if self.can_next():
            self.index += 1
        return self.index

    def prev(self) -> int:
        if self.can_prev():
            self.index -= 1
        return self.index

    def jump(self, idx: int) -> int:
        return self.set_index(idx)

