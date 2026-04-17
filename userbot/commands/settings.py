"""Settings commands: prefix, alias, lang, theme, 2fa, powersave, logs, rollback."""

import asyncio
import json
import os
import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telethon import TelegramClient
    from telethon.events import NewMessage

from ..config import get as config_get, set as config_set
from ..utils import Colors, cprint

#: Current command prefix
command_prefix: str = "."

#: Current aliases dict
aliases: dict = {}

#: Power save mode flag
power_save_mode: bool = False


async def prefix_handler(
    event: "NewMessage",
    prefix_global: str,
) -> None:
    """
    Handle .prefix command - change command prefix.

    :param event: Telethon event object.
    :param prefix_global: Global prefix variable to update.
    """
    new_prefix = event.text.split(None, 1)[1].strip() if " " in event.text else ""
    if len(new_prefix) != 1:
        await event.edit("❌ Префикс должен быть одним символом")
        return

    config_set("command_prefix", new_prefix)
    globals()["command_prefix"] = new_prefix

    await event.edit(f"✅ Префикс изменен на `{new_prefix}`")


async def alias_handler(
    event: "NewMessage",
    aliases_global: dict,
) -> None:
    """
    Handle .alias command - create command alias.

    :param event: Telethon event object.
    :param aliases_global: Global aliases dict to update.
    """
    args = event.text.split(None, 1)[1].strip() if " " in event.text else ""
    if "=" not in args:
        await event.edit(f"❌ Использование: `{command_prefix}alias алиас = команда`")
        return

    parts = args.split("=")
    if len(parts) != 2:
        await event.edit(f"❌ Использование: `{command_prefix}alias алиас = команда`")
        return

    alias = parts[0].strip()
    command = parts[1].strip()

    aliases_global[alias] = command
    config_set("aliases", aliases_global)
    globals()["aliases"] = aliases_global

    await event.edit(
        f"✅ Алиас создан: `{command_prefix}{alias}` → `{command_prefix}{command}`"
    )


async def lang_handler(event: "NewMessage") -> None:
    """
    Handle .lang command - change language.

    :param event: Telethon event object.
    """
    from ..utils.i18n import LANGS, LANGUAGE

    new_lang = event.text.split(None, 1)[1].strip() if " " in event.text else ""
    if new_lang in LANGS:
        config_set("language", new_lang)
        globals()["LANGUAGE"] = new_lang
        await event.edit(f"✅ Language changed to: {new_lang}")
    else:
        await event.edit(f"❌ Available: {', '.join(LANGS.keys())}")


async def theme_handler(event: "NewMessage") -> None:
    """
    Handle .theme command - change theme.

    :param event: Telethon event object.
    """
    from ..utils.theme import THEMES, THEME

    new_theme = event.text.split(None, 1)[1].strip() if " " in event.text else ""
    if new_theme in THEMES:
        config_set("theme", new_theme)
        globals()["THEME"] = new_theme
        await event.edit(f"✅ Тема изменена на: {new_theme}")
    else:
        await event.edit(f"❌ Доступны: {', '.join(THEMES.keys())}")


async def logs_handler(
    event: "NewMessage",
    client: "TelegramClient",
    logs_dir: str = "logs",
) -> None:
    """
    Handle .logs command - send logs to chat.

    :param event: Telethon event object.
    :param client: Telegram client instance.
    :param logs_dir: Logs directory path.
    """
    args = event.text.split(None, 1)[1].strip() if " " in event.text else ""
    target_chat = int(args) if args else event.chat_id

    if not os.path.exists(logs_dir):
        await event.edit("📝 Логи отсутствуют")
        return

    log_files = sorted([f for f in os.listdir(logs_dir) if f.endswith(".log")])
    if not log_files:
        await event.edit("📝 Логи отсутствуют")
        return

    latest_log = os.path.join(logs_dir, log_files[-1])
    await client.send_file(
        target_chat, latest_log, caption=f"📝 Логи за {log_files[-1][:-4]}"
    )
    await event.delete()


async def rollback_handler(event: "NewMessage", backup_file: str = "userbot_backup/__init__.py") -> None:
    """
    Handle .rollback command - rollback to previous version.

    :param event: Telethon event object.
    :param backup_file: Backup file path.
    """
    if not os.path.exists(backup_file):
        await event.edit("❌ Бэкап не найден")
        return

    await event.edit("🔄 Откат к предыдущей версии...")

    try:
        shutil.copy(backup_file, "userbot/__init__.py")

        await event.edit("✅ Откат завершен\nПерезагрузка...")
        await asyncio.sleep(1)
        import sys
        import os

        os.execl(sys.executable, sys.executable, *sys.argv)
    except Exception as e:
        await event.edit(f"❌ Ошибка отката: {str(e)}")


async def handler_2fa(event: "NewMessage") -> None:
    """
    Handle .2fa command - toggle two-factor authentication.

    :param event: Telethon event object.
    """
    current = config_get("2fa_enabled", False)
    config_set("2fa_enabled", not current)

    status = (
        "✅ включена (инлайн-подтверждение)"
        if not current
        else "❌ выключена"
    )
    await event.edit(
        f"🔐 Двухфакторная аутентификация {status}\n\n"
        f"Теперь опасные команды требуют подтверждения через кнопки."
    )


async def powersave_handler(event: "NewMessage") -> None:
    """
    Handle .powersave command - toggle power save mode.

    :param event: Telethon event object.
    """
    global power_save_mode

    current = config_get("power_save_mode", False)
    new_value = not current
    config_set("power_save_mode", new_value)
    power_save_mode = new_value

    status = "🔋 включен" if new_value else "⚡ выключен"
    features = (
        "\n• Логирование отключено\n• Healthcheck реже в 3 раза\n• Снижена нагрузка"
        if new_value
        else ""
    )
    await event.edit(f"Режим энергосбережения {status}{features}")


async def menu_handler(
    event: "NewMessage",
    client: "TelegramClient",
) -> None:
    """
    Handle .menu command - show interactive menu.

    :param event: Telethon event object.
    :param client: Telegram client instance.
    """
    from telethon import Button

    title = "🤖 **Mitrich UserBot - Меню**"

    buttons = [
        [
            Button.inline("📊 Инфо", b"info"),
            Button.inline("📦 Модули", b"modules"),
        ],
        [
            Button.inline("⚙️ Настройки", b"settings"),
            Button.inline("📝 Логи", b"logs"),
        ],
        [
            Button.inline("🔄 Обновить", b"update"),
            Button.inline("🔄 Перезагрузка", b"restart"),
        ],
    ]
    await event.edit(title, buttons=buttons)


async def confirm_handler(event: "NewMessage") -> None:
    """
    Handle .confirm command - confirm pending command.

    :param event: Telethon event object.
    """
    await event.edit("✅ Команда подтверждена. Выполните её снова.")