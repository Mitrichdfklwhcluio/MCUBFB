"""Healthcheck task for monitoring bot status."""

import asyncio
import time
from typing import TYPE_CHECKING

import psutil

if TYPE_CHECKING:
    from telethon import TelegramClient

from ..utils import Colors, cprint, ensure_dir


async def healthcheck(
    client: "TelegramClient",
    interval: int = 30,
    power_save_mode: bool = False,
    healthcheck_file: str = "restart.tmp",
    logs_dir: str = "logs",
    log_command_func: callable = None,
) -> None:
    """
    Periodic healthcheck task to monitor bot status.

    :param client: Telegram client instance.
    :param interval: Check interval in minutes.
    :param power_save_mode: If True, check 3x less frequently.
    :param healthcheck_file: Path to restart file.
    :param logs_dir: Logs directory path.
    :param log_command_func: Function to log commands (optional).
    """
    from ..config import get

    ensure_dir(logs_dir)

    last_healthcheck = time.time()
    reconnect_attempts = 0

    while True:
        try:
            interval_seconds = (
                interval * 3 if power_save_mode else interval
            ) * 60
            await asyncio.sleep(interval_seconds)

            if shutdown_flag := False:  # Placeholder for shutdown check
                break

            if power_save_mode:
                last_healthcheck = time.time()
                continue

            if not client.is_connected():
                cprint("⚠️ Healthcheck: соединение потеряно", Colors.YELLOW)
                if not await safe_connect(client):
                    cprint(
                        "❌ Healthcheck: не удалось восстановить соединение",
                        Colors.RED,
                    )
                    continue

            current_time = time.time()

            process = psutil.Process()
            cpu = process.cpu_percent(interval=0.1)
            ram = process.memory_info().rss / 1024 / 1024

            if cpu > 80 or ram > 500:
                if log_command_func:
                    log_command_func(
                        f"HEALTHCHECK: High usage - CPU: {cpu}%, RAM: {ram}MB",
                        0,
                        0,
                        False,
                    )

            last_healthcheck = current_time
        except Exception as e:
            if log_command_func:
                log_command_func(f"HEALTHCHECK ERROR: {str(e)}", 0, 0, False)
            reconnect_attempts = 0
            await asyncio.sleep(30)


async def safe_connect(client: "TelegramClient") -> bool:
    """
    Safely connect to Telegram with retry logic.

    :param client: Telegram client instance.
    :return: True if connected successfully.
    """
    from ..config import get

    max_attempts = 5
    reconnect_attempts = 0
    reconnect_delay = 10

    while reconnect_attempts < max_attempts:
        try:
            if client.is_connected():
                return True

            await client.connect()
            if await client.is_user_authorized():
                cprint("✅ Переподключение успешно", Colors.GREEN)
                reconnect_attempts = 0
                return True

        except (ConnectionError, Exception) as e:
            reconnect_attempts += 1
            cprint(
                f"❌ Ошибка подключения ({reconnect_attempts}/{max_attempts}): {e}",
                Colors.RED,
            )

            if reconnect_attempts >= max_attempts:
                cprint("⚠️ Достигнут лимит попыток переподключения", Colors.YELLOW)
                return False

            wait_time = reconnect_delay * reconnect_attempts
            cprint(f"⏳ Повторная попытка через {wait_time} секунд...", Colors.YELLOW)
            await asyncio.sleep(wait_time)

    return False