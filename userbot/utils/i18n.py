"""Internationalization (i18n) support."""


LANGS: dict = {
    "ru": {
        "ping": "Pong!",
        "restart": "Перезагрузка...",
        "update_check": "🔄 Проверка обновлений...",
        "module_installed": "✅ Модуль {} установлен",
        "error": "❌ Ошибка: {}",
    },
    "en": {
        "ping": "Pong!",
        "restart": "Restarting...",
        "update_check": "🔄 Checking updates...",
        "module_installed": "✅ Module {} installed",
        "error": "❌ Error: {}",
    },
}


def t(key: str) -> str:
    """
    Translate a key to the current language.

    :param key: Translation key.
    :return: Translated string or key if not found.
    """
    return LANGS.get(LANGUAGE, LANGS["ru"]).get(key, key)


#: Current language (set by config)
LANGUAGE: str = "ru"