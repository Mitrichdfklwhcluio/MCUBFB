"""Theme support for message formatting."""


THEMES: dict = {
    "default": {"success": "✅", "error": "❌", "info": "ℹ️", "warning": "⚠️"},
    "minimal": {"success": "✓", "error": "✗", "info": "i", "warning": "!"},
    "emoji": {"success": "🎉", "error": "💥", "info": "💡", "warning": "⚡"},
}


def theme(key: str) -> str:
    """
    Get theme symbol for a key.

    :param key: Theme key (e.g., 'success', 'error').
    :return: Theme symbol or empty string if not found.
    """
    return THEMES.get(THEME, THEMES["default"]).get(key, "")


#: Current theme (set by config)
THEME: str = "default"