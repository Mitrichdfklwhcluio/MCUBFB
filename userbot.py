import asyncio
import time
import sys
import os
import importlib.util
import re
import psutil
import aiohttp
import json
import subprocess
from telethon import TelegramClient, events, Button

class Colors:
    RESET = '\033[0m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    PURPLE = '\033[95m'
    CYAN = '\033[96m'

def cprint(text, color=''):
    print(f'{color}{text}{Colors.RESET}')

async def send_inline(client, chat_id, query):
    """
    Функция для вызова инлайн-бота из любого места (включая модули).
    """
    bot_username = config.get('inline_bot_username')
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

VERSION = '1.0.0'
DB_VERSION = 1
RESTART_FILE = 'restart.tmp'
MODULES_DIR = 'modules'
IMG_DIR = 'img'
LOGS_DIR = 'logs'
CONFIG_FILE = 'config.json'
BACKUP_FILE = 'userbot.py.backup'
ERROR_FILE = 'crash.tmp'
MODULES_REPO = 'https://raw.githubusercontent.com/Mitrichdfklwhcluio/MCUBFB/main/modules_catalog'
UPDATE_REPO = 'https://raw.githubusercontent.com/Mitrichdfklwhcluio/MCUBFB/main/'
loaded_modules = {}
start_time = time.time()
command_prefix = '.'
aliases = {}
last_healthcheck = time.time()
pending_confirmations = {}
power_save_mode = False
catalog_cache = {}

# переменые для риканекта
reconnect_attempts = 0
max_reconnect_attempts = 5
reconnect_delay = 10
shutdown_flag = False


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if not os.path.exists(CONFIG_FILE):
    print('Файл config.json не найден')
    print('Скопируйте config.example.json в config.json и заполните данные')
    sys.exit(1)

with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
    config = json.load(f)

command_prefix = config.get('command_prefix', '.')
aliases = config.get('aliases', {})
HEALTHCHECK_INTERVAL = config.get('healthcheck_interval', 30)
DEVELOPER_CHAT_ID = config.get('developer_chat_id', None)
DANGEROUS_COMMANDS = ['update', 'stop', 'um', 'rollback']
LANGUAGE = config.get('language', 'ru')
THEME = config.get('theme', 'default')
power_save_mode = config.get('power_save_mode', False)

LANGS = {
    'ru': {
        'ping': 'Pong!',
        'restart': 'Перезагрузка...',
        'update_check': '🔄 Проверка обновлений...',
        'module_installed': '✅ Модуль {} установлен',
        'error': '❌ Ошибка: {}'
    },
    'en': {
        'ping': 'Pong!',
        'restart': 'Restarting...',
        'update_check': '🔄 Checking updates...',
        'module_installed': '✅ Module {} installed',
        'error': '❌ Error: {}'
    }
}

THEMES = {
    'default': {'success': '✅', 'error': '❌', 'info': 'ℹ️', 'warning': '⚠️'},
    'minimal': {'success': '✓', 'error': '✗', 'info': 'i', 'warning': '!'},
    'emoji': {'success': '🎉', 'error': '💥', 'info': '💡', 'warning': '⚡'}
}

def t(key):
    return LANGS.get(LANGUAGE, LANGS['ru']).get(key, key)

def theme(key):
    return THEMES.get(THEME, THEMES['default']).get(key, '')

def progress_bar(current, total, width=10):
    percent = current / total
    filled = int(width * percent)
    bar = '█' * filled + '░' * (width - filled)
    return f'[{bar}] {int(percent * 100)}%'

async def migrate_data():
    db_version = config.get('db_version', 0)
    if db_version < DB_VERSION:
        cprint(f'🔄 Миграция данных с версии {db_version} до {DB_VERSION}...', Colors.YELLOW)
        config['db_version'] = DB_VERSION
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        cprint('✅ Миграция завершена', Colors.GREEN)

try:
    API_ID = int(config['api_id'])
    API_HASH = str(config['api_hash'])
    PHONE = str(config['phone'])
except (KeyError, ValueError) as e:
    print(f'Ошибка в config.json: {e}')
    print('Проверьте что api_id - это число, api_hash и phone - строки')
    sys.exit(1)

if API_ID == 0 or 'YOUR' in API_HASH or 'YOUR' in PHONE:
    print('Заполните config.json своими данными')
    print('1. Получите API_ID и API_HASH на https://my.telegram.org')
    print('2. Укажите номер телефона в формате +13371337')
    sys.exit(1)

import socks
proxy = config.get('proxy')

cprint(f'🔑 API_ID: {API_ID}', Colors.CYAN)
cprint(f'📞 Phone: {PHONE}', Colors.CYAN)

client = TelegramClient('user_session', API_ID, API_HASH, proxy=proxy)

if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

def log_command(command, chat_id, user_id, success=True):
    if power_save_mode:
        return
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    log_file = os.path.join(LOGS_DIR, f'{time.strftime("%Y-%m-%d")}.log')
    status = 'SUCCESS' if success else 'ERROR'
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f'[{timestamp}] [{status}] Chat: {chat_id} | User: {user_id} | Command: {command}\n')

