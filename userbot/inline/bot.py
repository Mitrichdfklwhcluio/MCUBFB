"""Inline bot for userbot."""

import asyncio
import json
import re
from typing import TYPE_CHECKING, Optional

from telethon import Button, events
from telethon.errors import RPCError

if TYPE_CHECKING:
    from telethon import TelegramClient

from ..config import get as config_get

#: Catalog cache (global)
catalog_cache: dict = {}

#: Pending confirmations (global)
pending_confirmations: dict = {}

#: Inline bot client (global)
_inline_client: Optional["TelegramClient"] = None


async def check_inline_bot(client: "TelegramClient") -> bool:
    """
    Check if inline bot is configured, create if not.

    :param client: Main Telegram client instance.
    :return: True if inline bot is available.
    """
    bot_token = config_get("inline_bot_token")

    if bot_token:
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://api.telegram.org/bot{bot_token}/getMe"
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("ok"):
                            bot_username = data["result"]["username"]
                            from ..utils import Colors, cprint

                            cprint(f"✅ Inline-бот активен: @{bot_username}", Colors.GREEN)
                            return True
        except Exception:
            pass

    from ..utils import Colors, cprint

    cprint("🤖 Создание inline-бота...", Colors.YELLOW)
    try:
        me = await client.get_me()
        bot_username = f"MCUB_{str(me.id)[-6:]}_{str(int(asyncio.get_event_loop().time()))[-4:]}_bot"

        botfather = await client.get_entity("BotFather")

        await client.send_message(botfather, "/newbot")
        await asyncio.sleep(1)

        await client.send_message(botfather, "MCUBinline")
        await asyncio.sleep(1)

        await client.send_message(botfather, bot_username)
        await asyncio.sleep(2)

        messages = await client.get_messages(botfather, limit=1)
        if messages and "token" in messages[0].text.lower():
            token_match = re.search(r"(\d+:[A-Za-z0-9_-]+)", messages[0].text)
            if token_match:
                bot_token = token_match.group(1)
                from ..config import set as config_set

                config_set("inline_bot_token", bot_token)
                config_set("inline_bot_username", bot_username)

                await client.send_message(botfather, "/setinline")
                await asyncio.sleep(1)
                await client.send_message(botfather, f"@{bot_username}")
                await asyncio.sleep(1)
                await client.send_message(botfather, "inline")

                cprint(f"✅ Inline-бот создан: @{bot_username}", Colors.GREEN)
                return True

        cprint("❌ Не удалось создать бота", Colors.RED)
    except Exception as e:
        cprint(f"❌ Ошибка создания бота: {e}", Colors.RED)

    return False


async def run_inline_bot(
    main_client: "TelegramClient",
    api_id: int,
    api_hash: str,
    pending_confirmations_global: dict,
    catalog_cache_global: dict,
) -> None:
    """
    Run inline bot callback handler.

    :param main_client: Main Telegram client instance.
    :param api_id: API ID.
    :param api_hash: API hash.
    :param pending_confirmations_global: Pending confirmations dict.
    :param catalog_cache_global: Catalog cache dict.
    """
    global pending_confirmations, catalog_cache, _inline_client

    pending_confirmations = pending_confirmations_global
    catalog_cache = catalog_cache_global

    bot_token = config_get("inline_bot_token")
    if not bot_token:
        return

    try:
        from telethon import TelegramClient as BotClient

        bot = BotClient("inline_bot", api_id, api_hash)
        await bot.start(bot_token=bot_token)
        _inline_client = bot

        @bot.on(events.InlineQuery)
        async def inline_handler(event: events.InlineQuery) -> None:
            """Handle inline queries."""
            query = event.text or ""
            builder = None

            try:
                builder = _handle_inline_query(event, query)
            except Exception as e:
                print(f"Inline handler error: {e}")
                builder = event.builder.article("Error", text=f"⚠️ Error")

            if builder:
                try:
                    await event.answer([builder])
                except Exception as e:
                    print(f"Inline answer error: {e}")

        @bot.on(events.CallbackQuery)
        async def bot_callback_handler(event: events.CallbackQuery) -> None:
            """Handle callback queries."""
            await _handle_callback_query(event, main_client)

        await bot.run_until_disconnected()
    except Exception:
        pass


async def _handle_inline_query(event: events.InlineQuery, query: str):
    """Process inline query and return article."""
    if query.startswith("2fa_"):
        return _handle_2fa_query(event, query)
    elif query.startswith("catalog_"):
        return _handle_catalog_query(event, query)
    elif "|" in query:
        return _handle_message_with_buttons(event, query)
    else:
        text = query.strip() if query else "Empty"
        return event.builder.article("Message", text=text, parse_mode="html")


