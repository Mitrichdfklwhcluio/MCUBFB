"""Terminal colors and printing utilities."""


class Colors:
    """ANSI color codes for terminal output."""

    RESET: str = '\033[0m'
    RED: str = '\033[91m'
    GREEN: str = '\033[92m'
    YELLOW: str = '\033[93m'
    BLUE: str = '\033[94m'
    PURPLE: str = '\033[95m'
    CYAN: str = '\033[96m'


def cprint(text: str, color: str = "") -> None:
    """
    Print text with optional color.

    :param text: Text to print.
    :param color: ANSI color code (e.g., Colors.RED).
    """
    print(f"{color}{text}{Colors.RESET}")