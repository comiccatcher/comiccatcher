import asyncio
from typing import Optional
from urllib.parse import urljoin

from PyQt6.QtGui import QPixmap

from logger import get_logger
from api.image_manager import ImageManager
from api.progression import ProgressionSync
from models.opds import Publication
from ui.base_reader import BaseReaderView

logger = get_logger("ui.reader")


class ReaderView(BaseReaderView):
    """
    OPDS streaming reader.

    Fetches pages via ImageManager (3-tier cache), syncs reading progression
    via the Readium Locator API.
    """

    def __init__(self, config_manager, on_exit, image_manager: ImageManager = None):
        super().__init__(on_exit)
        self.config_manager = config_manager
        self.api_client    = None
        self.image_manager = image_manager
        self.progression_sync: Optional[ProgressionSync] = None
        self.progression_url: Optional[str] = None

        self._current_pub: Optional[Publication] = None
        self._manifest_url: Optional[str] = None
        self._reading_order: list = []
        self._load_token = 0
        self._prefetch_set: set[str] = set()

        # Wire thumbnail loader so the slider can pull pages on demand
        self.thumb_slider.set_thumb_loader(self._load_page_pixmap)

    # ------------------------------------------------------------------ #
    # BaseReaderView interface                                             #
    # ------------------------------------------------------------------ #

    async def _load_page_pixmap(self, idx: int) -> Optional[QPixmap]:
        if not self._reading_order or idx >= len(self._reading_order):
            return None
        item = self._reading_order[idx]
        href = item.get("href", "")
        base = self.api_client.profile.get_base_url()
        url  = href if href.startswith("http") else urljoin(base, href)

        # Populate disk cache then load via path (avoids base64 decode overhead)
        await self.image_manager.get_image_b64(url)
        path = self.image_manager._get_cache_path(url)
        if path.exists():
            pm = QPixmap(str(path))
            return pm if not pm.isNull() else None
        return None

    async def _do_prefetch(self, idx: int):
        if not self._reading_order or idx >= len(self._reading_order):
            return
        item = self._reading_order[idx]
        href = item.get("href", "")
        base = self.api_client.profile.get_base_url()
        url  = href if href.startswith("http") else urljoin(base, href)
        if url in self._prefetch_set:
            return
        self._prefetch_set.add(url)
        try:
            await self.image_manager.get_image_b64(url)
        except Exception:
            pass
        finally:
            self._prefetch_set.discard(url)

    def _on_page_changed(self, idx: int):
        if not self.progression_url or not self._reading_order or self._total == 0:
            return
        item = self._reading_order[idx]
        href = item.get("href", "")
        pct  = 1.0 if idx == self._total - 1 else idx / self._total
        asyncio.create_task(self.progression_sync.update_progression(
            self.progression_url,
            fraction=pct,
            title=item.get("title", f"Page {idx + 1}"),
            href=href,
            position=idx + 1,
            content_type=item.get("type", "image/jpeg"),
        ))

    # ------------------------------------------------------------------ #
    # Loading                                                              #
    # ------------------------------------------------------------------ #

    def load_manifest(self, pub: Publication, manifest_url: str, image_manager: ImageManager):
        self._load_token += 1
        self._current_pub  = pub
        self._manifest_url = manifest_url
        self._reading_order = []
        self._index = 0
        self._prefetch_set.clear()
        self.image_manager    = image_manager
        self.progression_sync = ProgressionSync(
            self.api_client, self.config_manager.get_device_id()
        )
        self.progression_url = self._discover_progression_url(pub.links)
        asyncio.create_task(self._fetch_and_load(self._load_token))

    def _discover_progression_url(self, links) -> Optional[str]:
        _PROG_RELS = {
            "http://opds-spec.org/rel/progression",
            "http://readium.org/rel/progression",
            "http://librarysimplified.org/terms/rel/state",
            "http://www.cantook.com/api/progression",
        }
        for link in (links or []):
            rel  = getattr(link, "rel", None) or (link.get("rel") if isinstance(link, dict) else None)
            rels = [rel] if isinstance(rel, str) else (rel or [])
            if any(r in _PROG_RELS for r in rels):
                href = getattr(link, "href", None) or (link.get("href") if isinstance(link, dict) else None)
                if href:
                    return urljoin(self.api_client.profile.get_base_url(), href)
        return None

    async def _fetch_and_load(self, token: int):
        try:
            if self._manifest_url:
                resp = await self.api_client.get(self._manifest_url)
                resp.raise_for_status()
                data = resp.json()
                if "readingOrder" in data:
                    self._reading_order = data["readingOrder"]
                # Progression link may live in the manifest itself
                prog = self._discover_progression_url(data.get("links", []))
                if prog:
                    self.progression_url = prog
            elif self._current_pub.readingOrder:
                self._reading_order = [
                    item.model_dump() for item in self._current_pub.readingOrder
                ]

            if token != self._load_token:
                return
            if not self._reading_order:
                logger.error("No pages found in manifest")
                return

            self._setup_reader(self._current_pub.metadata.title, len(self._reading_order))

            # Restore reading position from server progression
            if self.progression_url:
                prog_data = await self.progression_sync.get_progression(self.progression_url)
                if prog_data:
                    loc = prog_data.get("locator", {}).get("locations", {})
                    pct = loc.get("progression") or prog_data.get("progression")
                    pos = loc.get("position")
                    if pos is not None and pos > 0:
                        self._index = pos - 1
                    elif pct is not None:
                        self._index = int(pct * len(self._reading_order))
                    self._index = max(0, min(self._index, len(self._reading_order) - 1))

            await self._show_page()

        except Exception as e:
            logger.error(f"Error loading manifest: {e}")
