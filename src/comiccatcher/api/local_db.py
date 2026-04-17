# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

import sqlite3
from pathlib import Path
from typing import Dict, List, Any, Optional
import threading

from comiccatcher.logger import get_logger

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
            
            # Get current version
            cursor.execute("PRAGMA user_version")
            version = cursor.fetchone()[0]
            logger.debug(f"Current DB version: {version}")

            # 1. Ensure table exists (legacy or new)
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
                    month TEXT,
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

            # 2. Run migrations based on version
            if version < 2:
                # Migration for fields added in this task
                fields_to_add = ["manga", "notes", "imprint", "genre", "web"]
                for f in fields_to_add:
                    try:
                        cursor.execute(f"ALTER TABLE comics ADD COLUMN {f} TEXT")
                        logger.info(f"Added column {f} to comics table.")
                    except sqlite3.OperationalError as e:
                        # Silently ignore if column already exists (handles legacy partial migrations)
                        if "duplicate column name" not in str(e).lower():
                            logger.warning(f"Migration error adding {f}: {e}")
                
                cursor.execute("PRAGMA user_version = 2")
                self.conn.commit()
                logger.info("Database migrated to version 2.")
            
            # Ensure indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_series ON comics(series)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_publisher ON comics(publisher)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_title ON comics(title)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_url ON comics(source_url)")
            self.conn.commit()

    def _migrate_db(self):
        # We handle migration in _init_db now via user_version
        pass

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
                    file_path, file_mtime, title, series, issue, volume, year, month,
                    publisher, summary, page_count, writer, penciller, inker,
                    colorist, letterer, editor, cover_artist, source_url, _status,
                    manga, notes, imprint, genre, web
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_path) DO UPDATE SET
                    file_mtime=excluded.file_mtime,
                    title=excluded.title,
                    series=excluded.series,
                    issue=excluded.issue,
                    volume=excluded.volume,
                    year=excluded.year,
                    month=excluded.month,
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
                    _status=excluded._status,
                    manga=excluded.manga,
                    notes=excluded.notes,
                    imprint=excluded.imprint,
                    genre=excluded.genre,
                    web=excluded.web
            """, (
                file_path,
                mtime,
                meta.get("title"),
                meta.get("series"),
                str(meta.get("issue")) if meta.get("issue") is not None else None,
                str(meta.get("volume")) if meta.get("volume") is not None else None,
                str(meta.get("year")) if meta.get("year") is not None else None,
                str(meta.get("month")) if meta.get("month") is not None else None,
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
                meta.get("_comicbox_status", "ok"),
                str(meta.get("manga")) if meta.get("manga") is not None else None,
                meta.get("notes"),
                meta.get("imprint"),
                meta.get("genre"),
                meta.get("web")
            ))
            self.conn.commit()

    def remove_comic(self, file_path: str):
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM comics WHERE file_path = ?", (file_path,))
            self.conn.commit()

    def clear_all(self):
        """Removes all entries from the comics table."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM comics")
            self.conn.commit()
            logger.info("Local library database cleared.")

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
            
    def get_comics_grid(self, sort_order: str, sort_direction: str) -> List[sqlite3.Row]:
        sort_dir = "ASC" if sort_direction == "asc" else "DESC"
        if sort_order == "pub_date":
            order = f"year {sort_dir}, title {sort_dir}"
        elif sort_order == "added_date":
            order = f"file_mtime {sort_dir}, title {sort_dir}"
        else: # alpha
            order = f"COALESCE(series, title, file_path) {sort_dir}"

        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(f"SELECT * FROM comics ORDER BY {order}")
            return cursor.fetchall()

    def get_comics_grouped(self, group_by: str, sort_order: str, sort_direction: str) -> Dict[str, List[sqlite3.Row]]:
        field_map = {"series": "series", "publisher": "publisher", "writer": "writer", "artist": "penciller"}
        field = field_map.get(group_by, "series")

        sort_dir = "ASC" if sort_direction == "asc" else "DESC"
        if sort_order == "pub_date":
            order = f"year {sort_dir}, title {sort_dir}"
        elif sort_order == "added_date":
            order = f"file_mtime {sort_dir}, title {sort_dir}"
        else:
            order = f"COALESCE(series, title, file_path) {sort_dir}"

        with self._lock:
            cursor = self.conn.cursor()

            if field == "series":
                # Primary sort inside group: Volume then Issue numerically, fallback to alpha
                full_order = f"{field} {sort_dir}, CAST(volume AS REAL) {sort_dir}, CAST(issue AS REAL) {sort_dir}, {order}"
            else:
                full_order = f"{field} {sort_dir}, {order}"

            cursor.execute(f"SELECT * FROM comics ORDER BY {full_order}")
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
