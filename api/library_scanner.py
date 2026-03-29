import asyncio
import os
from pathlib import Path
from typing import Callable, List, Optional, Set

from api.local_db import LocalLibraryDB
from ui.local_comicbox import read_comicbox_dict_and_cover, flatten_comicbox
from logger import get_logger

logger = get_logger("api.library_scanner")

COMIC_EXTS = {".cbz", ".cbr", ".cb7", ".pdf"}

class LibraryScanner:
    def __init__(self, db: LocalLibraryDB, library_dir: Path, on_cover: Optional[Callable] = None):
        self.db = db
        self.library_dir = library_dir
        self.is_scanning = False
        self._cancel_flag = False
        self.on_progress: Callable[[int, int, str], None] = lambda curr, total, msg: None
        self.on_finished: Callable[[], None] = lambda: None
        self.on_cover = on_cover  # Optional[Callable[[Path, bytes], None]] — sync, called in thread
        
    def cancel(self):
        self._cancel_flag = True

    async def scan(self) -> bool:
        if self.is_scanning:
            return False
            
        self.is_scanning = True
        self._cancel_flag = False
        has_changes = False
        
        try:
            logger.debug(f"Starting library scan in {self.library_dir}")
            
            # 1. Get current DB state in one go
            db_mtimes = await asyncio.to_thread(self.db.get_all_comics_mtimes)
            
            # 2. Collect all comic files
            all_files: List[Path] = []
            
            def _collect_files(directory: Path):
                try:
                    for p in directory.iterdir():
                        if p.name.startswith("."):
                            continue
                        if p.is_dir():
                            _collect_files(p)
                        elif p.suffix.lower() in COMIC_EXTS:
                            all_files.append(p)
                except Exception as e:
                    logger.error(f"Error reading directory {directory}: {e}")
            
            self.on_progress(0, 0, "Discovering files...")
            await asyncio.to_thread(_collect_files, self.library_dir)
            
            total_files = len(all_files)
            processed = 0
            
            # 3. Process each file
            current_paths: Set[str] = set()
            to_update: List[Path] = []
            
            for file_path in all_files:
                path_str = str(file_path.absolute())
                current_paths.add(path_str)
                
                try:
                    mtime = file_path.stat().st_mtime
                    db_mtime = db_mtimes.get(path_str)
                    
                    if db_mtime is None or db_mtime < mtime:
                        to_update.append(file_path)
                except Exception as e:
                    logger.error(f"Error stat-ing {file_path}: {e}")

            if not to_update:
                logger.debug("No files changed, skipping metadata update.")
            else:
                has_changes = True
                # Process updates in smaller concurrent batches to avoid overloading
                batch_size = 5
                for i in range(0, len(to_update), batch_size):
                    if self._cancel_flag: break
                    batch = to_update[i:i+batch_size]
                    
                    async def process_file(fp: Path):
                        nonlocal processed
                        try:
                            mtime = fp.stat().st_mtime
                            raw_meta, cover_bytes = await asyncio.to_thread(read_comicbox_dict_and_cover, fp)
                            flat_meta = flatten_comicbox(raw_meta)
                            await asyncio.to_thread(self.db.upsert_comic, str(fp.absolute()), mtime, flat_meta)
                            if cover_bytes and self.on_cover:
                                await asyncio.to_thread(self.on_cover, fp, cover_bytes)
                        except Exception as e:
                            logger.error(f"Error processing {fp}: {e}")
                        processed += 1
                        self.on_progress(processed, total_files, f"Updated {processed}/{total_files}...")

                    await asyncio.gather(*(process_file(fp) for fp in batch))
            
            if not self._cancel_flag:
                # Always cleanup missing files
                self.on_progress(total_files, total_files, "")
                removed_count = await asyncio.to_thread(self.db.remove_missing_comics, list(current_paths))
                if removed_count > 0:
                    has_changes = True
                
            logger.debug(f"Library scan finished. Changes: {has_changes}")
            return has_changes
            
        except Exception as e:
            logger.error(f"Scan failed: {e}")
            return False
        finally:
            self.is_scanning = False
            self.on_finished(has_changes)