async def healthcheck():
    global last_healthcheck, reconnect_attempts
    while True:
        try:
            interval = (HEALTHCHECK_INTERVAL * 3 if power_save_mode else HEALTHCHECK_INTERVAL) * 60
            await asyncio.sleep(interval)

            if shutdown_flag:
                break

            if power_save_mode:
                last_healthcheck = time.time()
                continue

            if not client.is_connected():
                cprint('⚠️ Healthcheck: соединение потеряно', Colors.YELLOW)
                if not await safe_connect():
                    cprint('❌ Healthcheck: не удалось восстановить соединение', Colors.RED)
                    continue

            current_time = time.time()

            process = psutil.Process()
            cpu = process.cpu_percent(interval=0.1)
            ram = process.memory_info().rss / 1024 / 1024

            if cpu > 80 or ram > 500:
                log_command(f'HEALTHCHECK: High usage - CPU: {cpu}%, RAM: {ram}MB', 0, 0, False)

            last_healthcheck = current_time
        except Exception as e:
            log_command(f'HEALTHCHECK ERROR: {str(e)}', 0, 0, False)
            reconnect_attempts = 0
            await asyncio.sleep(30)


async def safe_connect():
    global reconnect_attempts
    while reconnect_attempts < max_reconnect_attempts:
        if shutdown_flag:
            return False
        try:
            if client.is_connected():
                return True

            await client.connect()
            if await client.is_user_authorized():
                cprint('✅ Переподключение успешно', Colors.GREEN)
                reconnect_attempts = 0
                return True

        except (ConnectionError, RPCError) as e:
            reconnect_attempts += 1
            cprint(f'❌ Ошибка подключения ({reconnect_attempts}/{max_reconnect_attempts}): {e}', Colors.RED)

            if reconnect_attempts >= max_reconnect_attempts:
                cprint('⚠️ Достигнут лимит попыток переподключения', Colors.YELLOW)
                return False

            wait_time = reconnect_delay * reconnect_attempts
            cprint(f'⏳ Повторная попытка через {wait_time} секунд...', Colors.YELLOW)
            await asyncio.sleep(wait_time)

        except Exception as e:
            cprint(f'❌ Неожиданная ошибка: {e}', Colors.RED)
            reconnect_attempts += 1
            await asyncio.sleep(reconnect_delay)

    return False

async def send_with_retry(event, text, **kwargs):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if not client.is_connected():
                if not await safe_connect():
                    return None
            return await event.edit(text, **kwargs)
        except (ConnectionError, RPCError) as e:
            if attempt < max_retries - 1:
                cprint(f'⚠️ Повтор отправки ({attempt+1}/{max_retries})', Colors.YELLOW)
                await asyncio.sleep(2 * (attempt + 1))
            else:
                cprint(f'❌ Не удалось отправить сообщение: {e}', Colors.RED)
                return None
    return None

async def check_connection():
    while True:
        await asyncio.sleep(60)
        if shutdown_flag:
            break
        if not client.is_connected():
            cprint('🔍 Проверка соединения: отключено', Colors.YELLOW)
            if not await safe_connect():
                cprint('❌ Проверка соединения: переподключение не удалось', Colors.RED)
            else:
                cprint('✅ Проверка соединения: восстановлено', Colors.GREEN)


async def report_crash(error_msg):
    if DEVELOPER_CHAT_ID:
        try:
            me = await client.get_me()
            report = f'🚨 **Crash Report**\n\n'
            report += f'👤 User: {me.first_name} ({me.id})\n'
            report += f'💻 Version: {VERSION}\n'
            report += f'⏰ Time: {time.strftime("%Y-%m-%d %H:%M:%S")}\n'
            report += f'❌ Error:\n```\n{error_msg[:500]}\n```'
            await client.send_message(DEVELOPER_CHAT_ID, report)
        except:
            pass

