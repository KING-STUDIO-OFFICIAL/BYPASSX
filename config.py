import os
from dotenv import load_dotenv

load_dotenv()


def _get_env(key: str, default: str = "") -> str:
    value = os.getenv(key)
    if value is None or value == "":
        return default
    return value


DISCORD_TOKEN: str = _get_env("DISCORD_TOKEN", "")
API_BASE_URL: str = _get_env("API_BASE_URL", "http://prem-eu3.bot-hosting.net:21550")
DISCORD_INVITE_URL: str = _get_env("DISCORD_INVITE_URL", "https://discord.gg/example")
PORT: int = int(_get_env("PORT", "3000"))

API_TIMEOUT: int = 15
API_RETRIES: int = 2

BYPASS_ENDPOINT: str = f"{API_BASE_URL}/bypass"
SUPPORTED_ENDPOINT: str = f"{API_BASE_URL}/supported"

CONFIG_FILE: str = "data/config.json"

DEFAULT_DELETE_TIME: int = 60
MIN_DELETE_TIME: int = 25
MAX_DELETE_TIME: int = 250

MIN_SLOWDOWN: int = 0
MAX_SLOWDOWN: int = 60

CONFIRMATION_TIMEOUT: int = 60

EMOJI_CHECKMARK: str = "https://cdn.discordapp.com/emojis/1526851357330505822.webp?size=100"
EMOJI_CONFETTI: str = "https://cdn.discordapp.com/emojis/1526817132501798983.webp?size=100&animated=true"
EMOJI_KEY: str = "https://cdn.discordapp.com/emojis/1525381310200414310.webp?size=100"
EMOJI_TIMER: str = "https://cdn.discordapp.com/emojis/1525380296852377711.webp?size=100&animated=true"
EMOJI_ERROR: str = "https://cdn.discordapp.com/emojis/1526850359958704138.webp?size=100&animated=true"

COLOR_CHOICES = {
    "black": 0x000000,
    "red": 0xFF0000,
    "blue": 0x0000FF,
    "green": 0x00FF00,
    "purple": 0x800080,
    "yellow": 0xFFFF00,
    "orange": 0xFFA500,
    "white": 0xFFFFFF,
}

EMBED_COLOR: int = 0x000000
ERROR_COLOR: int = 0x000000
