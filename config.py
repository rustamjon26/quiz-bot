"""Environment configuration. Values come from the process environment or a local .env file."""

from __future__ import annotations

import logging
import os
import re
from typing import NamedTuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

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


def _normalize_site_url(raw: str, default: str = _DEFAULT_SITE_URL) -> str:
    candidate = raw or default
    parsed = urlparse(candidate)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return candidate
    return default


def _handle(raw: str, default: str) -> str:
    value = (raw or default).strip()
    if value and not value.startswith("@"):
        value = f"@{value}"
    return value or default


class Channel(NamedTuple):
    chat: str | int
    title: str
    url: str


_USERNAME_RE = re.compile(r"@[A-Za-z0-9_]{4,32}")
_BARE_USERNAME_RE = re.compile(r"[A-Za-z0-9_]{4,32}")


def _utf16_len(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def _valid_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _username_from_tme(value: str) -> str | None:
    """Public ``https://t.me/username`` links. Invite links (``+`` / joinchat) do not count."""
    parsed = urlparse(value.strip())
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if parsed.scheme not in {"http", "https"} or host not in {"t.me", "telegram.me"}:
        return None
    slug = parsed.path.strip("/")
    if not slug or "/" in slug or slug.startswith("+") or slug.lower() == "joinchat":
        return None
    if _BARE_USERNAME_RE.fullmatch(slug):
        return slug
    return None


def _skip_channel(name: str, entry: str, reason: str) -> None:
    logger.warning("%s: skipping channel entry %r (%s)", name, entry, reason)


def _parse_channel_entry(entry: str) -> Channel | None:
    pieces = [piece.strip() for piece in entry.split("|", 2)]
    chat_raw = pieces[0] if pieces else ""
    title = pieces[1] if len(pieces) > 1 else ""
    url = pieces[2] if len(pieces) > 2 else ""
    if not chat_raw:
        return None

    if len(pieces) == 1:
        slug = _username_from_tme(chat_raw)
        if slug:
            return Channel(f"@{slug}", slug, f"https://t.me/{slug}")
        if _USERNAME_RE.fullmatch(chat_raw):
            name = chat_raw[1:]
            return Channel(chat_raw, name, f"https://t.me/{name}")
        if _BARE_USERNAME_RE.fullmatch(chat_raw):
            return Channel(f"@{chat_raw}", chat_raw, f"https://t.me/{chat_raw}")
        return None

    slug = _username_from_tme(chat_raw)
    if slug:
        chat_raw = f"@{slug}"
        if not url:
            url = f"https://t.me/{slug}"

    if _USERNAME_RE.fullmatch(chat_raw):
        if not title:
            title = chat_raw[1:]
        if _utf16_len(title) > 64 or (url and not _valid_http_url(url)):
            return None
        if not url:
            url = f"https://t.me/{chat_raw[1:]}"
        return Channel(chat_raw, title, url)

    try:
        chat_id = int(chat_raw)
    except ValueError:
        return None
    if not title or _utf16_len(title) > 64 or not url.lower().startswith("https://") or not _valid_http_url(url):
        return None
    return Channel(chat_id, title, url)


def parse_channels(raw: str, name: str = "CHANNELS") -> tuple[Channel, ...]:
    """Parse a channel list. Empty, or every entry skipped, leaves the step off.

    Each comma-separated entry is ``chat|Title``, ``chat|Title|invite_url``,
    a lone ``@username``, or ``https://t.me/username``. A numeric id still
    needs an https invite URL. Bad entries are logged and skipped.
    """
    channels: list[Channel] = []
    for part in raw.split(","):
        entry = part.strip()
        if not entry:
            continue
        try:
            channel = _parse_channel_entry(entry)
        except Exception:
            logger.warning("%s: skipping channel entry %r (could not parse)", name, entry)
            continue
        if channel is None:
            _skip_channel(name, entry, "could not parse")
            continue
        channels.append(channel)
    return tuple(channels)


def channels_for(project: str) -> tuple[Channel, ...]:
    """SafarTrip falls back to CHANNELS. 'both' is the union, first list wins ties."""
    if project == "mendora":
        return CHANNELS_MENDORA
    if project == "both":
        return _union(channels_for("safartrip"), channels_for("mendora"))
    if CHANNELS_SAFARTRIP:
        return CHANNELS_SAFARTRIP
    return CHANNELS


def _union(first: tuple[Channel, ...], second: tuple[Channel, ...]) -> tuple[Channel, ...]:
    seen: set[str | int] = set()
    merged: list[Channel] = []
    for channel in (*first, *second):
        if channel.chat in seen:
            continue
        seen.add(channel.chat)
        merged.append(channel)
    return tuple(merged)


BOT_TOKEN: str = _raw("BOT_TOKEN")
ADMIN_CHAT_ID: int | None = _parse_chat_id(_raw("ADMIN_CHAT_ID"))
ADMIN_IDS: frozenset[int] = _parse_admin_ids(_raw("ADMIN_IDS"))
PROMO_CODE_SAFARTRIP: str = (
    _raw("PROMO_CODE_SAFARTRIP") or _raw("PROMO_CODE", _DEFAULT_PROMO_CODE) or _DEFAULT_PROMO_CODE
)
PROMO_TEXT_SAFARTRIP: str = (
    _raw("PROMO_TEXT_SAFARTRIP") or _raw("PROMO_TEXT", _DEFAULT_PROMO_TEXT) or _DEFAULT_PROMO_TEXT
)
PROMO_CODE_MENDORA: str = _raw("PROMO_CODE_MENDORA")
PROMO_TEXT_MENDORA: str = _raw("PROMO_TEXT_MENDORA")
PROMO_CODE: str = PROMO_CODE_SAFARTRIP
PROMO_TEXT: str = PROMO_TEXT_SAFARTRIP
SITE_URL_SAFARTRIP: str = _normalize_site_url(
    _raw("SITE_URL_SAFARTRIP") or _raw("SITE_URL"),
    "https://safartrip.uz",
)
SITE_URL_MENDORA: str = _normalize_site_url(_raw("SITE_URL_MENDORA"), "https://mendora.tech")
SITE_URL: str = SITE_URL_SAFARTRIP
DB_PATH: str = _raw("DB_PATH", _DEFAULT_DB_PATH) or _DEFAULT_DB_PATH
CHANNELS: tuple[Channel, ...] = parse_channels(_raw("CHANNELS"), "CHANNELS")
CHANNELS_SAFARTRIP: tuple[Channel, ...] = parse_channels(_raw("CHANNELS_SAFARTRIP"), "CHANNELS_SAFARTRIP")
CHANNELS_MENDORA: tuple[Channel, ...] = parse_channels(_raw("CHANNELS_MENDORA"), "CHANNELS_MENDORA")
CONTACT_SAFARTRIP: str = _handle(_raw("CONTACT_SAFARTRIP"), "@anvarovic06")
CONTACT_MENDORA: str = _handle(_raw("CONTACT_MENDORA"), "@sz_2302")


def validate() -> None:
    """Fail fast when the bot cannot start. Never prints the token."""
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is missing. Set it in the environment or in .env.")
    if ":" not in BOT_TOKEN:
        raise SystemExit("BOT_TOKEN does not look like a Telegram bot token.")


def is_admin(user_id: int | None) -> bool:
    return user_id is not None and user_id in ADMIN_IDS
