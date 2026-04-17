"""System commands: ping, info, help, restart, update, stop."""

import asyncio
import os
import re
import shutil
import sys
import time
from typing import TYPE_CHECKING, Optional

import aiohttp
import psutil

if TYPE_CHECKING:
    from telethon import TelegramClient
    from telethon.events import NewMessage

from ..config import get as config_get
from ..utils import (
    Colors,
    cprint,
    format_uptime,
    get_version_from_code,
    progress_bar,
)

#: Bot version
VERSION: str = "1.0.0"

#: Database version
DB_VERSION: int = 1

#: Restart file path
RESTART_FILE: str = "restart.tmp"

#: Backup file path
BACKUP_FILE: str = "userbot.py.backup"

#: Update repo URL
UPDATE_REPO: str = "https://raw.githubusercontent.com/Mitrichdfklwhcluio/MCUBFB/main/"

#: Current command prefix
command_prefix: str = "."

#: Start time (set on initialization)
start_time: float = time.time()

#: Power save mode flag
power_save_mode: bool = False


async def ping_handler(event: "NewMessage") -> None:
    """
    Handle .ping command - check latency.

    :param event: Telethon event object.
    """
    start = time.time()
    msg = await event.edit("Pong!")
    end = time.time()
    await msg.edit(f"Pong! {round((end - start) * 1000)}ms")


async def info_handler(event: "NewMessage") -> None:
    """
    Handle .info command - show bot info.

    :param event: Telethon event object.
    """
    await event.delete()

    me = await event.client.get_me()
    owner_name = me.first_name

    # Check latest version
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{UPDATE_REPO}version.txt",
                timeout=aiohttp.ClientTimeout(total=3),
            ) as resp:
                if resp.status == 200:
                    latest_version = (await resp.text()).strip()
                    version_status = (
                        "✅ Актуальная"
                        if VERSION == latest_version
                        else f"⚠️ Доступна {latest_version}"
                    )
                else:
                    version_status = "❓ Не удалось проверить"
    except Exception:
        version_status = "❓ Не удалось проверить"

    uptime_seconds = int(time.time() - start_time)
    uptime = format_uptime(uptime_seconds)

    process = psutil.Process()
    cpu_percent = process.cpu_percent(interval=0.1)
    ram_mb = process.memory_info().rss / 1024 / 1024
    power_status = "🔋 Вкл" if power_save_mode else "⚡ Выкл"

    # Get first image from img directory
    img_path = None
    if os.path.exists("img"):
        images = [
            f
            for f in os.listdir("img")
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif"))
        ]
        if images:
            img_path = os.path.join("img", images[0])

    caption = f"""**Mitrich UserBot**
👤 Владелец: {owner_name}
💻 Версия: {VERSION}
{version_status}
⏱ Аптайм: {uptime}
📊 CPU: {cpu_percent:.1f}%
💾 RAM: {ram_mb:.1f} MB
🔋 Энергосбережение: {power_status}
🟢 Статус: Working"""

    if img_path:
        await event.client.send_file(event.chat_id, img_path, caption=caption)
    else:
        await event.client.send_message(event.chat_id, caption)


async def help_handler(event: "NewMessage") -> None:
    """
    Handle .help command - show help text.

    :param event: Telethon event object.
    """
    help_text = f"""📚 **Mitrich UserBot - Команды**

**Основные:**
{command_prefix}ping - проверка задержки
{command_prefix}info - информация о юзерботе
{command_prefix}help - список команд
{command_prefix}update - обновление с GitHub
{command_prefix}restart - перезагрузка
{command_prefix}stop - остановка юзербота

**Модули:**
{command_prefix}im - установить модуль (ответ на .py файл)
{command_prefix}dlm [название] - скачать модуль из каталога
{command_prefix}dlml - каталог доступных модулей
{command_prefix}lm - список модулей
{command_prefix}um [название] - удалить модуль
{command_prefix}unlm [название] - выгрузить модуль в чат

**Настройки:**
{command_prefix}prefix [символ] - изменить префикс команд
{command_prefix}alias [алиас] = [команда] - создать алиас
{command_prefix}logs [chat_id] - отправить логи в чат
{command_prefix}t [команда] - выполнить команду в терминале
{command_prefix}rollback - откатиться к предыдущей версии
{command_prefix}2fa - вкл/выкл 2FA для опасных команд
{command_prefix}powersave - режим энергосбережения
{command_prefix}ibot [текст | кнопка:url] - отправить через inline-бота"""

    await event.edit(help_text)


async def restart_handler(event: "NewMessage") -> None:
    """
    Handle .restart command - restart the bot.

    :param event: Telethon event object.
    """
    await event.edit("Перезагрузка...")

    with open(RESTART_FILE, "w") as f:
        f.write(f"{event.chat_id},{event.id},{time.time()}")

    os.execl(sys.executable, sys.executable, *sys.argv)


async def update_handler(event: "NewMessage") -> None:
    """
    Handle .update command - update from GitHub.

    :param event: Telethon event object.
    """
    import shutil

    await event.edit("🔄 Проверка обновлений...")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{UPDATE_REPO}userbot/__init__.py") as resp:
                if resp.status == 200:
                    new_code = await resp.text()

                    new_version = get_version_from_code(new_code)
                    if new_version and new_version != VERSION:
                        await event.edit(f"📥 Обновление до {new_version}...")

                        # Backup current
                        shutil.copy("userbot/__init__.py", BACKUP_FILE)

                        # Update
                        with open("userbot/__init__.py", "w", encoding="utf-8") as f:
                            f.write(new_code)

                        await event.edit(
                            f"✅ Обновлено до {new_version}\n📦 Бэкап создан\nПерезагрузка..."
                        )
                        await asyncio.sleep(1)
                        os.execl(sys.executable, sys.executable, "-m", "userbot")
                    else:
                        await event.edit(f"✅ У вас актуальная версия {VERSION}")
                else:
                    await event.edit("❌ Не удалось получить обновление")
    except Exception as e:
        await event.edit(f"❌ Ошибка: {str(e)}")


async def stop_handler(event: "NewMessage", shutdown_callback: callable = None) -> None:
    """
    Handle .stop command - stop the bot.

    :param event: Telethon event object.
    :param shutdown_callback: Function to call on shutdown.
    """
    if shutdown_callback:
        shutdown_callback()

    await event.edit("⛔ Остановка юзербота...")
    await asyncio.sleep(1)
    await event.client.disconnect()