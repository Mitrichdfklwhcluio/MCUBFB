"""
UserBot - Telegram UserBot framework.

This is the main entry point for the UserBot.
Run with: python -m userbot
"""

import asyncio
import os
import sys
import time
from typing import Optional

from telethon import TelegramClient

from .config import (
    CONFIG_FILE,
    DEFAULT_CONFIG,
    config,
    get as config_get,
    load_config,
    save_config,
    validate_credentials,
)
from .core.handler import create_handler, setup_handlers, pending_confirmations
from .core.loader import load_all_modules
from .inline.bot import check_inline_bot, run_inline_bot
from .tasks import healthcheck as healthcheck_task
from .tasks import connection as connection_task
from .utils import (
    Colors,
    cprint,
    ensure_dir,
    format_uptime,
)


#: Bot version
VERSION: str = "1.0.0"

#: Database version
DB_VERSION: int = 1

#: Directories
MODULES_DIR: str = "modules"
IMG_DIR: str = "img"
LOGS_DIR: str = "logs"

#: Files
RESTART_FILE: str = "restart.tmp"
BACKUP_FILE: str = "userbot.py.backup"
ERROR_FILE: str = "crash.tmp"

#: Global state
start_time: float = time.time()
shutdown_flag: bool = False
command_prefix: str = "."
aliases: dict = {}


async def migrate_data() -> None:
    """Migrate config data if needed."""
    global config

    db_version = config.get("db_version", 0)
    if db_version < DB_VERSION:
        cprint(f"🔄 Миграция данных с версии {db_version} до {DB_VERSION}...", Colors.YELLOW)
        config["db_version"] = DB_VERSION
        save_config()
        cprint("✅ Миграция завершена", Colors.GREEN)


async def report_crash(
    client: TelegramClient,
    error_msg: str,
    error_file: str = ERROR_FILE,
) -> None:
    """
    Report crash to developer.

    :param client: Telegram client instance.
    :param error_msg: Error message.
    :param error_file: Error file path.
    """
    developer_chat_id = config_get("developer_chat_id")
    if developer_chat_id:
        try:
            me = await client.get_me()
            report = f"🚨 **Crash Report**\n\n"
            report += f"👤 User: {me.first_name} ({me.id})\n"
            report += f"💻 Version: {VERSION}\n"
            report += f"⏰ Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            report += f"❌ Error:\n```\n{error_msg[:500]}\n```"
            await client.send_message(developer_chat_id, report)
        except Exception:
            pass


async def load_and_run_modules(
    client: TelegramClient,
    send_inline_func: Optional[callable] = None,
) -> int:
    """
    Load all modules and return count.

    :param client: Telegram client instance.
    :param send_inline_func: Send inline function.
    :return: Number of loaded modules.
    """
    ensure_dir(MODULES_DIR)

    loaded_count = await load_all_modules(client, send_inline_func, MODULES_DIR)
    return loaded_count


async def send_inline(
    client: TelegramClient,
    chat_id: int,
    query: str,
) -> bool:
    """
    Send inline query via inline bot.

    :param client: Telegram client instance.
    :param chat_id: Target chat ID.
    :param query: Inline query text.
    :return: True if successful.
    """
    bot_username = config_get("inline_bot_username")
    if not bot_username:
        return False

    try:
        results = await client.inline_query(bot_username, query)
        if results:
            await results[0].click(chat_id)
            return True
    except Exception as e:
        print(f"Inline Error: {e}")
    return False


async def main() -> None:
    """Main entry point."""
    global command_prefix, aliases, shutdown_flag

    # Load configuration
    load_config()
    api_id, api_hash, phone = validate_credentials()

    # Set global state from config
    command_prefix = config_get("command_prefix", ".")
    aliases = config_get("aliases", {})

    # Ensure directories
    ensure_dir(LOGS_DIR)
    ensure_dir(MODULES_DIR)
    ensure_dir(IMG_DIR)

    # Create client
    proxy = config.get("proxy")
    client = TelegramClient("user_session", api_id, api_hash, proxy=proxy)

    # Migrate data if needed
    await migrate_data()

    # Start client
    try:
        await client.start(phone=phone)

        if not await healthcheck_task.safe_connect(client):
            cprint("❌ Не удалось подключиться к Telegram", Colors.RED)
            sys.exit(1)

        cprint("✅ MCUB запущен", Colors.GREEN)

        # Setup inline bot
        await check_inline_bot(client)

        # Setup command handlers
        from .core.handler import setup_handlers

        pending_conf = {}
        setup_handlers(client, pending_conf)

        # Start background tasks
        from .tasks import healthcheck, connection

        healthcheck_interval = config_get("healthcheck_interval", 30)
        power_save_mode = config_get("power_save_mode", False)
        enable_2fa = config_get("2fa_enabled", False)

        asyncio.create_task(
            healthcheck.healthcheck(
                client,
                interval=healthcheck_interval,
                power_save_mode=power_save_mode,
                logs_dir=LOGS_DIR,
            )
        )
        asyncio.create_task(connection.check_connection(client))
        asyncio.create_task(
            run_inline_bot(
                client, api_id, api_hash, pending_conf, {}
            )
        )
        cprint(
            f"💚 Healthcheck запущен (каждые {healthcheck_interval} мин)",
            Colors.GREEN,
        )

    except Exception as e:
        print(f"❌ Ошибка авторизации: {e}")
        print("Проверьте API_ID, API_HASH и PHONE в config.json")
        await report_crash(client, str(e))
        sys.exit(1)

    # Load modules
    await load_and_run_modules(client, send_inline)

    # Handle restart file
    if os.path.exists(RESTART_FILE):
        with open(RESTART_FILE, "r") as f:
            chat_id, msg_id, start_ts = f.read().split(",")
        os.remove(RESTART_FILE)
        restart_time = round((time.time() - float(start_ts)) * 1000)
        if client.is_connected():
            await client.edit_message(
                int(chat_id), int(msg_id), f"MCUB перезагружен ✅\nВремя: {restart_time}ms"
            )
        else:
            cprint(
                f"⚠️ Не удалось отправить сообщение о перезагрузке: нет соединения",
                Colors.YELLOW,
            )

    # Main loop
    while True:
        try:
            if shutdown_flag:
                break
            if not client.is_connected():
                if not await healthcheck_task.safe_connect(client):
                    cprint(
                        "⚠️ Основное соединение потеряно, ожидание...", Colors.YELLOW
                    )
                    await asyncio.sleep(30)
                    continue

            await client.run_until_disconnected()

        except (ConnectionError, Exception) as e:
            cprint(f"⚠️ Разрыв соединения: {e}", Colors.YELLOW)
            if not await healthcheck_task.safe_connect(client):
                cprint("❌ Критический разрыв соединения", Colors.RED)
                await asyncio.sleep(60)
        except Exception as e:
            cprint(f"❌ Неожиданная ошибка в main: {e}", Colors.RED)
            await asyncio.sleep(30)


def run() -> None:
    """Run the bot."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⛔ Остановка юзербота...")
        sys.exit(0)


if __name__ == "__main__":
    run()