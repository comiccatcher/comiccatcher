# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from comiccatcher.logger import get_logger

logger = get_logger("ui.local_archive")

@dataclass(frozen=True)
class LocalPage:
    name: str
    index: int


def list_archive_pages(path: Path) -> List[LocalPage]:
    """
    List image entries in a comic archive (CBZ, CBR, CB7, CBT, PDF), 
    sorted for reading order via comicbox.
    """
    p = Path(path)
    if not p.exists() or not p.is_file():
        return []

    try:
        from comicbox.box import Comicbox  # type: ignore
        with Comicbox(str(p)) as cb:
            # Comicbox already filters out metadata files and sorts case-insensitively.
            pages = cb.get_page_filenames()
            return [LocalPage(name=n, index=i) for i, n in enumerate(pages)]
    except Exception as e:
        logger.error(f"Failed to list pages for {path}: {e}")
        return []


def read_archive_entry_bytes(path: Path, name: str) -> Optional[bytes]:
    """
    Read the bytes of a specific entry (page) from the archive.
    """
    p = Path(path)
    if not p.exists() or not p.is_file():
        return None

    try:
        from comicbox.box import Comicbox  # type: ignore
        with Comicbox(str(p)) as cb:
            # comicbox's get_page_by_filename returns bytes.
            # It also handles decompression for ZIP, RAR, 7Z, and TAR.
            return cb.get_page_by_filename(name)
    except Exception as e:
        logger.error(f"Failed to read entry {name} from {path}: {e}")
        return None


def read_archive_first_image(path: Path) -> Optional[Tuple[str, bytes]]:
    """
    Returns (name, bytes) for the first image entry in the archive, or None if unavailable.
    """
    pages = list_archive_pages(path)
    if not pages:
        return None
    first = pages[0]
    data = read_archive_entry_bytes(path, first.name)
    if data is None:
        return None
    return first.name, data
