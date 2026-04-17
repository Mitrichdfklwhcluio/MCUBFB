"""Configuration management."""

import json
import os
import sys
from typing import Any, Optional

#: Configuration file path
CONFIG_FILE: str = "config.json"

#: Default configuration values
DEFAULT_CONFIG: dict = {
    "api_id": 0,
    "api_hash": "",
    "phone": "",
    "command_prefix": ".",
    "aliases": {},
    "healthcheck_interval": 30,
    "developer_chat_id": None,
    "language": "ru",
    "theme": "default",
    "power_save_mode": False,
    "2fa_enabled": False,
    "db_version": 1,
}

#: Current config dictionary
config: dict = {}


def load_config() -> dict:
    """
    Load configuration from config.json.

    :return: Loaded configuration dictionary.
    :raises SystemExit: If config file doesn't exist or is invalid.
    """
    global config

    if not os.path.exists(CONFIG_FILE):
        print("Файл config.json не найден")
        print("Скопируйте config.example.json в config.json и заполните данные")
        sys.exit(1)

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    for key, value in DEFAULT_CONFIG.items():
        if key not in config:
            config[key] = value

    return config


def save_config() -> None:
    """
    Save configuration to config.json.
    """
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get(key: str, default: Any = None) -> Any:
    """
    Get config value by key.

    :param key: Configuration key.
    :param default: Default value if key not found.
    :return: Configuration value or default.
    """
    return config.get(key, default)


def set_value(key: str, value: Any) -> None:
    """
    Set config value and save.

    :param key: Configuration key.
    :param value: Value to set.
    """
    config[key] = value
    save_config()


def set(key: str, value: Any) -> None:
    """
    Set config value (alias for set_value).

    :param key: Configuration key.
    :param value: Value to set.
    """
    set_value(key, value)


def validate_credentials() -> tuple[int, str, str]:
    """
    Validate API credentials from config.

    :return: Tuple of (api_id, api_hash, phone).
    :raises SystemExit: If credentials are invalid.
    """
    global config

    try:
        api_id = int(config["api_id"])
        api_hash = str(config["api_hash"])
        phone = str(config["phone"])
    except (KeyError, ValueError) as e:
        print(f"Ошибка в config.json: {e}")
        print("Проверьте что api_id - это число, api_hash и phone - строки")
        sys.exit(1)

    if api_id == 0 or "YOUR" in api_hash or "YOUR" in phone:
        print("Заполните config.json своими данными")
        print("1. Получите API_ID и API_HASH на https://my.telegram.org")
        print("2. Укажите номер телефона в формате +13371337")
        sys.exit(1)

    return api_id, api_hash, phone


def migrate_data(db_version: int, target_version: int) -> bool:
    """
    Migrate config to new version if needed.

    :param db_version: Current database version.
    :param target_version: Target version to migrate to.
    :return: True if migration was performed.
    """
    global config

    if db_version < target_version:
        config["db_version"] = target_version
        save_config()
        return True
    return False