@client.on(events.NewMessage(outgoing=True))
async def handler(event):
    global command_prefix, aliases, pending_confirmations, power_save_mode, config
    text = event.text
    
    if not text.startswith(command_prefix):
        return
    
    cmd = text[len(command_prefix):].split()[0] if ' ' in text else text[len(command_prefix):]
    if cmd in aliases:
        text = command_prefix + aliases[cmd] + text[len(command_prefix) + len(cmd):]
    
    if cmd == 'confirm':
            confirm_key = f'{event.chat_id}_{event.sender_id}'
            if confirm_key in pending_confirmations:
                saved_command = pending_confirmations[confirm_key]
                del pending_confirmations[confirm_key]
                event.text = saved_command
                await handler(event)
                return
            else:
                await event.edit('❌ Нет команд, ожидающих подтверждения')
                return

    if cmd in DANGEROUS_COMMANDS and config.get('2fa_enabled', False):
        confirm_key = f'{event.chat_id}_{event.sender_id}'
        if confirm_key not in pending_confirmations:
            pending_confirmations[confirm_key] = text
            await event.delete()
            
            bot_username = config.get('inline_bot_username')
            if bot_username:
                try:
                    query = f'2fa_{confirm_key}_{text}'
                    bot = await client.inline_query(bot_username, query)
                    await bot[0].click(event.chat_id)
                except:
                    await client.send_message(event.chat_id, f'⚠️ Требуется подтверждение: `{text}`\n\nНапишите `{command_prefix}confirm` для подтверждения')
            else:
                await client.send_message(event.chat_id, f'⚠️ Требуется подтверждение: `{text}`\n\nНапишите `{command_prefix}confirm` для подтверждения')
            return
        else:
            await event.edit('⚠️ Эта команда уже ожидает подтверждения')
            return
    
    log_command(text, event.chat_id, event.sender_id)
    
    if text == f'{command_prefix}ping':
        start = time.time()
        msg = await event.edit('Pong!')
        end = time.time()
        await msg.edit(f'Pong! {round((end - start) * 1000)}ms')
    
    elif text == f'{command_prefix}info':
        await event.delete()
        
        me = await client.get_me()
        owner_name = me.first_name
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://raw.githubusercontent.com/Mitrichdfklwhcluio/MCUBFB/refs/heads/main/version.txt', timeout=aiohttp.ClientTimeout(total=3)) as resp:
                    if resp.status == 200:
                        latest_version = (await resp.text()).strip()
                        version_status = '✅ Актуальная' if VERSION == latest_version else f'⚠️ Доступна {latest_version}'
                    else:
                        version_status = '❓ Не удалось проверить'
        except:
            version_status = '❓ Не удалось проверить'
        
        uptime_seconds = int(time.time() - start_time)
        hours = uptime_seconds // 3600
        minutes = (uptime_seconds % 3600) // 60
        seconds = uptime_seconds % 60
        uptime = f'{hours}ч {minutes}м {seconds}с'
        
        process = psutil.Process()
        cpu_percent = process.cpu_percent(interval=0.1)
        ram_mb = process.memory_info().rss / 1024 / 1024
        power_status = '🔋 Вкл' if power_save_mode else '⚡ Выкл'
        
        img_path = None
        if os.path.exists(IMG_DIR):
            images = [f for f in os.listdir(IMG_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))]
            if images:
                img_path = os.path.join(IMG_DIR, images[0])
        
        caption = f'''**Mitrich UserBot**
👤 Владелец: {owner_name}
💻 Версия: {VERSION}
{version_status}
⏱ Аптайм: {uptime}
📊 CPU: {cpu_percent:.1f}%
💾 RAM: {ram_mb:.1f} MB
🔋 Энергосбережение: {power_status}
🟢 Статус: Working'''
        
        if img_path:
            await client.send_file(event.chat_id, img_path, caption=caption)
        else:
            await client.send_message(event.chat_id, caption)
    
    elif text == f'{command_prefix}help':
        help_text = f'''📚 **Mitrich UserBot - Команды**

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
{command_prefix}alias [алиас] = [команда] - создать алиас (пример: alias p = ping)
{command_prefix}logs [chat_id] - отправить логи в чат
{command_prefix}t [команда] - выполнить команду в терминале
{command_prefix}rollback - откатиться к предыдущей версии
{command_prefix}2fa - вкл/выкл 2FA для опасных команд
{command_prefix}powersave - режим энергосбережения
{command_prefix}ibot [текст | кнопка:url] - отправить через inline-бота'''
        await event.edit(help_text)
    
    elif text == f'{command_prefix}restart':
        await event.edit('Перезагрузка...')
        with open(RESTART_FILE, 'w') as f:
            f.write(f'{event.chat_id},{event.id},{time.time()}')
        os.execl(sys.executable, sys.executable, *sys.argv)
    
    elif text == f'{command_prefix}update':
        await event.edit('🔄 Проверка обновлений...')
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f'{UPDATE_REPO}/userbot.py') as resp:
                    if resp.status == 200:
                        new_code = await resp.text()
                        
                        if 'VERSION' in new_code:
                            new_version = re.search(r"VERSION = '([^']+)'", new_code)
                            if new_version and new_version.group(1) != VERSION:
                                await event.edit(f'📥 Обновление до {new_version.group(1)}...')
                                
                                with open(__file__, 'r', encoding='utf-8') as f:
                                    current_code = f.read()
                                with open(BACKUP_FILE, 'w', encoding='utf-8') as f:
                                    f.write(current_code)
                                
                                with open(__file__, 'w', encoding='utf-8') as f:
                                    f.write(new_code)
                                
                                await event.edit(f'✅ Обновлено до {new_version.group(1)}\n📦 Бэкап создан\nПерезагрузка...')
                                await asyncio.sleep(1)
                                os.execl(sys.executable, sys.executable, *sys.argv)
                            else:
                                await event.edit(f'✅ У вас актуальная версия {VERSION}')
                        else:
                            await event.edit('❌ Не удалось проверить версию')
                    else:
                        await event.edit('❌ Не удалось получить обновление')
        except Exception as e:
            await event.edit(f'❌ Ошибка: {str(e)}')
    
    elif text == f'{command_prefix}stop':
        global shutdown_flag
        shutdown_flag = True
        await event.edit('⛔ Остановка юзербота...')
        await asyncio.sleep(1)
        await client.disconnect()
    
    elif text == f'{command_prefix}dlml' or text.startswith(f'{command_prefix}dlml '):
        page = 1
        if ' ' in text:
            try:
                page = int(text.split()[1])
            except:
                page = 1
        
        bot_username = config.get('inline_bot_username')
        if not bot_username:
            await event.edit('❌ Inline-бот не настроен')
            return
        
        await event.delete()
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f'{MODULES_REPO}/catalog.json') as resp:
                    if resp.status == 200:
                        text_data = await resp.text()
                        catalog = json.loads(text_data)
                        
                        global catalog_cache
                        catalog_cache = catalog
                        
                        query = f'catalog_{page}'
                        results = await client.inline_query(bot_username, query)
                        
                        if results:
                            await results[0].click(event.chat_id)
                        else:
                            await client.send_message(event.chat_id, '❌ Ошибка инлайн-бота')
                    else:
                        await client.send_message(event.chat_id, '❌ Каталог не найден')
        except Exception as e:
            await client.send_message(event.chat_id, f'❌ Ошибка: {str(e)}')
    
    elif text.startswith(f'{command_prefix}dlm '):
        module_name = text[len(command_prefix)+4:].strip()
        is_update = module_name in loaded_modules
        msg = await event.edit(f'📥 {"Обновление" if is_update else "Загрузка"} {module_name}...')
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f'{MODULES_REPO}/{module_name}.py') as resp:
                    if resp.status == 200:
                        if not os.path.exists(MODULES_DIR):
                            os.makedirs(MODULES_DIR)
                        
                        code = await resp.text()
                        file_path = os.path.join(MODULES_DIR, f'{module_name}.py')
                        
                        if is_update and module_name in sys.modules:
                            del sys.modules[module_name]
                        
                        await msg.edit(f'📥 {progress_bar(1, 3)} Сохранение...')
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(code)
                        
                        await msg.edit(f'📦 {progress_bar(2, 3)} Установка зависимостей...')
                        if 'requires' in code:
                            reqs = re.findall(r'# requires: (.+)', code)
                            if reqs:
                                for req in reqs[0].split(','):
                                    subprocess.run([sys.executable, '-m', 'pip', 'install', req.strip()], capture_output=True)
                        
                        await msg.edit(f'⚙️ {progress_bar(3, 3)} Загрузка модуля...')
                        spec = importlib.util.spec_from_file_location(module_name, file_path)
                        module = importlib.util.module_from_spec(spec)
                        sys.modules[module_name] = module
                        spec.loader.exec_module(module)
                        
                        if hasattr(module, 'register'):
                            client.send_inline = send_inline
                            module.register(client)
                            loaded_modules[module_name] = module
                            status = '🔄 обновлен' if is_update else 'установлен'
                            await msg.edit(f'{theme("success")} Модуль {module_name} {status}')
                        else:
                            await event.edit(f'❌ Модуль не имеет register(client)')
                            os.remove(file_path)
                    else:
                        await event.edit(f'❌ Модуль {module_name} не найден в каталоге')
        except Exception as e:
            await event.edit(f'❌ Ошибка: {str(e)}')
    
    elif text == f'{command_prefix}im':
        if not event.is_reply:
            await event.edit('❌ Ответьте на .py файл')
            return
        
        reply = await event.get_reply_message()
        if not reply.document or not reply.document.attributes[0].file_name.endswith('.py'):
            await event.edit('❌ Это не .py файл')
            return
        
        file_name = reply.document.attributes[0].file_name
        module_name = file_name[:-3]
        is_update = module_name in loaded_modules
        
        await event.edit(f'📥 {"Обновление" if is_update else "Загрузка"} модуля...')
        
        if not os.path.exists(MODULES_DIR):
            os.makedirs(MODULES_DIR)
        
        file_path = os.path.join(MODULES_DIR, file_name)
        await reply.download_media(file_path)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()
            
            if 'from .. import' in code or 'import loader' in code:
                await event.edit(f'Модуль не совместим. Используйте модули с register(client)')
                os.remove(file_path)
                return
            
            if is_update and module_name in sys.modules:
                del sys.modules[module_name]
            
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            
            if hasattr(module, 'register'):
                client.send_inline = send_inline
                module.register(client)
                loaded_modules[module_name] = module
                status = '🔄 обновлен' if is_update else 'установлен'
                await event.edit(f'✅ Модуль {file_name} {status}')
            else:
                await event.edit(f'❌ Модуль должен иметь функцию register(client)')
                os.remove(file_path)
        except Exception as e:
            await event.edit(f'❌ Ошибка: {str(e)}')
            if os.path.exists(file_path):
                os.remove(file_path)
    
    elif text == f'{command_prefix}lm':
        if not loaded_modules:
            await event.edit('📦 Модули не загружены')
            return
        
        msg = '📦 **Загруженные модули:**\n\n'
        for name, module in loaded_modules.items():
            msg += f'• **{name}**\n'
            if os.path.exists(os.path.join(MODULES_DIR, f'{name}.py')):
                with open(os.path.join(MODULES_DIR, f'{name}.py'), 'r', encoding='utf-8') as f:
                    code = f.read()
                    commands = re.findall(r"pattern=r['\"]\^?\\?\.([a-zA-Z0-9_]+)", code)
                    if commands:
                        msg += f'  Команды: {", ".join([f".{cmd}" for cmd in commands])}\n'
            msg += '\n'
        await event.edit(msg)
    
    elif text.startswith(f'{command_prefix}um '):
        module_name = text[len(command_prefix)+3:].strip()
        
        if module_name not in loaded_modules:
            await event.edit(f'❌ Модуль {module_name} не найден')
            return
        
        file_path = os.path.join(MODULES_DIR, f'{module_name}.py')
        if os.path.exists(file_path):
            os.remove(file_path)
        
        if module_name in sys.modules:
            del sys.modules[module_name]
        
        del loaded_modules[module_name]
        await event.edit(f'🗑️ Модуль {module_name} удален\n\n⚠️ Перезагрузите юзербот для полного удаления')
    
    elif text.startswith(f'{command_prefix}unlm '):
        module_name = text[len(command_prefix)+5:].strip()
        
        if module_name not in loaded_modules:
            await event.edit(f'❌ Модуль {module_name} не найден')
            return
        
        file_path = os.path.join(MODULES_DIR, f'{module_name}.py')
        if not os.path.exists(file_path):
            await event.edit(f'❌ Файл модуля {module_name}.py не найден')
            return
        
        await event.edit(f'📤 Отправка модуля {module_name}...')
        await client.send_file(event.chat_id, file_path, caption=f'📦 Модуль: {module_name}.py')
        await event.delete()
    
    elif text.startswith(f'{command_prefix}prefix '):
        new_prefix = text[len(command_prefix)+7:].strip()
        if len(new_prefix) != 1:
            await event.edit('❌ Префикс должен быть одним символом')
            return
        
        command_prefix = new_prefix
        config['command_prefix'] = new_prefix
        
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        await event.edit(f'✅ Префикс изменен на `{new_prefix}`')
    
    elif text.startswith(f'{command_prefix}alias '):
        args = text[len(command_prefix)+6:].strip()
        if '=' not in args:
            await event.edit(f'❌ Использование: `{command_prefix}alias алиас = команда`')
            return
        
        parts = args.split('=')
        if len(parts) != 2:
            await event.edit(f'❌ Использование: `{command_prefix}alias алиас = команда`')
            return
        
        alias = parts[0].strip()
        command = parts[1].strip()
        
        aliases[alias] = command
        config['aliases'] = aliases
        
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        await event.edit(f'✅ Алиас создан: `{command_prefix}{alias}` → `{command_prefix}{command}`')
    
    elif text == f'{command_prefix}menu':
        title = '🤖 **Mitrich UserBot - Меню**'
        
        buttons = [
            [
                Button.inline('📊 Инфо', b'info'), Button.inline('📦 Модули', b'modules')
            ],
            [
                Button.inline('⚙️ Настройки', b'settings'), Button.inline('📝 Логи', b'logs')
            ],
            [
                Button.inline('🔄 Обновить', b'update'), Button.inline('🔄 Перезагрузка', b'restart')
            ]
        ]
        await event.edit(title, buttons=buttons)
    
    elif text.startswith(f'{command_prefix}lang '):
        new_lang = text[len(command_prefix)+5:].strip()
        if new_lang in LANGS:
            global LANGUAGE
            LANGUAGE = new_lang
            config['language'] = new_lang
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            await event.edit(f'✅ Language changed to: {new_lang}')
        else:
            await event.edit(f'❌ Available: {", ".join(LANGS.keys())}')
    
    elif text.startswith(f'{command_prefix}theme '):
        new_theme = text[len(command_prefix)+6:].strip()
        if new_theme in THEMES:
            global THEME
            THEME = new_theme
            config['theme'] = new_theme
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            await event.edit(f'{theme("success")} Тема изменена на: {new_theme}')
        else:
            await event.edit(f'❌ Доступны: {", ".join(THEMES.keys())}')
    
    elif text.startswith(f'{command_prefix}logs'):
        args = text[len(command_prefix)+5:].strip()
        target_chat = int(args) if args else event.chat_id
        
        log_files = sorted([f for f in os.listdir(LOGS_DIR) if f.endswith('.log')])
        if not log_files:
            await event.edit('📝 Логи отсутствуют')
            return
        
        latest_log = os.path.join(LOGS_DIR, log_files[-1])
        await client.send_file(target_chat, latest_log, caption=f'📝 Логи за {log_files[-1][:-4]}')
        await event.delete()
    
    elif text == f'{command_prefix}confirm':
        await event.edit('✅ Команда подтверждена. Выполните её снова.')
        return
    
    elif text == f'{command_prefix}2fa':
        current = config.get('2fa_enabled', False)
        config['2fa_enabled'] = not current
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        status = '✅ включена (инлайн-подтверждение)' if not current else '❌ выключена'
        await event.edit(f'🔐 Двухфакторная аутентификация {status}\n\n'
                        f'Теперь опасные команды требуют подтверждения через кнопки.')
    
    elif text == f'{command_prefix}rollback':
        if not os.path.exists(BACKUP_FILE):
            await event.edit('❌ Бэкап не найден')
            return
        
        await event.edit('🔄 Откат к предыдущей версии...')
        
        try:
            with open(BACKUP_FILE, 'r', encoding='utf-8') as f:
                backup_code = f.read()
            
            with open(__file__, 'w', encoding='utf-8') as f:
                f.write(backup_code)
            
            await event.edit('✅ Откат завершен\nПерезагрузка...')
            await asyncio.sleep(1)
            os.execl(sys.executable, sys.executable, *sys.argv)
        except Exception as e:
            await event.edit(f'❌ Ошибка отката: {str(e)}')
    
    elif text == f'{command_prefix}powersave':
        power_save_mode = not power_save_mode
        config['power_save_mode'] = power_save_mode
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        status = '🔋 включен' if power_save_mode else '⚡ выключен'
        features = '\n• Логирование отключено\n• Healthcheck реже в 3 раза\n• Снижена нагрузка' if power_save_mode else ''
        await event.edit(f'Режим энергосбережения {status}{features}')
    
    elif text.startswith(f'{command_prefix}ibot '):
        bot_username = config.get('inline_bot_username')
        if not bot_username:
            await event.edit('❌ Inline-бот не настроен. Перезапустите юзербот')
            return
        
        await event.delete()
        
        args = text[len(command_prefix)+5:].strip()
        
        try:
            results = await client.inline_query(bot_username, args)
            
            if results:
                await results[0].click(event.chat_id)
            else:
                await client.send_message(event.chat_id, '❌ Инлайн-бот не вернул результатов')
                
        except Exception as e:
            await client.send_message(event.chat_id, f'❌ Ошибка инлайна: {e}')
    
    elif text.startswith(f'{command_prefix}t '):
        command = text[len(command_prefix)+2:].strip()
        if not command:
            await event.edit('❌ Укажите команду')
            return
        
        await event.edit(f'💻 Выполнение: `{command}`')
        
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            output = stdout.decode('utf-8') if stdout else ''
            error = stderr.decode('utf-8') if stderr else ''
            
            result = ''
            if output:
                result += f'📝 **Вывод:**\n```\n{output[:3000]}\n```\n'
            if error:
                result += f'❌ **Ошибка:**\n```\n{error[:3000]}\n```\n'
            
            if not result:
                result = '✅ Команда выполнена без вывода'
            
            result = f'💻 **Terminal:** `{command}`\n\n{result}'
            await event.edit(result)
        except Exception as e:
            await event.edit(f'❌ Ошибка: {str(e)}')


