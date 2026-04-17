# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

from __future__ import annotations

import io
from pathlib import Path
from typing import List, Optional

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

class PDFFile:
    SUFFIX = ".pdf"

    @classmethod
    def to_datetime(cls, _value) -> datetime:
        """Zero."""
        return datetime(1970, 1, 1, tzinfo=timezone.utc)

    @classmethod
    def to_pdf_date(cls, _value):
        """Empty."""

    @classmethod
    def is_pdffile(cls, path: str) -> bool:
        if not path:
            return False
        return Path(path).suffix.lower() == cls.SUFFIX

    def __init__(self, path: str):
        if fitz is None:
            raise ImportError("PyMuPDF (fitz) is not installed. PDF support unavailable.")
        self.path = path
        self.doc = fitz.open(path)
        self._page_count = self.doc.page_count
        # Pre-generate namelist for consistency. 
        # Using .jpg is much faster to encode/decode than .png for comics.
        self._names = [f"page_{i:03d}.jpg" for i in range(self._page_count)]

    def namelist(self) -> List[str]:
        return self._names

    def infolist(self) -> List:
        # Comicbox uses infolist for sorting and metadata.
        class StubInfo:
            def __init__(self, name, size):
                self.filename = name
                self.file_size = size
        return [StubInfo(n, 0) for n in self._names]

    def read(self, filename: str, fmt: str = "jpg", props: dict | None = None) -> bytes:
        """
        Renders or extracts a PDF page image.
        filename: expected to be 'page_NNN.jpg'
        """
        try:
            # Extract index from filename
            idx = self._names.index(filename)
        except ValueError:
            return b""

        if idx < 0 or idx >= self._page_count:
            return b""

        page = self.doc.load_page(idx)

        # --- FAST PATH: Direct Image Extraction ---
        # If the page consists essentially of one large image (very common in comic PDFs),
        # extracting it directly is much faster and preserves original quality exactly.
        img_list = page.get_images()
        # Heuristic: If exactly one image and no text, it's a pure "comic page".
        if len(img_list) == 1:
            text = page.get_text().strip()
            if not text:
                xref = img_list[0][0]
                base_image = self.doc.extract_image(xref)
                if base_image:
                    return base_image["image"]

        # --- SLOW PATH: Optimized Rendering ---
        # Fall back to rendering if the page is complex (text + images, multiple images, etc.)
        # Optimization: 1.6x zoom (approx 115 DPI) is usually plenty for comics
        # and significantly faster/lighter than 2.0x (144 DPI).
        zoom = 1.6
        mat = fitz.Matrix(zoom, zoom)
        
        # Default to jpg for speed and smaller cache footprint
        img_format = fmt.lower() if fmt else "jpg"
        if img_format not in ("png", "webp", "jpg", "jpeg"):
            img_format = "jpg"

        # annots=False avoids rendering sticky notes/comments which saves cycles
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB, alpha=False, annots=False)
        
        if img_format in ("jpg", "jpeg"):
            return pix.tobytes("jpg", jpg_quality=85)
        return pix.tobytes(img_format)

    def close(self):
        if hasattr(self, "doc") and self.doc:
            self.doc.close()
            self.doc = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def get_metadata(self) -> dict:
        if not self.doc:
            return {}
        return self.doc.metadata
