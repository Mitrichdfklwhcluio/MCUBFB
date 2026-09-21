"""Helper utilities."""


import os
import time
import shlex
from typing import Optional

from telethon.tl.types import Message
from telethon.events import NewMessage

from ..config import get

def get_prefix() -> str:
    return get("command_prefix", ".")

def args(text: Message | NewMessage | str) -> list[str]:

    message = text if isinstance(text, str) else getattr(text, "text", '')
    
    if not message.startswith(get_prefix()):
        return []
    try:
        parts = shlex.split(message[len(get_prefix()):])
    except ValueError:
        parts = message[len(prefix):].split()
    return parts[1:] if len(parts) > 1 else []

def progress_bar(current: int, total: int, width: int = 10) -> str:
    """
    Generate a text progress bar.

    :param current: Current progress value.
    :param total: Total value.
    :param width: Width of the bar in characters.
    :return: Formatted progress bar string.
    """
    percent = current / total
    filled = int(width * percent)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {int(percent * 100)}%"


def format_uptime(seconds: int) -> str:
    """
    Format uptime seconds to human-readable string.

    :param seconds: Uptime in seconds.
    :return: Formatted string (e.g., "1ч 23м 45с").
    """
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours}ч {minutes}м {secs}с"


def log_command(
    command: str,
    chat_id: int,
    user_id: int,
    success: bool = True,
    logs_dir: str = "logs",
    enabled: bool = True,
) -> None:
    """
    Log command execution to file.

    :param command: Command text.
    :param chat_id: Chat ID.
    :param user_id: User ID.
    :param success: Whether command succeeded.
    :param logs_dir: Logs directory path.
    :param enabled: Whether logging is enabled.
    """
    if not enabled:
        return

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    log_file = os.path.join(logs_dir, f"{time.strftime('%Y-%m-%d')}.log")
    status = "SUCCESS" if success else "ERROR"

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(
            f"[{timestamp}] [{status}] Chat: {chat_id} | User: {user_id} | Command: {command}\n"
        )


def ensure_dir(path: str) -> None:
    """
    Ensure directory exists, create if not.

    :param path: Directory path.
    """
    if not os.path.exists(path):
        os.makedirs(path)


def get_version_from_code(code: str) -> Optional[str]:
    """
    Extract VERSION from source code.

    :param code: Source code string.
    :return: Version string or None if not found.
    """
    import re

    match = re.search(r"""VERSION\s*=\s*['"]([^'"]+)['"]""", code)
    return match.group(1) if match else None