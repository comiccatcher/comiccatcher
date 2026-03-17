from __future__ import annotations

import base64
from pathlib import Path
from urllib.parse import urlsplit


# 1x1 transparent pixel placeholder (PNG), base64 payload only (no data: prefix).
TRANSPARENT_PIXEL_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
TRANSPARENT_DATA_URL = f"data:image/png;base64,{TRANSPARENT_PIXEL_B64}"


def data_url_from_b64(b64: str, mime: str = "image/jpeg") -> str:
    b64 = (b64 or "").strip()
    mime = (mime or "application/octet-stream").strip()
    if not b64:
        return TRANSPARENT_DATA_URL
    return f"data:{mime};base64,{b64}"


def data_url_from_bytes(data: bytes, mime: str = "image/jpeg") -> str:
    if not data:
        return TRANSPARENT_DATA_URL
    encoded = base64.b64encode(data).decode("utf-8")
    return data_url_from_b64(encoded, mime)


def normalize_b64(b64: str) -> str:
    return (b64 or "").strip()


def guess_mime_from_url(url: str, default: str = "image/jpeg") -> str:
    try:
        ext = Path(urlsplit(url).path).suffix.lower()
    except Exception:
        ext = ""
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    if ext == ".png":
        return "image/png"
    if ext == ".webp":
        return "image/webp"
    return default
