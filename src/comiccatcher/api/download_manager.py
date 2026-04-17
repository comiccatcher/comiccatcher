# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

import asyncio
import os
import re
import hashlib
from pathlib import Path
from typing import Dict, Optional, Callable, List
from urllib.parse import unquote_plus, urlsplit
import httpx
from comiccatcher.api.client import APIClient
from comiccatcher.logger import get_logger

logger = get_logger("api.download_manager")

_FILENAME_MAX = 180


def _iterative_unquote_plus(s: str, max_rounds: int = 3) -> str:
    """
    Decode strings that may be encoded multiple times (e.g. %2523 -> %23 -> #).
    Also treats '+' as space (like browsers do for form-style encodings).
    """
    out = s or ""
    for _ in range(max_rounds):
        new = unquote_plus(out)
        if new == out:
            break
        out = new
    return out


def _filename_from_content_disposition(cd: str) -> Optional[str]:
    """
    Parse Content-Disposition and return a decoded filename if present.

    Supports:
    - filename="x.cbz"
    - filename*=UTF-8''x%20y.cbz
    """
    if not cd:
        return None

    # Prefer RFC 5987 filename*
    m = re.search(r"filename\*\s*=\s*([^;]+)", cd, flags=re.IGNORECASE)
    if m:
        raw = m.group(1).strip().strip("\"'")
        if "''" in raw:
            _, _, rest = raw.partition("''")
            return _iterative_unquote_plus(rest)
        return _iterative_unquote_plus(raw)

    m = re.search(r"filename\s*=\s*([^;]+)", cd, flags=re.IGNORECASE)
    if m:
        raw = m.group(1).strip().strip("\"'")
        return _iterative_unquote_plus(raw)
    return None


def _filename_from_url(url: str) -> Optional[str]:
    try:
        leaf = Path(urlsplit(url).path).name
        if not leaf:
            return None
        return _iterative_unquote_plus(leaf)
    except Exception:
        return None


def _sanitize_filename(name: str, mime_type: Optional[str] = None) -> str:
    """
    Keep names user-friendly while being safe across OSes.
    Rely on the provided mime_type to determine the correct extension.
    """
    if not name:
        name = "download"

    name = Path(str(name)).name
    # Remove existing extension to re-apply correctly based on MIME
    stem = Path(name).stem
    name = re.sub(r"\s+", " ", stem).strip()

    allowed = set(" ._-#()[]")
    cleaned = "".join(c for c in name if c.isalnum() or c in allowed).strip(" .")
    if not cleaned:
        cleaned = "download"

    # Map MIME to extension
    MIME_MAP = {
        "application/vnd.comicbook+zip": ".cbz",
        "application/x-cbz": ".cbz",
        "application/zip": ".cbz",
        "application/vnd.comicbook-rar": ".cbr",
        "application/x-cbr": ".cbr",
        "application/x-rar": ".cbr",
        "application/x-rar-compressed": ".cbr",
        "application/x-cb7": ".cb7",
        "application/x-7z-compressed": ".cb7",
        "application/x-cbt": ".cbt",
        "application/x-tar": ".cbt",
        "application/pdf": ".pdf",
        "application/epub+zip": ".epub"
    }
    
    ext = ".cbz" # Default fallback
    if mime_type:
        ext = MIME_MAP.get(mime_type.lower().split(";")[0].strip(), ".cbz")
    
    # Check if stem already has the correct extension (e.g. from Content-Disposition)
    if cleaned.lower().endswith(ext):
        final_name = cleaned
    else:
        final_name = f"{cleaned}{ext}"

    if len(final_name) > _FILENAME_MAX:
        final_name = final_name[: _FILENAME_MAX - len(ext)] + ext

    return final_name


def _collision_free_path(dir_path: Path, filename: str) -> Path:
    p = dir_path / filename
    if not p.exists():
        return p
    stem = p.stem
    suffix = p.suffix
    n = 2
    while True:
        candidate = dir_path / f"{stem} ({n}){suffix}"
        if not candidate.exists():
            return candidate
        n += 1

class DownloadTask:
    def __init__(self, book_id: str, title: str, url: str):
        self.book_id = book_id
        self.title = title
        self.url = url
        self.progress = 0.0 # 0 to 1.0
        self.status = "Pending" # Pending, Downloading, Completed, Failed, Cancelled
        self.error = None
        self.file_path = None
        self._active_task: Optional[asyncio.Task] = None

