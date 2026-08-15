import json
import os
import threading
from typing import Any

from utils.logger import logger

DEFAULTS: dict[str, Any] = {
    "auto_channel": None,
    "delete_time": 60,
    "slowdown": 0,
    "enabled": False,
}


class ConfigManager:

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self._lock = threading.Lock()
        self._data: dict[str, dict[str, Any]] = {}
        self._ensure_dir()
        self.load()

    def _ensure_dir(self) -> None:
        directory = os.path.dirname(self.file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

    def load(self) -> None:
        with self._lock:
            if not os.path.exists(self.file_path):
                self._data = {}
                self._save_locked()
                return
            try:
                with open(self.file_path, "r", encoding="utf-8") as fh:
                    loaded = json.load(fh)
                if isinstance(loaded, dict):
                    self._data = loaded
                else:
                    self._data = {}
            except (json.JSONDecodeError, OSError) as exc:
                logger.error("Failed to load config file: %s", exc)
                self._data = {}

    def _save_locked(self) -> None:
        try:
            with open(self.file_path, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=4)
        except OSError as exc:
            logger.error("Failed to save config file: %s", exc)

    def save(self) -> None:
        with self._lock:
            self._save_locked()

    def get_guild_config(self, guild_id: int) -> dict[str, Any]:
        key = str(guild_id)
        with self._lock:
            guild = self._data.get(key)
        if not guild:
            return dict(DEFAULTS)
        merged = dict(DEFAULTS)
        merged.update(guild)
        return merged

    def set_guild_config(self, guild_id: int, updates: dict[str, Any]) -> None:
        key = str(guild_id)
        with self._lock:
            guild = self._data.get(key)
            if not guild:
                guild = dict(DEFAULTS)
            else:
                base = dict(DEFAULTS)
                base.update(guild)
                guild = base
            guild.update(updates)
            self._data[key] = guild
            self._save_locked()

    def is_auto_enabled(self, guild_id: int) -> bool:
        return bool(self.get_guild_config(guild_id).get("enabled", False))

    def get_auto_channel(self, guild_id: int) -> int | None:
        return self.get_guild_config(guild_id).get("auto_channel")

    def get_delete_time(self, guild_id: int) -> int:
        return int(self.get_guild_config(guild_id).get("delete_time", 60))

    def get_slowdown(self, guild_id: int) -> int:
        return int(self.get_guild_config(guild_id).get("slowdown", 0))

    def all_configs(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return json.loads(json.dumps(self._data))


config_manager = ConfigManager("data/config.json")
