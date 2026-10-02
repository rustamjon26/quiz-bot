"""All user-facing copy. Edit wording here; keep button labels within Telegram's 64-character limit."""

from __future__ import annotations

import html
import re

ROLE_TRAVELER = "traveler"
ROLE_OWNER = "owner"
ROLE_GUIDE = "guide"
ROLES = (ROLE_TRAVELER, ROLE_OWNER, ROLE_GUIDE)

ROLE_LABELS = {
    ROLE_TRAVELER: "✈️ Sayohatchi",
    ROLE_OWNER: "🏡 Joy egasi",
    ROLE_GUIDE: "🧭 Gid",
}

BTN_TRAVELER = "✈️ Sayohatchiman"
BTN_OWNER = "🏡 Joyim bor (mehmon uyi, dacha, mehmonxona)"
BTN_GUIDE = "🧭 Gidman"
BTN_SHARE_PHONE = "📱 Raqamni yuborish"
BTN_SITE = "🌐 safartrip.uz"
BTN_CHECK = "✅ Tekshirish"

FOUNDER_URL = "https://t.me/anvarovic06"
FOUNDER_HANDLE = "@anvarovic06"

GREETING = (
    "Assalomu alaykum! SafarTrip'ga xush kelibsiz 👋\n"
    "Quyidagilardan birini tanlang:"
)
ASK_NAME = "Ismingiz nima?"
NAME_INVALID = "Ismingizni 2–60 ta belgi oralig'ida yozing."
ASK_PHONE = "Bog'lanishimiz uchun telefon raqamingizni pastdagi tugma orqali yuboring."
PHONE_NEED_BUTTON = "Iltimos, «📱 Raqamni yuborish» tugmasini bosing."
PHONE_WRONG = "Iltimos, o'zingizning raqamingizni yuboring — pastdagi tugmani bosing."
CANCELLED = "Bekor qilindi. Qayta boshlash uchun /start ni bosing."
UNKNOWN = "Boshlash uchun /start ni bosing."
IN_FLOW_UNKNOWN = "Tushunmadim. So'ralgan ma'lumotni yuboring yoki /start ni bosing."
ERROR = "Xatolik yuz berdi. Iltimos, /start ni qayta bosing."
SITE_HINT = "Saytga o'tish:"
SUBSCRIBE_PROMPT = (
    "Deyarli tayyor! Quyidagi kanallarga obuna bo'ling, "
    "so'ng «✅ Tekshirish» tugmasini bosing 👇"
)
SUB_HINT = "Kanallarga obuna bo'ling va «✅ Tekshirish» tugmasini bosing."
SUBSCRIBED_OK = "Obuna tasdiqlandi. Rahmat! ✅"
_ALERT_LIMIT = 200

_USERNAME_RE = re.compile(r"[A-Za-z0-9_]{4,32}")


def _founder_line() -> str:
    return (
        f'Savollar bo\'lsa, asoschiga yozing: '
        f'<a href="{FOUNDER_URL}">{FOUNDER_HANDLE}</a>'
    )


def thanks_traveler(name: str, promo_code: str, promo_text: str) -> str:
    return (
        f"Rahmat, <b>{html.escape(name)}</b>! 🎉\n\n"
        f"Promo-kod: <code>{html.escape(promo_code)}</code>\n"
        f"{html.escape(promo_text)}\n\n"
        f"{_founder_line()}"
    )


def thanks_owner(name: str) -> str:
    return (
        f"Rahmat, <b>{html.escape(name)}</b>! 🏡\n\n"
        "SafarTrip jamoasi tez orada siz bilan bog'lanadi va joyingizni qo'shadi.\n\n"
        f"{_founder_line()}"
    )


def thanks_guide(name: str) -> str:
    return (
        f"Rahmat, <b>{html.escape(name)}</b>! 🧭\n\n"
        "SafarTrip jamoasi tez orada siz bilan bog'lanadi va sizni gidlar ro'yxatiga qo'shadi.\n\n"
        f"{_founder_line()}"
    )


def missing_channels_alert(titles: list[str]) -> str:
    text = "Hali obuna bo'lmadingiz: " + ", ".join(titles)
    if len(text) <= _ALERT_LIMIT:
        return text
    return text[: _ALERT_LIMIT - 1] + "…"


def admin_subscribed(name: str) -> str:
    return f"✅ {html.escape(name)} kanallarga obuna bo'ldi"


def admin_channel_error(title: str) -> str:
    return (
        f"⚠️ {html.escape(title)} tekshirib bo'lmadi: "
        "bot kanalga admin emas yoki ID noto'g'ri"
    )


def thanks_for(role: str, name: str, promo_code: str, promo_text: str) -> str:
    if role == ROLE_TRAVELER:
        return thanks_traveler(name, promo_code, promo_text)
    if role == ROLE_OWNER:
        return thanks_owner(name)
    if role == ROLE_GUIDE:
        return thanks_guide(name)
    return thanks_traveler(name, promo_code, promo_text)


def admin_lead(
    *,
    is_new: bool,
    role: str,
    full_name: str,
    username: str | None,
    phone: str | None,
    source: str,
    when: str,
) -> str:
    header = "🆕 <b>Yangi ariza</b>" if is_new else "♻️ <b>Ariza yangilandi</b>"
    role_line = ROLE_LABELS.get(role, html.escape(role))
    return (
        f"{header}\n\n"
        f"{role_line}\n"
        f"👤 {html.escape(full_name)}\n"
        f"📞 {_contact_html(username, phone)}\n"
        f"📍 {html.escape(source)}\n"
        f"🕐 {html.escape(when)}"
    )


def _contact_html(username: str | None, phone: str | None) -> str:
    if username and _USERNAME_RE.fullmatch(username):
        safe = html.escape(username)
        return f'<a href="https://t.me/{safe}">@{safe}</a>'
    if phone:
        return html.escape(phone)
    return "—"


def stats_message(
    total: int,
    today: int,
    by_role: list[tuple[str, int]],
    by_source: list[tuple[str, int]],
    subscribed: int = 0,
) -> str:
    percent = round(subscribed * 100 / total) if total else 0
    lines = [
        "📊 <b>Statistika</b>",
        "",
        f"Jami: <b>{total}</b>",
        f"Bugun: <b>{today}</b>",
        f"Obuna: <b>{subscribed}</b> ({percent}%)",
        "",
        "<b>Rollar</b>",
    ]
    if by_role:
        rank = {role: index for index, role in enumerate(ROLES)}
        ordered = sorted(by_role, key=lambda item: (rank.get(item[0], 99), item[0] or ""))
        for role, count in ordered:
            label = ROLE_LABELS.get(role, html.escape(role or "—"))
            lines.append(f"{label} — {count}")
    else:
        lines.append("—")
    lines.append("")
    lines.append("<b>Manbalar</b>")
    if by_source:
        for source, count in by_source:
            lines.append(f"{html.escape(source or '—')} — {count}")
    else:
        lines.append("—")
    lines.append("")
    lines.append("Bugun — Toshkent vaqti bilan.")
    return "\n".join(lines)


def export_caption(count: int) -> str:
    return f"Barcha arizalar: {count} ta."
