"""Module management commands: im, dlm, dlml, lm, um, unlm."""

import asyncio
import json
import os
import re
import subprocess
import sys
from typing import TYPE_CHECKING

import aiohttp

if TYPE_CHECKING:
    from telethon import TelegramClient
    from telethon.events import NewMessage

from ..config import get as config_get
from ..core.loader import (
    get_loaded_modules,
    get_module_commands,
    load_module_from_code,
    load_module_from_file,
    unload_module,
)
from ..utils import Colors, cprint, progress_bar

#: Modules directory
MODULES_DIR: str = "modules"

#: Modules catalog repo
MODULES_REPO: str = (
    "https://raw.githubusercontent.com/Mitrichdfklwhcluio/MCUBFB/main/modules_catalog"
)

#: Catalog cache
catalog_cache: dict = {}


async def im_handler(
    event: "NewMessage",
    client: "TelegramClient",
    modules_dir: str = MODULES_DIR,
) -> None:
    """
    Handle .im command - install module from reply.

    :param event: Telethon event object.
    :param client: Telegram client instance.
    :param modules_dir: Modules directory path.
    """
    if not event.is_reply:
        await event.edit("❌ Ответьте на .py файл")
        return

    reply = await event.get_reply_message()
    if not reply.document or not reply.document.attributes[0].file_name.endswith(
        ".py"
    ):
        await event.edit("❌ Это не .py файл")
        return

    file_name = reply.document.attributes[0].file_name
    module_name = file_name[:-3]
    is_update = module_name in get_loaded_modules()

    await event.edit(f'📥 {"Обновление" if is_update else "Загрузка"} модуля...')

    if not os.path.exists(modules_dir):
        os.makedirs(modules_dir)

    file_path = os.path.join(modules_dir, file_name)
    await reply.download_media(file_path)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()

        if "from .. import" in code or "import loader" in code:
            await event.edit(
                "Модуль не совместим. Используйте модули с register(client)"
            )
            os.remove(file_path)
            return

        success = await load_module_from_file(
            client, file_path, send_inline=None, modules_dir=modules_dir
        )
        status = "🔄 обновлен" if is_update else "установлен"
        await event.edit(f"✅ Модуль {file_name} {status}")
    except Exception as e:
        await event.edit(f"❌ Ошибка: {str(e)}")
        if os.path.exists(file_path):
            os.remove(file_path)


