"""Main command handler dispatcher."""

import re
from typing import TYPE_CHECKING, Callable, Dict, List, Optional

from telethon import events

if TYPE_CHECKING:
    from telethon import TelegramClient

from ..config import get as config_get
from ..utils import Colors, cprint


#: Command handlers registry
handlers: Dict[str, Callable] = {}

#: Command prefix
command_prefix: str = "."

#: Aliases
aliases: Dict[str, str] = {}

#: Dangerous commands
DANGEROUS_COMMANDS: List[str] = ["update", "stop", "um", "rollback"]

#: Pending confirmations (global)
pending_confirmations: dict = {}


def register_handler(command: str, handler: Callable) -> None:
    """
    Register a command handler.

    :param command: Command name (without prefix).
    :param handler: Handler function.
    """
    handlers[command] = handler


async def send_inline(client: "TelegramClient", chat_id: int, query: str) -> bool:
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


def create_handler(
    client: "TelegramClient",
    pending_confirmations_global: dict,
) -> callable:
    """
    Create main command handler.

    :param client: Telegram client instance.
    :param pending_confirmations_global: Pending confirmations dict.
    :return: Handler function.
    """

    async def handler(event: events.NewMessage) -> None:
        """Main command handler."""
        global command_prefix, aliases

        text = event.text
        chat_id = event.chat_id
        sender_id = event.sender_id

        # Check prefix
        if not text.startswith(command_prefix):
            return

        # Extract command
        cmd = text[len(command_prefix):].split()[0] if " " in text else text[len(command_prefix):]

        # Resolve alias
        if cmd in aliases:
            text = command_prefix + aliases[cmd] + text[len(command_prefix) + len(cmd):]
            cmd = text[len(command_prefix):].split()[0] if " " in text else text[len(command_prefix):]

        # Import handlers here to avoid circular imports
        from ..commands.system import (
            ping_handler,
            info_handler,
            help_handler,
            restart_handler,
            update_handler,
            stop_handler,
        )
        from ..commands.modules import (
            im_handler,
            dlm_handler,
            dlml_handler,
            lm_handler,
            um_handler,
            unlm_handler,
        )
        from ..commands.settings import (
            prefix_handler,
            alias_handler,
            lang_handler,
            theme_handler,
            logs_handler,
            rollback_handler,
            powersave_handler,
            menu_handler,
            confirm_handler,
            handler_2fa,
            aliases as aliases_global,
        )
        from ..commands.utility import t_handler, ibot_handler

        # Handle confirm
        if cmd == "confirm":
            confirm_key = f"{chat_id}_{sender_id}"
            if confirm_key in pending_confirmations_global:
                saved_command = pending_confirmations_global[confirm_key]
                del pending_confirmations_global[confirm_key]
                event.text = saved_command
                await handler(event)
                return
            else:
                await event.edit("❌ Нет команд, ожидающих подтверждения")
                return

        # Handle 2FA for dangerous commands
        if cmd in DANGEROUS_COMMANDS and config_get("2fa_enabled", False):
            confirm_key = f"{chat_id}_{sender_id}"
            if confirm_key not in pending_confirmations_global:
                pending_confirmations_global[confirm_key] = text
                await event.delete()

                bot_username = config_get("inline_bot_username")
                if bot_username:
                    try:
                        query = f"2fa_{confirm_key}_{text}"
                        bot = await client.inline_query(bot_username, query)
                        await bot[0].click(chat_id)
                    except Exception:
                        await client.send_message(
                            chat_id,
                            f"⚠️ Требуется подтверждение: `{text}`\n\n"
                            f"Напишите `{command_prefix}confirm` для подтверждения",
                        )
                else:
                    await client.send_message(
                        chat_id,
                        f"⚠️ Требуется подтверждение: `{text}`\n\n"
                        f"Напишите `{command_prefix}confirm` для подтверждения",
                    )
                return
            else:
                await event.edit("⚠️ Эта команда уже ожидает подтверждения")
                return

        # Dispatch commands
        try:
            if text == f"{command_prefix}ping":
                await ping_handler(event)

            elif text == f"{command_prefix}info":
                await info_handler(event)

            elif text == f"{command_prefix}help":
                await help_handler(event)

            elif text == f"{command_prefix}restart":
                await restart_handler(event)

            elif text == f"{command_prefix}update":
                await update_handler(event)

            elif text == f"{command_prefix}stop":
                await stop_handler(event)

            elif text == f"{command_prefix}dlml" or text.startswith(f"{command_prefix}dlml "):
                await dlml_handler(event, client)

            elif text.startswith(f"{command_prefix}dlm "):
                await dlm_handler(event, client)

            elif text == f"{command_prefix}im":
                await im_handler(event, client)

            elif text == f"{command_prefix}lm":
                await lm_handler(event)

            elif text.startswith(f"{command_prefix}um "):
                await um_handler(event)

            elif text.startswith(f"{command_prefix}unlm "):
                await unlm_handler(event, client)

            elif text.startswith(f"{command_prefix}prefix "):
                await prefix_handler(event, command_prefix)

            elif text.startswith(f"{command_prefix}alias "):
                await alias_handler(event, aliases_global)

            elif text == f"{command_prefix}menu":
                await menu_handler(event, client)

            elif text.startswith(f"{command_prefix}lang "):
                await lang_handler(event)

            elif text.startswith(f"{command_prefix}theme "):
                await theme_handler(event)

            elif text.startswith(f"{command_prefix}logs"):
                await logs_handler(event, client)

            elif text == f"{command_prefix}confirm":
                await confirm_handler(event)

            elif text == f"{command_prefix}2fa":
                await handler_2fa(event)

            elif text == f"{command_prefix}rollback":
                await rollback_handler(event)

            elif text == f"{command_prefix}powersave":
                await powersave_handler(event)

            elif text.startswith(f"{command_prefix}ibot "):
                await ibot_handler(event, client)

            elif text.startswith(f"{command_prefix}t "):
                await t_handler(event)

        except Exception as e:
            await event.edit(f"❌ Ошибка: {str(e)}")

    return handler


def setup_handlers(
    client: "TelegramClient",
    pending_confirmations_global: dict,
) -> None:
    """
    Setup all command handlers.

    :param client: Telegram client instance.
    :param pending_confirmations_global: Pending confirmations dict.
    """
    handler = create_handler(client, pending_confirmations_global)
    client.add_event_handler(handler, events.NewMessage(outgoing=True))