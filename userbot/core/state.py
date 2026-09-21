"""Shared runtime state for the userbot."""

class State:

    def __init__(self) -> None:
        self.catalog_cache: dict = {}
        self.pending_confirmations: dict = {}
        self.inline_client = None  # Optional[TelegramClient]

state = State()