async def dlm_handler(
    event: "NewMessage",
    client: "TelegramClient",
    modules_dir: str = MODULES_DIR,
) -> None:
    """
    Handle .dlm command - download module from catalog.

    :param event: Telethon event object.
    :param client: Telegram client instance.
    :param modules_dir: Modules directory path.
    """
    module_name = event.text.split(None, 1)[1].strip() if " " in event.text else ""
    is_update = module_name in get_loaded_modules()
    msg = await event.edit(
        f'📥 {"Обновление" if is_update else "Загрузка"} {module_name}...'
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{MODULES_REPO}/{module_name}.py") as resp:
                if resp.status == 200:
                    if not os.path.exists(modules_dir):
                        os.makedirs(modules_dir)

                    code = await resp.text()
                    file_path = os.path.join(modules_dir, f"{module_name}.py")

                    if is_update and module_name in sys.modules:
                        del sys.modules[module_name]

                    await msg.edit(f"📥 {progress_bar(1, 3)} Сохранение...")
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(code)

                    await msg.edit(f"📦 {progress_bar(2, 3)} Установка зависимостей...")
                    reqs = re.findall(r"# requires: (.+)", code)
                    if reqs:
                        for req in reqs[0].split(","):
                            subprocess.run(
                                [sys.executable, "-m", "pip", "install", req.strip()],
                                capture_output=True,
                            )

                    await msg.edit(f"⚙️ {progress_bar(3, 3)} Загрузка модуля...")

                    success = await load_module_from_code(
                        client, code, module_name, send_inline=None, modules_dir=modules_dir
                    )
                    if success:
                        status = "🔄 обновлен" if is_update else "установлен"
                        await msg.edit(f"✅ Модуль {module_name} {status}")
                    else:
                        await event.edit(f"❌ Модуль не имеет register(client)")
                        os.remove(file_path)
                else:
                    await event.edit(f"❌ Модуль {module_name} не найден в каталоге")
    except Exception as e:
        await event.edit(f"❌ Ошибка: {str(e)}")


async def dlml_handler(
    event: "NewMessage",
    client: "TelegramClient",
    catalog_url: str = MODULES_REPO,
) -> None:
    """
    Handle .dlml command - show modules catalog.

    :param event: Telethon event object.
    :param client: Telegram client instance.
    :param catalog_url: Catalog URL.
    """
    page = 1
    if " " in event.text:
        try:
            page = int(event.text.split()[1])
        except ValueError:
            page = 1

    bot_username = config_get("inline_bot_username")
    if not bot_username:
        await event.edit("❌ Inline-бот не настроен")
        return

    await event.delete()

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{catalog_url}/catalog.json") as resp:
                if resp.status == 200:
                    text_data = await resp.text()
                    global catalog_cache
                    catalog_cache = json.loads(text_data)

                    query = f"catalog_{page}"
                    results = await client.inline_query(bot_username, query)

                    if results:
                        await results[0].click(event.chat_id)
                    else:
                        await client.send_message(
                            event.chat_id, "❌ Ошибка инлайн-бота"
                        )
                else:
                    await client.send_message(
                        event.chat_id, "❌ Каталог не найден"
                    )
    except Exception as e:
        await client.send_message(event.chat_id, f"❌ Ошибка: {str(e)}")


async def lm_handler(
    event: "NewMessage",
    modules_dir: str = MODULES_DIR,
) -> None:
    """
    Handle .lm command - list loaded modules.

    :param event: Telethon event object.
    :param modules_dir: Modules directory path.
    """
    modules = get_loaded_modules()
    if not modules:
        await event.edit("📦 Модули не загружены")
        return

    msg = "📦 **Загруженные модули:**\n\n"
    for name, module in modules.items():
        msg += f"• **{name}**\n"
        if os.path.exists(os.path.join(modules_dir, f"{name}.py")):
            commands = get_module_commands(name, modules_dir)
            if commands:
                msg += f"  Команды: {', '.join([f'.{cmd}' for cmd in commands])}\n"
        msg += "\n"

    await event.edit(msg)


async def um_handler(
    event: "NewMessage",
    modules_dir: str = MODULES_DIR,
) -> None:
    """
    Handle .um command - unload module.

    :param event: Telethon event object.
    :param modules_dir: Modules directory path.
    """
    module_name = event.text.split(None, 1)[1].strip() if " " in event.text else ""
    modules = get_loaded_modules()

    if module_name not in modules:
        await event.edit(f"❌ Модуль {module_name} не найден")
        return

    await unload_module(module_name, modules_dir)
    await event.edit(
        f"🗑️ Модуль {module_name} удален\n\n⚠️ Перезагрузите юзербот для полного удаления"
    )


async def unlm_handler(
    event: "NewMessage",
    client: "TelegramClient",
    modules_dir: str = MODULES_DIR,
) -> None:
    """
    Handle .unlm command - upload module to chat.

    :param event: Telethon event object.
    :param client: Telegram client instance.
    :param modules_dir: Modules directory path.
    """
    module_name = event.text.split(None, 1)[1].strip() if " " in event.text else ""
    modules = get_loaded_modules()

    if module_name not in modules:
        await event.edit(f"❌ Модуль {module_name} не найден")
        return

    file_path = os.path.join(modules_dir, f"{module_name}.py")
    if not os.path.exists(file_path):
        await event.edit(f"❌ Файл модуля {module_name}.py не найден")
        return

    await event.edit(f"📤 Отправка модуля {module_name}...")
    await client.send_file(
        event.chat_id, file_path, caption=f"📦 Модуль: {module_name}.py"
    )
    await event.delete()