class DownloadManager:
    def __init__(self, api_client: APIClient, download_dir: Optional[Path] = None):
        self.api_client = api_client
        # Default to the app's library folder ("~/ComicCatcher" unless configured).
        # UI layer can also override by passing download_dir explicitly.
        if download_dir is None:
            self.download_dir = Path.home() / "ComicCatcher"
        else:
            self.download_dir = Path(download_dir)
        self.tasks: Dict[str, DownloadTask] = {}
        self._callbacks: List[Callable] = []
        self._queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None

    def _ensure_worker(self):
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._queue_worker())

    async def _queue_worker(self):
        while True:
            task = await self._queue.get()
            try:
                await self._download_worker(task)
            except Exception as e:
                logger.error(f"Error in download worker: {e}")
            finally:
                self._queue.task_done()

    def set_callback(self, callback: Callable):
        """Deprecated: use add_callback instead."""
        self.add_callback(callback)

    def add_callback(self, callback: Callable):
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def remove_callback(self, callback: Callable):
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    async def start_download(self, book_id: str, title: str, url: str):
        # Ensure we have a unique ID for the task list
        if not book_id:
            # Fallback to a hash of the URL if identifier is missing
            import hashlib
            book_id = hashlib.md5(url.encode()).hexdigest()

        if book_id in self.tasks and self.tasks[book_id].status in ("Completed", "Downloading", "Pending"):
            logger.info(f"Book {title} already queued or downloading.")
            return

        task = DownloadTask(book_id, title, url)
        task.status = "Pending"
        self.tasks[book_id] = task
        self._notify()
        
        await self._queue.put(task)
        self._ensure_worker()

    def cancel_download(self, book_id: str):
        if book_id in self.tasks:
            task = self.tasks[book_id]
            # Since we are using a sequential queue, we need to know if the task is currently downloading
            if task.status == "Downloading":
                if hasattr(task, "_active_task") and task._active_task and not task._active_task.done():
                    task._active_task.cancel()
            elif task.status == "Pending":
                # Removing from queue is hard in asyncio.Queue, we just mark it as cancelled
                pass

            task.status = "Cancelled"
            self._notify()

    async def _download_worker(self, task: DownloadTask):
        if task.status == "Cancelled":
            return
            
        task.status = "Downloading"
        task._active_task = asyncio.current_task()
        self._notify()
        
        try:
            self.download_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            # If CWD isn't usable for some reason, fall back to current CWD anyway.
            self.download_dir = Path.cwd()

        # Provisional path shown in UI until response headers arrive.
        task.file_path = _collision_free_path(self.download_dir, _sanitize_filename(task.title))
        
        try:
            async with self.api_client.client.stream("GET", task.url) as response:
                if response.status_code != 200:
                    raise Exception(f"Server returned status {response.status_code}")

                # Choose filename like browsers do: Content-Disposition first, then URL leaf, then title.
                cd = response.headers.get("Content-Disposition") or response.headers.get("content-disposition") or ""
                mime = response.headers.get("Content-Type") or response.headers.get("content-type")
                
                suggested = _filename_from_content_disposition(cd) or _filename_from_url(task.url) or task.title
                task.file_path = _collision_free_path(self.download_dir, _sanitize_filename(suggested, mime))
                self._notify()
                
                total_bytes = int(response.headers.get("Content-Length", 0))
                downloaded_bytes = 0
                
                with open(task.file_path, "wb") as f:
                    async for chunk in response.aiter_bytes():
                        f.write(chunk)
                        downloaded_bytes += len(chunk)
                        if total_bytes > 0:
                            task.progress = downloaded_bytes / total_bytes
                            self._notify()
                        
                        # yield control to event loop to allow cancellation
                        await asyncio.sleep(0)
                
            task.status = "Completed"
            task.progress = 1.0
            logger.info(f"Download completed: {task.title} -> {task.file_path}")
        except asyncio.CancelledError:
            task.status = "Cancelled"
            logger.info(f"Download cancelled: {task.title}")
            if task.file_path and task.file_path.exists():
                try: os.remove(task.file_path)
                except: pass
        except Exception as e:
            task.status = "Failed"
            task.error = str(e)
            logger.error(f"Download failed for {task.title}: {e}")
            if task.file_path and task.file_path.exists():
                try: os.remove(task.file_path)
                except: pass
        
        self._notify()

    def _notify(self):
        for cb in self._callbacks:
            try:
                cb()
            except Exception as e:
                logger.error(f"Error calling download callback: {e}")

    def get_task(self, book_id: str) -> Optional[DownloadTask]:
        return self.tasks.get(book_id)

    def remove_task(self, book_id: str):
        if book_id in self.tasks:
            task = self.tasks[book_id]
            if task.status == "Downloading":
                self.cancel_download(book_id)
            del self.tasks[book_id]
            self._notify()
