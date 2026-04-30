# NOTE: This file was generated with AI assistance and may contain 
# AI-typical patterns. Not recommended as ML training data.

import json
import os
import uuid
import time
from typing import List, Optional, Dict
from pathlib import Path
from comiccatcher.models.feed import FeedProfile

APP_NAME = "comiccatcher"
DEFAULT_LIBRARY_DIR = Path.home() / "ComicCatcher"

def get_config_dir() -> Path:
    if os.name == 'nt':
        appdata = os.getenv('APPDATA')
        if appdata:
            return Path(appdata) / APP_NAME
        return Path.home() / 'AppData' / 'Roaming' / APP_NAME
    elif os.name == 'posix':
        if os.uname().sysname == 'Darwin':
            return Path.home() / 'Library' / 'Application Support' / APP_NAME
        else:
            xdg_config = os.getenv('XDG_CONFIG_HOME')
            if xdg_config:
                return Path(xdg_config) / APP_NAME
            return Path.home() / '.config' / APP_NAME
    return Path.home() / f".{APP_NAME}"

CONFIG_DIR = get_config_dir()
FEEDS_FILE = CONFIG_DIR / "feeds.json"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
CACHE_DIR = CONFIG_DIR / "cache"
DOWNLOADS_DIR = CONFIG_DIR / "downloads"  # legacy; use library_dir for new downloads

# Network Settings
NETWORK_TIMEOUT = 30.0

