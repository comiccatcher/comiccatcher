import sqlite3
from pathlib import Path
from typing import Dict, List, Any, Optional
import threading

from logger import get_logger

logger = get_logger("api.local_db")

class LocalLibraryDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # We use check_same_thread=False because the app is asyncio-based and threads
        # might be used (e.g. asyncio.to_thread). We use a lock to ensure thread safety.
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self):
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS comics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT UNIQUE NOT NULL,
                    file_mtime REAL NOT NULL,
                    title TEXT,
                    series TEXT,
                    issue TEXT,
                    volume TEXT,
                    year TEXT,
                    publisher TEXT,
                    summary TEXT,
                    page_count INTEGER,
                    writer TEXT,
                    penciller TEXT,
                    inker TEXT,
                    colorist TEXT,
                    letterer TEXT,
                    editor TEXT,
                    cover_artist TEXT,
                    current_page INTEGER DEFAULT 0,
                    last_read REAL,
                    source_url TEXT,
                    _status TEXT
                )
            """)
            
            self.conn.commit()
            self._migrate_db()
            
            # Create indexes for fast sorting/grouping
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_series ON comics(series)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_publisher ON comics(publisher)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_title ON comics(title)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_url ON comics(source_url)")
            self.conn.commit()

    def _migrate_db(self):
        with self._lock:
            cursor = self.conn.cursor()
            try:
                cursor.execute("ALTER TABLE comics ADD COLUMN current_page INTEGER DEFAULT 0")
            except: pass
            try:
                cursor.execute("ALTER TABLE comics ADD COLUMN last_read REAL")
            except: pass
            try:
                cursor.execute("ALTER TABLE comics ADD COLUMN source_url TEXT")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_url ON comics(source_url)")
            except: pass
            self.conn.commit()

    def update_progress(self, file_path: str, current_page: int, page_count: Optional[int] = None):
        import time
        with self._lock:
            cursor = self.conn.cursor()
            if page_count is not None:
                cursor.execute("""
                    UPDATE comics SET current_page = ?, page_count = ?, last_read = ? WHERE file_path = ?
                """, (current_page, page_count, time.time(), file_path))
            else:
                cursor.execute("""
                    UPDATE comics SET current_page = ?, last_read = ? WHERE file_path = ?
                """, (current_page, time.time(), file_path))
            self.conn.commit()

    def mark_as_read(self, file_path: str):
        import time
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT page_count FROM comics WHERE file_path = ?", (file_path,))
            row = cursor.fetchone()
            if row:
                page_count = row["page_count"] or 9999  # Fallback high number if unknown
                cursor.execute("""
                    UPDATE comics SET current_page = ?, last_read = ? WHERE file_path = ?
                """, (page_count, time.time(), file_path))
                self.conn.commit()

    def mark_as_unread(self, file_path: str):
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE comics SET current_page = 0 WHERE file_path = ?
            """, (file_path,))
            self.conn.commit()

    def get_comic(self, file_path: str) -> Optional[sqlite3.Row]:
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM comics WHERE file_path = ?", (file_path,))
            return cursor.fetchone()

    def get_comic_by_url(self, url: str) -> Optional[sqlite3.Row]:
        if not url: return None
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM comics WHERE source_url = ?", (url,))
            return cursor.fetchone()

    def set_source_url(self, file_path: str, url: str):
        if not url: return
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("UPDATE comics SET source_url = ? WHERE file_path = ?", (url, file_path))
            self.conn.commit()

    def get_all_comics_mtimes(self) -> Dict[str, float]:
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT file_path, file_mtime FROM comics")
            return {row["file_path"]: row["file_mtime"] for row in cursor.fetchall()}

    def upsert_comic(self, file_path: str, mtime: float, meta: Dict[str, Any], source_url: Optional[str] = None):
        with self._lock:
            cursor = self.conn.cursor()
            
            # If source_url is NOT provided, we want to PRESERVE any existing source_url
            if source_url is None:
                cursor.execute("SELECT source_url FROM comics WHERE file_path = ?", (file_path,))
                row = cursor.fetchone()
                if row:
                    source_url = row["source_url"]

            cursor.execute("""
                INSERT INTO comics (
                    file_path, file_mtime, title, series, issue, volume, year,
                    publisher, summary, page_count, writer, penciller, inker,
                    colorist, letterer, editor, cover_artist, source_url, _status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_path) DO UPDATE SET
                    file_mtime=excluded.file_mtime,
                    title=excluded.title,
                    series=excluded.series,
                    issue=excluded.issue,
                    volume=excluded.volume,
                    year=excluded.year,
                    publisher=excluded.publisher,
                    summary=excluded.summary,
                    page_count=excluded.page_count,
                    writer=excluded.writer,
                    penciller=excluded.penciller,
                    inker=excluded.inker,
                    colorist=excluded.colorist,
                    letterer=excluded.letterer,
                    editor=excluded.editor,
                    cover_artist=excluded.cover_artist,
                    source_url=excluded.source_url,
                    _status=excluded._status
            """, (
                file_path,
                mtime,
                meta.get("title"),
                meta.get("series"),
                str(meta.get("issue")) if meta.get("issue") is not None else None,
                str(meta.get("volume")) if meta.get("volume") is not None else None,
                str(meta.get("year")) if meta.get("year") is not None else None,
                meta.get("publisher"),
                meta.get("summary"),
                meta.get("page_count"),
                meta.get("writer"),
                meta.get("penciller"),
                meta.get("inker"),
                meta.get("colorist"),
                meta.get("letterer"),
                meta.get("editor"),
                meta.get("cover_artist"),
                source_url,
                meta.get("_comicbox_status", "ok")
            ))
            self.conn.commit()

    def remove_comic(self, file_path: str):
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM comics WHERE file_path = ?", (file_path,))
            self.conn.commit()

    def remove_missing_comics(self, current_paths: List[str]) -> int:
        """Remove entries that are no longer in the file system. Returns count removed."""
        if not current_paths:
            return 0
            
        with self._lock:
            cursor = self.conn.cursor()
            # chunk to avoid sqlite limits
            chunk_size = 500
            
            # Get all paths first
            cursor.execute("SELECT file_path FROM comics")
            db_paths = {row["file_path"] for row in cursor.fetchall()}
            
            current_set = set(current_paths)
            to_delete = list(db_paths - current_set)
            
            total_deleted = 0
            for i in range(0, len(to_delete), chunk_size):
                chunk = to_delete[i:i+chunk_size]
                placeholders = ",".join("?" * len(chunk))
                cursor.execute(f"DELETE FROM comics WHERE file_path IN ({placeholders})", chunk)
                total_deleted += cursor.rowcount
                
            self.conn.commit()
            return total_deleted
            
    def get_all_comics_alphabetical(self) -> List[sqlite3.Row]:
        with self._lock:
            cursor = self.conn.cursor()
            # Sort by series, then issue, then title fallback
            cursor.execute("""
                SELECT * FROM comics 
                ORDER BY 
                    CASE WHEN series IS NULL OR series = '' THEN title ELSE series END ASC,
                    CAST(issue AS REAL) ASC,
                    title ASC
            """)
            return cursor.fetchall()
            
    def get_comics_grouped_by_series(self) -> Dict[str, List[sqlite3.Row]]:
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM comics 
                ORDER BY 
                    series ASC, 
                    CAST(issue AS REAL) ASC,
                    title ASC
            """)
            rows = cursor.fetchall()
            
        grouped = {}
        for row in rows:
            series = row["series"]
            if not series or series.strip() == "":
                series = "Unknown Series"
            if series not in grouped:
                grouped[series] = []
            grouped[series].append(row)
            
        return grouped

    def get_comics_grouped_by_field(self, field: str) -> Dict[str, List[sqlite3.Row]]:
        with self._lock:
            cursor = self.conn.cursor()
            # Allowed fields to prevent SQL injection (though we control the input)
            allowed = ["series", "publisher", "writer", "year", "penciller"]
            if field not in allowed:
                field = "series"
                
            cursor.execute(f"""
                SELECT * FROM comics 
                ORDER BY 
                    {field} ASC, 
                    CAST(issue AS REAL) ASC,
                    title ASC
            """)
            rows = cursor.fetchall()
            
        grouped = {}
        for row in rows:
            val = row[field]
            if not val or (isinstance(val, str) and val.strip() == ""):
                val = f"Unknown {field.replace('_', ' ').capitalize()}"
            if val not in grouped:
                grouped[val] = []
            grouped[val].append(row)
            
        return grouped

    def get_comics_in_dir(self, dir_path: str) -> Dict[str, sqlite3.Row]:
        """Return all comics under a directory, keyed by absolute file_path."""
        with self._lock:
            cursor = self.conn.cursor()
            prefix = dir_path.rstrip('/') + '/'
            cursor.execute("SELECT * FROM comics WHERE file_path LIKE ?", (prefix + '%',))
            rows = cursor.fetchall()
        return {row['file_path']: row for row in rows}

    def close(self):
        with self._lock:
            if self.conn:
                self.conn.close()
                self.conn = None