async def _handle_2fa_query(event: events.InlineQuery, query: str):
    """Handle 2FA confirmation query."""
    parts = query.split("_", 3)
    if len(parts) >= 4:
        command = parts[3]
        text = f"⚠️ **Требуется подтверждение**\n\nКоманда: `{command}`\n\nВы действительно хотите выполнить?"
        buttons = [
            [
                Button.inline("✅ Подтвердить", b"confirm_yes"),
                Button.inline("❌ Отменить", b"confirm_no"),
            ]
        ]
        return event.builder.article("2FA", text=text, buttons=buttons)
    return event.builder.article("Error", text="❌ Ошибка подтверждения")


async def _handle_catalog_query(event: events.InlineQuery, query: str):
    """Handle catalog page query."""
    try:
        page = int(query.split("_")[1])
    except (ValueError, IndexError):
        page = 1

    if not catalog_cache:
        return event.builder.article("Error", text="❌ Каталог не загружен. Используйте .dlml")

    modules_list = list(catalog_cache.items())
    per_page = 5
    total_pages = max(1, (len(modules_list) + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_modules = modules_list[start_idx:end_idx]

    msg = f"📚 <b>Каталог модулей</b> (Стр. {page}/{total_pages})\n\n"
    for module_name, info in page_modules:
        msg += f"• <b>{module_name}</b>\n"
        msg += f"  {info.get('description', 'Описание отсутствует')}\n"
    msg += '\nИспользуйте: <code>.dlm название</code>'

    buttons = []
    nav_buttons = []
    if page > 1:
        nav_buttons.append(Button.inline("⬅️ Назад", f"dlml_{page-1}".encode()))
    if page < total_pages:
        nav_buttons.append(Button.inline("➡️ Вперёд", f"dlml_{page+1}".encode()))
    if nav_buttons:
        buttons.append(nav_buttons)

    return event.builder.article(
        "Catalog", text=msg, buttons=buttons if buttons else None, parse_mode="html"
    )


async def _handle_message_with_buttons(event: events.InlineQuery, query: str):
    """Handle message with custom buttons."""
    parts = query.split("|")
    text = parts[0].strip() if parts else ""
    buttons = []

    for btn_data in parts[1:]:
        btn_data = btn_data.strip()
        if not btn_data or ":" not in btn_data:
            continue
        btn_parts = btn_data.split(":", 1)
        url = btn_parts[1].strip()
        if url.startswith(("http://", "https://", "t.me/", "tg://")):
            buttons.append([Button.url(btn_parts[0].strip(), url)])

    if not text:
        return event.builder.article("Error", text="⚠️ Empty message")

    return event.builder.article(
        "Message", text=text, buttons=buttons if buttons else None, parse_mode="html"
    )


async def _handle_callback_query(event: events.CallbackQuery, main_client: "TelegramClient") -> None:
    """Handle callback query."""
    sender = await event.get_sender()
    chat_id = event.chat_id

    me = await main_client.get_me()
    if sender.id != me.id:
        await event.answer("❌ Эта кнопка не для вас", alert=True)
        return

    if event.data == b"confirm_yes":
        confirm_key = f"{chat_id}_{sender.id}"
        if confirm_key in pending_confirmations:
            saved_command = pending_confirmations[confirm_key]
            del pending_confirmations[confirm_key]
            await event.answer("✅ Подтверждено")
            await event.edit(f"✅ **Команда подтверждена**\n\nВыполняю: `{saved_command}`")
            await main_client.send_message(chat_id, saved_command)
        else:
            await event.answer("❌ Команда не найдена")

    elif event.data == b"confirm_no":
        confirm_key = f"{chat_id}_{sender.id}"
        if confirm_key in pending_confirmations:
            del pending_confirmations[confirm_key]
            await event.answer("❌ Отменено")
            await event.edit("❌ Команда отменена")
        else:
            await event.answer("❌ Нечего отменять")

    elif event.data.startswith(b"dlml_"):
        try:
            page = int(event.data.decode().split("_")[1])
        except (ValueError, IndexError):
            page = 1
        await event.answer()

        if not catalog_cache:
            await event.edit("❌ Каталог не загружен")
            return

        modules_list = list(catalog_cache.items())
        per_page = 5
        total_pages = max(1, (len(modules_list) + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))

        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        page_modules = modules_list[start_idx:end_idx]

        msg = f"📚 <b>Каталог модулей</b> (Стр. {page}/{total_pages})\n\n"
        for module_name, info in page_modules:
            msg += f"• <b>{module_name}</b>\n"
            msg += f"  {info.get('description', 'Описание отсутствует')}\n"
        msg += '\nИспользуйте: <code>.dlm название</code>'

        buttons = []
        nav_buttons = []
        if page > 1:
            nav_buttons.append(Button.inline("⬅️ Назад", f"dlml_{page-1}".encode()))
        if page < total_pages:
            nav_buttons.append(Button.inline("➡️ Вперёд", f"dlml_{page+1}".encode()))
        if nav_buttons:
            buttons.append(nav_buttons)

        await event.edit(
            msg, buttons=buttons if buttons else None, parse_mode="html"
        )