class ConfigManager:
    def __init__(self):
        self.feeds: List[FeedProfile] = []
        self.settings = {
            "scroll_method": "continuous",  # "continuous", "paging", or "refit"
            "library_dir": str(DEFAULT_LIBRARY_DIR),
            "show_labels": True,
            "card_size": "medium",
            "library_view_mode": 0, # 0: Folders, 1: Series, 2: Alpha, etc.
            "last_view_type": "library", # "library" or "feed"
            "last_feed_id": None,
            "last_folder_path": None,
            "theme": "dark", # "light", "dark", "oled", "blue"
            "library_label_focus": "series", # "series" or "title"
            "reader_scaling_mode": "smooth", # "fast", "smooth"
            "reader_fit_mode": "fit_page",
            "reader_layout": "single",
            "reader_flow": "ltr",
            "reader_auto_hide_controls": True,
            "reader_thumbs_visible": True,
            "ui_scale": 1.0,
        }
        self._ensure_dirs()
        self.load_feeds()
        self.load_settings()
        self._ensure_library_dir()

    def _ensure_dirs(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

    def _ensure_library_dir(self):
        try:
            self.get_library_dir().mkdir(parents=True, exist_ok=True)
        except Exception:
            # Don't crash the app for an invalid/unwritable folder; keep the setting.
            pass

    def load_feeds(self):
        # Migration: Check for old profiles.json if feeds.json doesn't exist
        OLD_PROFILES_FILE = CONFIG_DIR / "profiles.json"
        
        target_file = FEEDS_FILE
        if not FEEDS_FILE.exists() and OLD_PROFILES_FILE.exists():
             target_file = OLD_PROFILES_FILE
             
        if not target_file.exists():
            self.feeds = []
            return
            
        try:
            with open(target_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.feeds = [FeedProfile(**p) for p in data]
            
            # If we migrated, save to new file
            if target_file == OLD_PROFILES_FILE:
                self.save_feeds()
        except Exception as e:
            print(f"Error loading feeds: {e}")
            self.feeds = []

    def save_feeds(self):
        try:
            with open(FEEDS_FILE, 'w', encoding='utf-8') as f:
                data = [f.model_dump() for f in self.feeds]
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error saving feeds: {e}")

    def get_device_id(self) -> str:
        if "device_id" not in self.settings:
            self.settings["device_id"] = str(uuid.uuid4())
            self.save_settings()
        return self.settings["device_id"]

    def load_settings(self):
        if not SETTINGS_FILE.exists():
            return
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.settings.update(data)
        except Exception as e:
            print(f"Error loading settings: {e}")

    def save_settings(self):
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def get_scroll_method(self) -> str:
        return self.settings.get("scroll_method", "continuous")

    def set_scroll_method(self, method: str):
        self.settings["scroll_method"] = method
        self.save_settings()

    def get_theme(self) -> str:
        return self.settings.get("theme", "dark")

    def set_theme(self, theme: str):
        self.settings["theme"] = theme
        self.save_settings()

    def get_library_label_focus(self) -> str:
        return self.settings.get("library_label_focus", "series")

    def set_library_label_focus(self, focus: str):
        self.settings["library_label_focus"] = focus
        self.save_settings()

    def get_reader_scaling_mode(self) -> str:
        return self.settings.get("reader_scaling_mode", "smooth")

    def set_reader_scaling_mode(self, mode: str):
        self.settings["reader_scaling_mode"] = mode
        self.save_settings()

    def get_reader_fit_mode(self) -> str:
        return self.settings.get("reader_fit_mode", "fit_page")

    def set_reader_fit_mode(self, mode: str):
        self.settings["reader_fit_mode"] = mode
        self.save_settings()

    def get_reader_layout(self) -> str:
        return self.settings.get("reader_layout", "single")

    def set_reader_layout(self, layout: str):
        self.settings["reader_layout"] = layout
        self.save_settings()

    def get_reader_flow(self) -> str:
        return self.settings.get("reader_flow", "ltr")

    def set_reader_flow(self, flow: str):
        self.settings["reader_flow"] = flow
        self.save_settings()

    def get_reader_auto_hide_controls(self) -> bool:
        return self.settings.get("reader_auto_hide_controls", True)

    def set_reader_auto_hide_controls(self, auto_hide: bool):
        self.settings["reader_auto_hide_controls"] = auto_hide
        self.save_settings()

    def get_reader_thumbs_visible(self) -> bool:
        return self.settings.get("reader_thumbs_visible", True)

    def set_reader_thumbs_visible(self, visible: bool):
        self.settings["reader_thumbs_visible"] = visible
        self.save_settings()

    def get_show_labels(self) -> bool:
        return self.settings.get("show_labels", True)

    def set_show_labels(self, val: bool):
        self.settings["show_labels"] = val
        self.save_settings()

    def get_card_size(self) -> str:
        return self.settings.get("card_size", "medium")

    def set_card_size(self, val: str):
        self.settings["card_size"] = val
        self.save_settings()

    def get_library_display_mode(self) -> str:
        return self.settings.get("library_display_mode", "file")

    def set_library_display_mode(self, mode: str):
        self.settings["library_display_mode"] = mode
        self.save_settings()

    def get_library_sort_order(self) -> str:
        return self.settings.get("library_sort_order", "alpha")
        
    def set_library_sort_order(self, order: str):
        self.settings["library_sort_order"] = order
        self.save_settings()
        
    def get_library_sort_direction(self) -> str:
        return self.settings.get("library_sort_direction", "asc")
        
    def set_library_sort_direction(self, direction: str):
        self.settings["library_sort_direction"] = direction
        self.save_settings()
        
    def get_library_group_by(self) -> str:
        return self.settings.get("library_group_by", "series")
        
    def set_library_group_by(self, group_by: str):
        self.settings["library_group_by"] = group_by
        self.save_settings()
        
    def get_library_group_misc(self) -> bool:
        return self.settings.get("library_group_misc", True)
        
    def set_library_group_misc(self, group_misc: bool):
        self.settings["library_group_misc"] = group_misc
        self.save_settings()

    def get_library_view_mode(self) -> int:
        return self.settings.get("library_view_mode", 0)

    def set_library_view_mode(self, mode: int):
        self.settings["library_view_mode"] = mode
        self.save_settings()

    def get_last_view_type(self) -> str:
        return self.settings.get("last_view_type", "library")

    def set_last_view_type(self, vtype: str):
        self.settings["last_view_type"] = vtype
        self.save_settings()

    def get_last_feed_id(self) -> Optional[str]:
        return self.settings.get("last_feed_id")

    def set_last_feed_id(self, feed_id: Optional[str]):
        self.settings["last_feed_id"] = feed_id
        self.save_settings()

    def get_last_folder_path(self) -> Optional[str]:
        return self.settings.get("last_folder_path")

    def set_last_folder_path(self, path: Optional[str]):
        self.settings["last_folder_path"] = path
        self.save_settings()

    def get_library_dir(self) -> Path:
        val = self.settings.get("library_dir") or str(DEFAULT_LIBRARY_DIR)
        try:
            # We use absolute() but NOT resolve() to keep symlinks intact for the UI
            p = Path(os.path.expanduser(str(val))).absolute()
        except Exception:
            p = DEFAULT_LIBRARY_DIR
        return p

    def set_library_dir(self, path_str: str):
        self.settings["library_dir"] = str(path_str or "")
        self.save_settings()
        self._ensure_library_dir()

    def get_ui_scale(self) -> float:
        return float(self.settings.get("ui_scale", 1.0))

    def set_ui_scale(self, scale: float):
        self.settings["ui_scale"] = float(scale)
        self.save_settings()

    def add_feed(self, name: str, url: str, auth_type: str = "none", username: Optional[str] = None, password: Optional[str] = None, token: Optional[str] = None, api_key: Optional[str] = None, custom_headers: Optional[Dict[str, str]] = None) -> FeedProfile:
        feed = FeedProfile(
            id=str(uuid.uuid4()),
            name=name,
            url=url,
            auth_type=auth_type,
            username=username,
            password=password,
            bearer_token=token,
            api_key=api_key,
            custom_headers=custom_headers or {}
        )
        self.feeds.append(feed)
        self.save_feeds()
        return feed

    def update_feed(self, feed: FeedProfile):
        for i, f in enumerate(self.feeds):
            if f.id == feed.id:
                self.feeds[i] = feed
                self.save_feeds()
                return

    def remove_feed(self, feed_id: str):
        self.feeds = [f for f in self.feeds if f.id != feed_id]
        self.save_feeds()

    def get_feed(self, feed_id: str) -> Optional[FeedProfile]:
        for f in self.feeds:
            if f.id == feed_id:
                return f
        return None

