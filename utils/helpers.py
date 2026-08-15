import re
from urllib.parse import urlparse
from datetime import datetime, timezone


URL_REGEX = re.compile(
    r"(https?://[^\s`<>\"]+)",
    re.IGNORECASE,
)


def extract_urls(text: str) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for match in URL_REGEX.findall(text or ""):
        if match not in seen:
            seen.add(match)
            urls.append(match)
    return urls


def get_hostname(url: str) -> str:
    try:
        parsed = urlparse(url)
        return (parsed.hostname or "").lower()
    except Exception:
        return ""


def is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def format_datetime(dt: datetime | None = None) -> str:
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def truncate(text: str, limit: int = 1000) -> str:
    if text is None:
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def mask_token(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return value[:4] + "***" + value[-4:]
