from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from logger import get_logger


logger = get_logger("ui.local_comicbox")


def read_comicbox_dict(path: Path) -> Dict[str, Any]:
    """
    Read comic metadata via comicbox.

    Returns a dict with either:
    - {"comicbox": {...}} (as produced by comicbox)
    - {"_comicbox_status": "missing"|"error", "_comicbox_error": "..."}
    """
    try:
        from comicbox.box import Comicbox  # type: ignore
    except ImportError as e:
        return {"_comicbox_status": "missing", "_comicbox_error": str(e)}

    try:
        with Comicbox(str(path)) as cb:
            d = cb.to_dict() or {}
        if not d:
            return {"_comicbox_status": "empty"}
        return d
    except Exception as e:
        logger.info(f"comicbox read failed for {path}: {e}")
        return {"_comicbox_status": "error", "_comicbox_error": str(e)}


def read_comicbox_cover(path: Path) -> Optional[bytes]:
    """
    Read the cover image bytes via comicbox.
    """
    try:
        from comicbox.box import Comicbox  # type: ignore
    except ImportError:
        return None

    try:
        with Comicbox(str(path)) as cb:
            return cb.get_cover_page()
    except Exception as e:
        logger.debug(f"comicbox cover read failed for {path}: {e}")
        return None


def _inner(d: Dict[str, Any]) -> Dict[str, Any]:
    # comicbox currently returns {"comicbox": {...}} at the top level.
    inner = d.get("comicbox")
    return inner if isinstance(inner, dict) else d


def _get(d: Dict[str, Any], *keys: str) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _names_for_role(credits: Any, role: str) -> List[str]:
    """
    credits is typically:
      { "Alan Moore": { "roles": {"Writer": {...}} }, ... }
    """
    out: List[str] = []
    if not isinstance(credits, dict):
        return out
    for name, info in credits.items():
        if not isinstance(info, dict):
            continue
        roles = info.get("roles")
        if isinstance(roles, dict) and role in roles:
            out.append(str(name))
    return out


def flatten_comicbox(d: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert comicbox output into the flat fields our UI expects.
    """
    if not isinstance(d, dict):
        return {}
    status = d.get("_comicbox_status")
    if status:
        return {"_comicbox_status": status, "_comicbox_error": d.get("_comicbox_error")}

    inner = _inner(d)

    flat: Dict[str, Any] = {}
    flat["title"] = _get(inner, "title")
    flat["series"] = _get(inner, "series", "name")

    issue_name = _get(inner, "issue", "name")
    issue_num = _get(inner, "issue", "number")
    flat["issue"] = issue_name or issue_num

    flat["volume"] = _get(inner, "volume", "number") or _get(inner, "volume")
    flat["year"] = _get(inner, "date", "year") or _get(inner, "date", "cover_date")
    flat["publisher"] = _get(inner, "publisher", "name")
    flat["summary"] = _get(inner, "summary")
    flat["page_count"] = _get(inner, "page_count")

    credits = _get(inner, "credits")
    flat["writer"] = ", ".join(_names_for_role(credits, "Writer"))
    flat["penciller"] = ", ".join(_names_for_role(credits, "Penciller"))
    flat["inker"] = ", ".join(_names_for_role(credits, "Inker"))
    flat["colorist"] = ", ".join(_names_for_role(credits, "Colorist"))
    flat["letterer"] = ", ".join(_names_for_role(credits, "Letterer"))
    flat["editor"] = ", ".join(_names_for_role(credits, "Editor"))
    flat["cover_artist"] = ", ".join(_names_for_role(credits, "CoverArtist"))

    # If everything is empty, report as empty.
    has_any = any(v not in (None, "", [], {}) for k, v in flat.items() if not k.startswith("_"))
    if not has_any:
        flat["_comicbox_status"] = "empty"
    return flat


def subtitle_from_flat(flat: Dict[str, Any]) -> str:
    """
    Make a single-line subtitle like: "Swamp Thing #57 (1987)".
    """
    if not isinstance(flat, dict):
        return ""
    series = (flat.get("series") or "").strip()
    issue = str(flat.get("issue") or "").strip()
    year = flat.get("year")

    year_s = ""
    if year is not None:
        year_s = str(year)
        # If cover_date datetime/date sneaks in, just keep first 4 digits if present.
        if len(year_s) >= 4 and year_s[:4].isdigit():
            year_s = year_s[:4]

    parts: List[str] = []
    if series:
        if issue:
            parts.append(f"{series} #{issue}")
        else:
            parts.append(series)

    if year_s:
        parts.append(f"({year_s})")

    return " ".join(parts).strip()