async def check_inline_bot():
    bot_token = config.get('inline_bot_token')
    
    if bot_token:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f'https://api.telegram.org/bot{bot_token}/getMe') as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('ok'):
                            bot_username = data['result']['username']
                            cprint(f'✅ Inline-бот активен: @{bot_username}', Colors.GREEN)
                            return True
        except:
            pass
    
    cprint('🤖 Создание inline-бота...', Colors.YELLOW)
    try:
        me = await client.get_me()
        bot_username = f'MCUB_{str(me.id)[-6:]}_{str(int(time.time()))[-4:]}_bot'
        
        botfather = await client.get_entity('BotFather')
        
        await client.send_message(botfather, '/newbot')
        await asyncio.sleep(1)
        
        await client.send_message(botfather, 'MCUBinline')
        await asyncio.sleep(1)
        
        await client.send_message(botfather, bot_username)
        await asyncio.sleep(2)
        
        messages = await client.get_messages(botfather, limit=1)
        if messages and 'token' in messages[0].text.lower():
            token_match = re.search(r'(\d+:[A-Za-z0-9_-]+)', messages[0].text)
            if token_match:
                bot_token = token_match.group(1)
                config['inline_bot_token'] = bot_token
                config['inline_bot_username'] = bot_username
                
                await client.send_message(botfather, '/setinline')
                await asyncio.sleep(1)
                await client.send_message(botfather, f'@{bot_username}')
                await asyncio.sleep(1)
                await client.send_message(botfather, 'inline')
                
                with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                    json.dump(config, f, ensure_ascii=False, indent=2)
                
                cprint(f'✅ Inline-бот создан: @{bot_username}', Colors.GREEN)
                return True
        
        cprint('❌ Не удалось создать бота', Colors.RED)
    except Exception as e:
        cprint(f'❌ Ошибка создания бота: {e}', Colors.RED)
    
    return False

