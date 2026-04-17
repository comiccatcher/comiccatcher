# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from comiccatcher.logger import get_logger


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


def read_comicbox_dict_and_cover(path: Path) -> Tuple[Dict[str, Any], Optional[bytes]]:
    """
    Read comic metadata AND cover image in a single comicbox pass.
    Returns (metadata_dict, cover_bytes_or_None).
    """
    try:
        from comicbox.box import Comicbox  # type: ignore
    except ImportError as e:
        return {"_comicbox_status": "missing", "_comicbox_error": str(e)}, None

    try:
        with Comicbox(str(path)) as cb:
            d = cb.to_dict() or {}
            try:
                cover = cb.get_cover_page()
            except Exception:
                cover = None
        if not d:
            return {"_comicbox_status": "empty"}, cover
        return d, cover
    except Exception as e:
        logger.info(f"comicbox read failed for {path}: {e}")
        return {"_comicbox_status": "error", "_comicbox_error": str(e)}, None


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
    flat["month"] = _get(inner, "date", "month")
    flat["publisher"] = _get(inner, "publisher", "name")
    flat["summary"] = _get(inner, "summary")
    if not flat["summary"]:
        # PDF fallback: comicbox often maps PDF:Subject to genres
        flat["summary"] = _get(inner, "genres")

    if isinstance(flat["summary"], (list, set)):
        flat["summary"] = ", ".join(str(s) for s in flat["summary"])
    elif isinstance(flat["summary"], dict):
        flat["summary"] = ", ".join(str(s) for s in flat["summary"].keys())

    flat["page_count"] = _get(inner, "page_count")
    flat["manga"] = _get(inner, "manga")
    flat["notes"] = _get(inner, "notes")
    flat["imprint"] = _get(inner, "publisher", "imprint")
    
    genres = _get(inner, "genres")
    if isinstance(genres, (list, set)):
        flat["genre"] = ", ".join(str(g) for g in genres)
    elif isinstance(genres, dict):
        flat["genre"] = ", ".join(str(g) for g in genres.keys())
    else:
        flat["genre"] = str(genres) if genres else ""

    web_urls = []
    
    # 1. Check explicit web field
    web = _get(inner, "web")
    if isinstance(web, list):
        web_urls.extend([str(w) for w in web if w])
    elif web:
        web_urls.append(str(web))

    # 2. Check identifiers (e.g., comicvine, metron) for URLs
    identifiers = _get(inner, "identifiers")
    if isinstance(identifiers, dict):
        for id_type, id_info in identifiers.items():
            if isinstance(id_info, dict):
                u = id_info.get("url")
                if u:
                    web_urls.append(str(u))
    
    flat["web"] = ", ".join(list(dict.fromkeys(web_urls))) # De-duplicate while preserving order

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


def generate_comic_labels(meta: Dict[str, Any], focus: str) -> Tuple[str, str]:
    """
    Generate primary and secondary labels for a comic based on metadata and focus preference.
    Focus can be "series" or "title".
    Returns (primary, secondary).
    """
    if not isinstance(meta, dict):
        return "", ""

    series = (meta.get("series") or "").strip()
    issue = str(meta.get("issue") or "").strip()
    volume = str(meta.get("volume") or "").strip()
    year = meta.get("year")
    title = (meta.get("title") or "").strip()

    # 1. Format Series Info: Series (Year) #Issue or Series vVolume #Issue
    series_parts = []
    if series:
        series_parts.append(series)

        import re
        is_year = False
        if volume and re.match(r"^\d{4}$", volume):
            v_val = int(volume)
            if 1900 <= v_val <= 2100:
                is_year = True

        if is_year:
            series_parts.append(f"({volume})")
        elif volume:
            series_parts.append(f"v{volume}")
        elif year:
            y_str = str(year)
            if len(y_str) >= 4 and y_str[:4].isdigit():
                series_parts.append(f"({y_str[:4]})")

        if issue:
            series_parts.append(f"#{issue}")

    series_info = " ".join(series_parts).strip()

    # 2. Assign Primary/Secondary
    if focus == "title" and title:
        primary = title
        secondary = series_info
    else:
        primary = series_info or title or "Unknown Comic"
        secondary = title if primary != title else ""

    return primary, secondary

