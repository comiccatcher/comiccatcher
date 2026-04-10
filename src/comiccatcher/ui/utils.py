import calendar
import re
from typing import Dict, List, Any, Optional, Tuple

def format_artist_credits(roles: Dict[str, str]) -> List[str]:
    """
    Intelligently group artist roles (Penciller, Inker, Colorist)
    if they share the same contributors.
    """
    final_creds = []
    if "Writer" in roles: final_creds.append(f"Writer: {roles['Writer']}")
    if "Author" in roles: final_creds.append(f"Writer: {roles['Author']}")
    
    # Combine Artist roles if they match
    # OPDS often uses 'Artist', local often uses 'Penciller'
    p = roles.get("Penciller") or roles.get("Artist")
    i = roles.get("Inker")
    c = roles.get("Colorist")
    
    if p and p == i:
        if c == p:
            final_creds.append(f"Artist: {p}")
        else:
            final_creds.append(f"Artist: {p}")
            if c: final_creds.append(f"Colorist: {c}")
    else:
        if p: final_creds.append(f"Artist: {p}" if "Artist" in roles and not roles.get("Penciller") else f"Penciller: {p}")
        if i: final_creds.append(f"Inker: {i}")
        if c: final_creds.append(f"Colorist: {c}")
        
    for role in ["Letterer"]:
        if role in roles: final_creds.append(f"{role}: {roles[role]}")
        
    return final_creds

def format_publication_date(month: Optional[Any], year: Optional[Any]) -> str:
    """Consistently format Month Year or just Year."""
    date_parts = []
    if month:
        try:
            m_val = int(month)
            if 1 <= m_val <= 12:
                date_parts.append(calendar.month_name[m_val])
        except (ValueError, TypeError):
            pass
    if year:
        date_parts.append(str(year))
    return " ".join(date_parts)

def format_file_size(size_bytes: int) -> str:
    """Format bytes into human-readable string."""
    if size_bytes <= 0: return ""
    num = float(size_bytes)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(num) < 1024.0:
            return f"{num:3.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} PB"

def parse_opds_date(date_str: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Try to extract month and year from OPDS date strings (ISO or YYYY-MM)."""
    if not date_str: return None, None

    # Try YYYY-MM first
    match = re.search(r"(\d{4})-(\d{2})", date_str)
    if match:
        return match.group(2), match.group(1)

    # Fallback to just YYYY
    match_y = re.search(r"(\d{4})", date_str)
    if match_y:
        return None, match_y.group(1)

    return None, None