async def run_inline_bot():
    bot_token = config.get('inline_bot_token')
    if not bot_token:
        return
    
    try:
        from telethon import TelegramClient as BotClient
        bot = BotClient('inline_bot', API_ID, API_HASH)
        await bot.start(bot_token=bot_token)
        
        @bot.on(events.InlineQuery)
        async def inline_handler(event):
            query = event.text
            
            if query.startswith('2fa_'):
                parts = query.split('_', 3)
                if len(parts) >= 4:
                    confirm_key = f'{parts[1]}_{parts[2]}'
                    command = parts[3]
                    text = f'⚠️ **Требуется подтверждение**\n\nКоманда: `{command}`\n\nВы действительно хотите выполнить эту команду?'
                    buttons = [
                        [Button.inline('✅ Подтвердить', b'confirm_yes'),
                         Button.inline('❌ Отменить', b'confirm_no')]
                    ]
                    builder = event.builder.article('2FA', text=text, buttons=buttons)
                else:
                    builder = event.builder.article('Error', text='❌ Ошибка подтверждения')
            elif query.startswith('catalog_'):
                page = int(query.split('_')[1])
                
                if not catalog_cache:
                    builder = event.builder.article('Error', text='❌ Каталог не загружен. Используйте .dlml')
                else:
                    catalog = catalog_cache
                    modules_list = list(catalog.items())
                    per_page = 5
                    total_pages = (len(modules_list) + per_page - 1) // per_page
                    
                    if page < 1:
                        page = 1
                    if page > total_pages:
                        page = total_pages
                    
                    start_idx = (page - 1) * per_page
                    end_idx = start_idx + per_page
                    page_modules = modules_list[start_idx:end_idx]
                    
                    msg = f'📚 <b>Каталог модулей</b> (Стр. {page}/{total_pages})\n\n'
                    for module_name, info in page_modules:
                        msg += f'• <b>{module_name}</b>\n'
                        msg += f'  {info.get("description", "Описание отсутствует")}\n'
                        if 'author' in info:
                            msg += f'  👤 Автор: @{info["author"]}\n'
                        if 'commands' in info:
                            msg += f'  Команды: {", ".join(info["commands"])}\n'
                        msg += '\n'
                    
                    msg += f'\nИспользуйте: <code>.dlm название</code>'
                    
                    buttons = []
                    nav_buttons = []
                    if page > 1:
                        nav_buttons.append(Button.inline('⬅️ Назад', f'dlml_{page-1}'.encode()))
                    if page < total_pages:
                        nav_buttons.append(Button.inline('➡️ Вперёд', f'dlml_{page+1}'.encode()))
                    
                    if nav_buttons:
                        buttons.append(nav_buttons)
                    
                    builder = event.builder.article('Catalog', text=msg, buttons=buttons if buttons else None, parse_mode='html')
            elif '|' in query:
                parts = query.split('|')
                text = parts[0].strip()
                buttons = []
                for btn_data in parts[1:]:
                    btn_data = btn_data.strip()
                    if ':' in btn_data:
                        btn_parts = btn_data.split(':', 1)
                        url = btn_parts[1].strip()
                        # Проверка валидности URL
                        if url.startswith(('http://', 'https://', 't.me/', 'tg://')):
                            buttons.append([Button.url(btn_parts[0].strip(), url)])
                
                builder = event.builder.article('Message', text=text, buttons=buttons if buttons else None, parse_mode='html')
            else:
                builder = event.builder.article('Message', text=query, parse_mode='html')
            
            await event.answer([builder])
        
        @bot.on(events.CallbackQuery)
        async def bot_callback_handler(event):
            global pending_confirmations
            sender = await event.get_sender()
            chat_id = event.chat_id
            
            # Проверка что кнопку нажал владелец
            me = await client.get_me()
            if sender.id != me.id:
                await event.answer('❌ Эта кнопка не для вас', alert=True)
                return
            
            if event.data == b'confirm_yes':
                confirm_key = f'{chat_id}_{sender.id}'
                if confirm_key in pending_confirmations:
                    saved_command = pending_confirmations[confirm_key]
                    del pending_confirmations[confirm_key]
                    
                    await event.answer('✅ Подтверждено')
                    await event.edit(f'✅ **Команда подтверждена**\n\nВыполняю: `{saved_command}`')
                    
                    await client.send_message(chat_id, saved_command)
                else:
                    await event.answer('❌ Команда не найдена')
                    await event.edit('❌ Команда не найдена или уже выполнена')
            
            elif event.data == b'confirm_no':
                confirm_key = f'{chat_id}_{sender.id}'
                if confirm_key in pending_confirmations:
                    del pending_confirmations[confirm_key]
                    await event.answer('❌ Отменено')
                    await event.edit('❌ Команда отменена')
                else:
                    await event.answer('❌ Нечего отменять')
                    await event.edit('❌ Нечего отменять')
            
            elif event.data.startswith(b'dlml_'):
                page = int(event.data.decode().split('_')[1])
                await event.answer()
                
                if not catalog_cache:
                    await event.edit('❌ Каталог не загружен')
                    return
                
                catalog = catalog_cache
                modules_list = list(catalog.items())
                per_page = 5
                total_pages = (len(modules_list) + per_page - 1) // per_page
                
                if page < 1:
                    page = 1
                if page > total_pages:
                    page = total_pages
                
                start_idx = (page - 1) * per_page
                end_idx = start_idx + per_page
                page_modules = modules_list[start_idx:end_idx]
                
                msg = f'📚 <b>Каталог модулей</b> (Стр. {page}/{total_pages})\n\n'
                for module_name, info in page_modules:
                    msg += f'• <b>{module_name}</b>\n'
                    msg += f'  {info.get("description", "Описание отсутствует")}\n'
                    if 'author' in info:
                        msg += f'  👤 Автор: @{info["author"]}\n'
                    if 'commands' in info:
                        msg += f'  Команды: {", ".join(info["commands"])}\n'
                    msg += '\n'
                
                msg += f'\nИспользуйте: <code>.dlm название</code>'
                
                buttons = []
                nav_buttons = []
                if page > 1:
                    nav_buttons.append(Button.inline('⬅️ Назад', f'dlml_{page-1}'.encode()))
                if page < total_pages:
                    nav_buttons.append(Button.inline('➡️ Вперёд', f'dlml_{page+1}'.encode()))
                
                if nav_buttons:
                    buttons.append(nav_buttons)
                
                await event.edit(msg, buttons=buttons if buttons else None, parse_mode='html')
        
        await bot.run_until_disconnected()
    except:
        pass

