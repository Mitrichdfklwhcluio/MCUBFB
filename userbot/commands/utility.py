"""Utility commands: t, ibot."""

import asyncio
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telethon import TelegramClient
    from telethon.events import NewMessage

from ..config import get as config_get


async def t_handler(event: "NewMessage") -> None:
    """
    Handle .t command - execute terminal command.

    :param event: Telethon event object.
    """
    command = event.text.split(None, 1)[1].strip() if " " in event.text else ""
    if not command:
        await event.edit("❌ Укажите команду")
        return

    await event.edit(f"💻 Выполнение: `{command}`")

    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        output = stdout.decode("utf-8") if stdout else ""
        error = stderr.decode("utf-8") if stderr else ""

        result = ""
        if output:
            result += f"📝 **Вывод:**\n```\n{output[:3000]}\n```\n"
        if error:
            result += f"❌ **Ошибка:**\n```\n{error[:3000]}\n```\n"

        if not result:
            result = "✅ Команда выполнена без вывода"

        result = f"💻 **Terminal:** `{command}`\n\n{result}"
        await event.edit(result)
    except Exception as e:
        await event.edit(f"❌ Ошибка: {str(e)}")


async def ibot_handler(
    event: "NewMessage",
    client: "TelegramClient",
) -> None:
    """
    Handle .ibot command - send via inline bot.

    :param event: Telethon event object.
    :param client: Telegram client instance.
    """
    bot_username = config_get("inline_bot_username")
    if not bot_username:
        await event.edit("❌ Inline-бот не настроен. Перезапустите юзербот")
        return

    await event.delete()

    args = event.text.split(None, 1)[1].strip() if " " in event.text else ""

    try:
        results = await client.inline_query(bot_username, args)

        if results:
            await results[0].click(event.chat_id)
        else:
            await client.send_message(
                event.chat_id, "❌ Инлайн-бот не вернул результатов"
            )

    except Exception as e:
        await client.send_message(event.chat_id, f"❌ Ошибка инлайна: {e}")