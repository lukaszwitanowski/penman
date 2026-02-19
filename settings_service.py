from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

SETTINGS_FILE_NAME = "settings.json"
SETTINGS_VERSION = 1
APP_DIR_NAME = "Penman"


def _resolve_settings_dir() -> Path:
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / APP_DIR_NAME
        return Path.home() / "AppData" / "Roaming" / APP_DIR_NAME

    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home) / APP_DIR_NAME.lower()
    return Path.home() / ".config" / APP_DIR_NAME.lower()


def get_settings_path() -> Path:
    return _resolve_settings_dir() / SETTINGS_FILE_NAME


def load_app_settings(defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = dict(defaults or {})
    settings_path = get_settings_path()
    if not settings_path.is_file():
        return result

    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return result

    if not isinstance(payload, dict):
        return result

    raw_settings = payload.get("settings")
    if isinstance(raw_settings, dict):
        for key, value in raw_settings.items():
            result[key] = value
        return result

    for key, value in payload.items():
        if key in {"version", "updated_at"}:
            continue
        result[key] = value
    return result


def save_app_settings(settings: dict[str, Any]) -> bool:
    settings_path = get_settings_path()
    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": SETTINGS_VERSION,
            "settings": settings,
        }
        settings_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except OSError:
        return False