async def main():
    global reconnect_attempts

    try:
        await migrate_data()

        await client.start(phone=PHONE)

        if not await safe_connect():
            cprint('❌ Не удалось подключиться к Telegram', Colors.RED)
            sys.exit(1)

        cprint('✅ MCUB запущен', Colors.GREEN)

        await check_inline_bot()
        asyncio.create_task(run_inline_bot())
        asyncio.create_task(healthcheck())
        asyncio.create_task(check_connection())
        cprint(f'💚 Healthcheck запущен (каждые {HEALTHCHECK_INTERVAL} мин)', Colors.GREEN)

    except Exception as e:
        print(f'❌ Ошибка авторизации: {e}')
        print('Проверьте API_ID, API_HASH и PHONE в config.json')
        await report_crash(str(e))
        sys.exit(1)

    if not os.path.exists(MODULES_DIR):
        os.makedirs(MODULES_DIR)

    if os.path.exists(MODULES_DIR):
        for file_name in os.listdir(MODULES_DIR):
            if file_name.endswith('.py'):
                try:
                    if not client.is_connected():
                        if not await safe_connect():
                            cprint('⚠️ Пропуск загрузки модулей: нет соединения', Colors.YELLOW)
                            break

                    file_path = os.path.join(MODULES_DIR, file_name)

                    with open(file_path, 'r', encoding='utf-8') as f:
                        code = f.read()

                    if 'from .. import' in code or 'import loader' in code:
                        cprint(f'Пропущен несовместимый модуль: {file_name}', Colors.YELLOW)
                        continue

                    spec = importlib.util.spec_from_file_location(file_name[:-3], file_path)
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[file_name[:-3]] = module
                    spec.loader.exec_module(module)
                    if hasattr(module, 'register'):
                        client.send_inline = send_inline
                        module.register(client)
                        loaded_modules[file_name[:-3]] = module
                        cprint(f'Загружен модуль: {file_name}', Colors.GREEN)
                    else:
                        cprint(f'Модуль {file_name} не имеет register(client)', Colors.YELLOW)
                except Exception as e:
                    cprint(f'Ошибка загрузки {file_name}: {e}', Colors.RED)

    if os.path.exists(RESTART_FILE):
        with open(RESTART_FILE, 'r') as f:
            chat_id, msg_id, start_time = f.read().split(',')
        os.remove(RESTART_FILE)
        restart_time = round((time.time() - float(start_time)) * 1000)
        if client.is_connected():
            await client.edit_message(int(chat_id), int(msg_id), f'MCUB перезагружен ✅\nВремя: {restart_time}ms')
        else:
            cprint(f'⚠️ Не удалось отправить сообщение о перезагрузке: нет соединения', Colors.YELLOW)

    while True:
        try:
            if shutdown_flag:
                break
            if not client.is_connected():
                if not await safe_connect():
                    cprint('⚠️ Основное соединение потеряно, ожидание...', Colors.YELLOW)
                    await asyncio.sleep(30)
                    continue

            await client.run_until_disconnected()

        except (ConnectionError, RPCError) as e:
            cprint(f'⚠️ Разрыв соединения: {e}', Colors.YELLOW)
            reconnect_attempts = 0
            if not await safe_connect():
                cprint('❌ Критический разрыв соединения', Colors.RED)
                await asyncio.sleep(60)
        except Exception as e:
            cprint(f'❌ Неожиданная ошибка в main: {e}', Colors.RED)
            reconnect_attempts = 0
            await asyncio.sleep(30)

