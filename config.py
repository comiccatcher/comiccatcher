import json
import os
import uuid
from typing import List, Optional
from pathlib import Path
from models.server import ServerProfile

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
PROFILES_FILE = CONFIG_DIR / "profiles.json"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
CACHE_DIR = CONFIG_DIR / "cache"
DOWNLOADS_DIR = CONFIG_DIR / "downloads"  # legacy; use library_dir for new downloads

class ConfigManager:
    def __init__(self):
        self.profiles: List[ServerProfile] = []
        self.settings = {
            "scroll_method": "infinite",  # "infinite", "paging", or "viewport"
            # Local library folder (downloaded / imported comics).
            "library_dir": str(DEFAULT_LIBRARY_DIR),
        }
        self._ensure_dirs()
        self.load_profiles()
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

    def load_profiles(self):
        if not PROFILES_FILE.exists():
            self.profiles = []
            return
        try:
            with open(PROFILES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.profiles = [ServerProfile(**p) for p in data]
        except Exception as e:
            print(f"Error loading profiles: {e}")
            self.profiles = []

    def save_profiles(self):
        try:
            with open(PROFILES_FILE, 'w', encoding='utf-8') as f:
                data = [p.model_dump() for p in self.profiles]
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error saving profiles: {e}")

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
        return self.settings.get("scroll_method", "infinite")

    def set_scroll_method(self, method: str):
        self.settings["scroll_method"] = method
        self.save_settings()

    def get_library_dir(self) -> Path:
        val = self.settings.get("library_dir") or str(DEFAULT_LIBRARY_DIR)
        try:
            p = Path(os.path.expanduser(str(val))).resolve()
        except Exception:
            p = DEFAULT_LIBRARY_DIR
        return p

    def set_library_dir(self, path_str: str):
        self.settings["library_dir"] = str(path_str or "")
        self.save_settings()
        self._ensure_library_dir()

    def add_profile(self, name: str, url: str, username: Optional[str] = None, password: Optional[str] = None, token: Optional[str] = None) -> ServerProfile:
        profile = ServerProfile(
            id=str(uuid.uuid4()),
            name=name,
            url=url,
            username=username,
            password=password,
            bearer_token=token
        )
        self.profiles.append(profile)
        self.save_profiles()
        return profile

    def update_profile(self, profile: ServerProfile):
        for i, p in enumerate(self.profiles):
            if p.id == profile.id:
                self.profiles[i] = profile
                self.save_profiles()
                return

    def remove_profile(self, profile_id: str):
        self.profiles = [p for p in self.profiles if p.id != profile_id]
        self.save_profiles()

    def get_profile(self, profile_id: str) -> Optional[ServerProfile]:
        for p in self.profiles:
            if p.id == profile_id:
                return p
        return None
