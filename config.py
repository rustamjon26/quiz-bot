"""Environment configuration. Values come from the process environment or a local .env file."""

from __future__ import annotations

import os
import re
from typing import NamedTuple
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

_DEFAULT_PROMO_CODE = "SCHOOL21"
_DEFAULT_PROMO_TEXT = "Birinchi bronga chegirma"
_DEFAULT_SITE_URL = "https://safartrip.uz"
_DEFAULT_DB_PATH = "leads.db"


def _raw(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        value = default
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1].strip()
    return value


def _parse_admin_ids(raw: str) -> frozenset[int]:
    ids: set[int] = set()
    for part in raw.split(","):
        item = part.strip()
        if not item:
            continue
        try:
            ids.add(int(item))
        except ValueError as exc:
            raise SystemExit("ADMIN_IDS must be a comma-separated list of integers") from exc
    return frozenset(ids)


def _parse_chat_id(raw: str) -> int | None:
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise SystemExit("ADMIN_CHAT_ID must be an integer") from exc


def _normalize_site_url(raw: str) -> str:
    candidate = raw or _DEFAULT_SITE_URL
    parsed = urlparse(candidate)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return candidate
    return _DEFAULT_SITE_URL


class Channel(NamedTuple):
    chat: str | int
    title: str
    url: str


_USERNAME_RE = re.compile(r"@[A-Za-z0-9_]{4,32}")


def _utf16_len(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def _valid_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def parse_channels(raw: str) -> tuple[Channel, ...]:
    """Parse CHANNELS. Empty means the subscription step is off.

    Each comma-separated entry is ``chat|Title`` or ``chat|Title|invite_url``.
    ``chat`` is ``@username`` or a numeric id. Titles cannot contain ``|`` or ``,``.
    """
    channels: list[Channel] = []
    for part in raw.split(","):
        entry = part.strip()
        if not entry:
            continue
        pieces = [piece.strip() for piece in entry.split("|", 2)]
        if len(pieces) < 2 or not pieces[0] or not pieces[1]:
            raise SystemExit(
                "CHANNELS entries must look like @channel|Title or -100id|Title|https://t.me/+invite"
            )
        chat_raw, title = pieces[0], pieces[1]
        url = pieces[2] if len(pieces) > 2 else ""
        if _utf16_len(title) > 64:
            raise SystemExit("A CHANNELS title is longer than 64 characters")
        if url and not _valid_http_url(url):
            raise SystemExit("A CHANNELS invite URL must start with http:// or https://")
        if _USERNAME_RE.fullmatch(chat_raw):
            if not url:
                url = f"https://t.me/{chat_raw[1:]}"
            channels.append(Channel(chat_raw, title, url))
            continue
        try:
            chat_id = int(chat_raw)
        except ValueError as exc:
            raise SystemExit(
                "A CHANNELS chat must be @username or a numeric id"
            ) from exc
        if not url:
            raise SystemExit("A numeric CHANNELS chat needs an invite URL")
        channels.append(Channel(chat_id, title, url))
    return tuple(channels)


BOT_TOKEN: str = _raw("BOT_TOKEN")
ADMIN_CHAT_ID: int | None = _parse_chat_id(_raw("ADMIN_CHAT_ID"))
ADMIN_IDS: frozenset[int] = _parse_admin_ids(_raw("ADMIN_IDS"))
PROMO_CODE: str = _raw("PROMO_CODE", _DEFAULT_PROMO_CODE) or _DEFAULT_PROMO_CODE
PROMO_TEXT: str = _raw("PROMO_TEXT", _DEFAULT_PROMO_TEXT) or _DEFAULT_PROMO_TEXT
SITE_URL: str = _normalize_site_url(_raw("SITE_URL", _DEFAULT_SITE_URL))
DB_PATH: str = _raw("DB_PATH", _DEFAULT_DB_PATH) or _DEFAULT_DB_PATH
CHANNELS: tuple[Channel, ...] = parse_channels(_raw("CHANNELS"))


def validate() -> None:
    """Fail fast when the bot cannot start. Never prints the token."""
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is missing. Set it in the environment or in .env.")
    if ":" not in BOT_TOKEN:
        raise SystemExit("BOT_TOKEN does not look like a Telegram bot token.")


def is_admin(user_id: int | None) -> bool:
    return user_id is not None and user_id in ADMIN_IDS