if __name__ == '__main__':
    try:
        if os.path.exists(ERROR_FILE):
            with open(ERROR_FILE, 'r') as f:
                error_data = f.read().split('|')
                if len(error_data) >= 2:
                    chat_id, msg_id = error_data[0], error_data[1]
                    print(f'⚠️ Обнаружен файл краша. Попытка восстановления...')

                    if os.path.exists(BACKUP_FILE):
                        print('📦 Найден бэкап. Восстанавливаю...')
                        with open(BACKUP_FILE, 'r', encoding='utf-8') as backup:
                            backup_code = backup.read()
                        with open(__file__, 'w', encoding='utf-8') as current:
                            current.write(backup_code)
                        os.remove(ERROR_FILE)
                        print('✅ Восстановление завершено. Перезапуск...')
                        os.execl(sys.executable, sys.executable, *sys.argv)
            os.remove(ERROR_FILE)

        asyncio.run(main())
    except KeyboardInterrupt:
        print('\n⛔ Остановка юзербота...')
        if client.is_connected():
            client.disconnect()
        sys.exit(0)
    except Exception as e:
        print(f'\n❌ Критическая ошибка: {e}')
        print('📝 Сохранение информации об ошибке...')

        try:
            if os.path.exists(RESTART_FILE):
                with open(RESTART_FILE, 'r') as f:
                    chat_id, msg_id, _ = f.read().split(',')
                with open(ERROR_FILE, 'w') as f:
                    f.write(f'{chat_id}|{msg_id}|{str(e)}')
        except:
            pass

        print('\n🔧 Варианты восстановления:')
        print('1. Перезапустите юзербот - будет попытка автовосстановления')
        print('2. Используйте команду .rollback для отката к предыдущей версии')
        print('3. Проверьте логи в папке logs/')
        sys.exit(1)
