"""Module loader for userbot."""

import importlib.util
import importlib
import os
import sys
from typing import TYPE_CHECKING, Callable, Dict, Optional

if TYPE_CHECKING:
    from telethon import TelegramClient

from ..utils import Colors, cprint, ensure_dir, progress_bar


#: Loaded modules registry
loaded_modules: Dict[str, "ModuleType"] = {}

#: Module type (stub for type hints)
ModuleType = type(lambda: None)


def register_module(name: str, module: ModuleType) -> None:
    """
    Register a loaded module.

    :param name: Module name.
    :param module: Module instance.
    """
    loaded_modules[name] = module


def unregister_module(name: str) -> Optional[ModuleType]:
    """
    Unregister a module.

    :param name: Module name.
    :return: Unregistered module or None.
    """
    if name in sys.modules:
        del sys.modules[name]
    if name in loaded_modules:
        del loaded_modules[name]
    return loaded_modules.get(name)


def is_module_compatible(code: str) -> bool:
    """
    Check if module code is compatible with current loader.

    :param code: Module source code.
    :return: True if compatible.
    """
    return "from .. import" not in code and "import loader" not in code


async def load_module_from_file(
    client: "TelegramClient",
    file_path: str,
    send_inline: Optional[Callable] = None,
    modules_dir: str = "modules",
) -> bool:
    """
    Load a module from file path.

    :param client: Telegram client instance.
    :param file_path: Full path to module file.
    :param send_inline: Function to send inline query.
    :param modules_dir: Modules directory path.
    :return: True if loaded successfully.
    """
    file_name = os.path.basename(file_path)
    module_name = file_name[:-3]  # Remove .py

    is_update = module_name in loaded_modules

    with open(file_path, "r", encoding="utf-8") as f:
        code = f.read()

    if not is_module_compatible(code):
        cprint(f"Пропущен несовместимый модуль: {file_name}", Colors.YELLOW)
        return False

    if is_update and module_name in sys.modules:
        del sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    try:
        spec.loader.exec_module(module)

        if hasattr(module, "register"):
            if send_inline:
                client.send_inline = send_inline
            module.register(client)
            loaded_modules[module_name] = module
            cprint(f"Загружен модуль: {file_name}", Colors.GREEN)
            return True
        else:
            cprint(f"Модуль {file_name} не имеет register(client)", Colors.YELLOW)
            return False
    except Exception as e:
        cprint(f"Ошибка загрузки {file_name}: {e}", Colors.RED)
        return False


async def load_module_from_code(
    client: "TelegramClient",
    code: str,
    module_name: str,
    send_inline: Optional[Callable] = None,
    modules_dir: str = "modules",
) -> bool:
    """
    Load a module from source code.

    :param client: Telegram client instance.
    :param code: Module source code.
    :param module_name: Module name.
    :param send_inline: Function to send inline query.
    :param modules_dir: Modules directory path.
    :return: True if loaded successfully.
    """
    is_update = module_name in loaded_modules

    ensure_dir(modules_dir)

    file_path = os.path.join(modules_dir, f"{module_name}.py")

    if not is_module_compatible(code):
        return False

    if is_update and module_name in sys.modules:
        del sys.modules[module_name]

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(code)

    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    try:
        spec.loader.exec_module(module)

        if hasattr(module, "register"):
            if send_inline:
                client.send_inline = send_inline
            module.register(client)
            loaded_modules[module_name] = module
            return True
        else:
            if os.path.exists(file_path):
                os.remove(file_path)
            return False
    except Exception:
        if os.path.exists(file_path):
            os.remove(file_path)
        return False


async def load_all_modules(
    client: "TelegramClient",
    send_inline: Optional[Callable] = None,
    modules_dir: str = "modules",
) -> int:
    """
    Load all modules from modules directory.

    :param client: Telegram client instance.
    :param send_inline: Function to send inline query.
    :param modules_dir: Modules directory path.
    :return: Number of successfully loaded modules.
    """
    ensure_dir(modules_dir)

    loaded_count = 0

    for file_name in os.listdir(modules_dir):
        if not file_name.endswith(".py"):
            continue

        try:
            file_path = os.path.join(modules_dir, file_name)

            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()

            if not is_module_compatible(code):
                cprint(f"Пропущен несовместимый модуль: {file_name}", Colors.YELLOW)
                continue

            if await load_module_from_file(
                client, file_path, send_inline, modules_dir
            ):
                loaded_count += 1
        except Exception as e:
            cprint(f"Ошибка загрузки {file_name}: {e}", Colors.RED)

    return loaded_count


async def unload_module(
    module_name: str,
    modules_dir: str = "modules",
) -> bool:
    """
    Unload a module by name.

    :param module_name: Name of module to unload.
    :param modules_dir: Modules directory path.
    :return: True if unloaded successfully.
    """
    file_path = os.path.join(modules_dir, f"{module_name}.py")

    if os.path.exists(file_path):
        os.remove(file_path)

    if module_name in sys.modules:
        del sys.modules[module_name]

    if module_name in loaded_modules:
        del loaded_modules[module_name]

    return True


def get_loaded_modules() -> Dict[str, ModuleType]:
    """
    Get all loaded modules.

    :return: Dictionary of loaded modules.
    """
    return loaded_modules.copy()


def get_module_commands(module_name: str, modules_dir: str = "modules") -> list[str]:
    """
    Extract commands from module source code.

    :param module_name: Name of module.
    :param modules_dir: Modules directory path.
    :return: List of command names (without prefix).
    """
    import re

    file_path = os.path.join(modules_dir, f"{module_name}.py")
    if not os.path.exists(file_path):
        return []

    with open(file_path, "r", encoding="utf-8") as f:
        code = f.read()

    # Match patterns like: r'^\.command'
    commands = re.findall(r"pattern=r['\"]\^?\\?\.([a-zA-Z0-9_]+)", code)
    return commands