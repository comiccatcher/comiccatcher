from pathlib import Path


def test_library_dir_default_and_set(monkeypatch, tmp_path):
    import config as cfg

    # Isolate config side-effects to a temp folder by patching module globals used by ConfigManager.
    patched_config_dir = tmp_path / "comiccatcher_cfg"
    monkeypatch.setattr(cfg, "CONFIG_DIR", patched_config_dir)
    monkeypatch.setattr(cfg, "PROFILES_FILE", patched_config_dir / "profiles.json")
    monkeypatch.setattr(cfg, "SETTINGS_FILE", patched_config_dir / "settings.json")
    monkeypatch.setattr(cfg, "CACHE_DIR", patched_config_dir / "cache")
    monkeypatch.setattr(cfg, "DOWNLOADS_DIR", patched_config_dir / "downloads")

    cm = cfg.ConfigManager()
    assert cm.get_library_dir() == (Path.home() / "ComicCatcher").resolve()

    cm.set_library_dir("~/MyComics")
    assert cm.get_library_dir() == (Path.home() / "MyComics").resolve()

