from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import zipfile


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass(frozen=True)
class LocalPage:
    name: str
    index: int


def list_cbz_pages(path: Path) -> List[LocalPage]:
    """
    List image entries in a CBZ, sorted for reading order.
    """
    p = Path(path)
    if not p.exists() or not p.is_file():
        return []

    pages: List[str] = []
    with zipfile.ZipFile(p, "r") as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            name = info.filename
            ext = Path(name).suffix.lower()
            if ext in IMAGE_EXTS:
                pages.append(name)

    # Sort by path/name; ComicTagger outputs typically use zero-padded names.
    pages.sort(key=lambda s: s.lower())
    return [LocalPage(name=n, index=i) for i, n in enumerate(pages)]


def read_cbz_entry_bytes(path: Path, name: str) -> Optional[bytes]:
    p = Path(path)
    if not p.exists() or not p.is_file():
        return None
    with zipfile.ZipFile(p, "r") as z:
        with z.open(name, "r") as f:
            return f.read()


def read_first_image(path: Path) -> Optional[tuple[str, bytes]]:
    """
    Returns (name, bytes) for the first image entry in the CBZ, or None if unavailable.
    """
    pages = list_cbz_pages(path)
    if not pages:
        return None
    first = pages[0]
    data = read_cbz_entry_bytes(path, first.name)
    if data is None:
        return None
    return first.name, data
