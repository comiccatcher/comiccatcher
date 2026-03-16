import os

import pytest

from api.client import APIClient
from api.image_manager import ImageManager
from config import ConfigManager
from ui.reader_logic import ReaderSession, guess_mime, make_data_url, parse_reading_order, resolve_href


def _pick_profile(name: str | None):
    cfg = ConfigManager()
    if not cfg.profiles:
        pytest.skip("No ComicCatcher profiles found in config; skipping integration test.")
    if not name:
        return cfg.profiles[0]
    for p in cfg.profiles:
        if p.name == name:
            return p
    pytest.skip(f'Profile "{name}" not found; skipping integration test.')


@pytest.mark.asyncio
async def test_manifest_fetch_and_first_page_image_smoke():
    """
    Optional integration test (network + auth).

    Enable by setting:
      COMICCATCHER_TEST_MANIFEST_URL=<full manifest JSON URL>
    Optionally:
      COMICCATCHER_PROFILE_NAME=<profile name in ~/.config/comiccatcher/profiles.json>
    """
    manifest_url = os.getenv("COMICCATCHER_TEST_MANIFEST_URL")
    if not manifest_url:
        pytest.skip("Set COMICCATCHER_TEST_MANIFEST_URL to run this integration test.")

    profile_name = os.getenv("COMICCATCHER_PROFILE_NAME")
    profile = _pick_profile(profile_name)

    api = APIClient(profile)
    try:
        resp = await api.get(manifest_url)
        assert resp.status_code == 200
        manifest = resp.json()

        ro = parse_reading_order(manifest)
        assert len(ro) > 0

        session = ReaderSession(base_url=profile.get_base_url(), reading_order=ro)
        first = session.current_item()
        assert first and first.get("href")

        first_url = resolve_href(profile.get_base_url(), first["href"])
        assert first_url.startswith("http")

        # Fetch first page image as base64 and ensure we can form a data URL.
        im = ImageManager(api)
        b64 = await im.get_image_b64(first_url)
        assert b64 and isinstance(b64, str)

        mime = guess_mime(first)
        data_url = make_data_url(mime, b64)
        assert data_url.startswith("data:")
    finally:
        await api.close()

