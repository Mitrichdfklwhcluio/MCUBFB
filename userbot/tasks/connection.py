"""Connection monitoring task."""

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telethon import TelegramClient

from ..utils import Colors, cprint


async def check_connection(client: "TelegramClient", enabled: bool = True) -> None:
    """
    Periodic connection check task.

    :param client: Telegram client instance.
    :param enabled: Whether task is enabled.
    """
    while True:
        await asyncio.sleep(60)

        if not enabled:
            break

        if not client.is_connected():
            cprint("🔍 Проверка соединения: отключено", Colors.YELLOW)
            from .healthcheck import safe_connect

            if not await safe_connect(client):
                cprint(
                    "❌ Проверка соединения: переподключение не удалось",
                    Colors.RED,
                )
            else:
                cprint("✅ Проверка соединения: восстановлено", Colors.GREEN)