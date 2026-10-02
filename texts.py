"""All user-facing copy. Edit wording here; keep button labels within Telegram's 64-character limit."""

from __future__ import annotations

import html
import re

ROLE_TRAVELER = "traveler"
ROLE_OWNER = "owner"
ROLE_GUIDE = "guide"
ROLE_TEACHER = "teacher"
ROLE_SCHOOL_OWNER = "school_owner"
ROLE_STUDENT = "student"
SAFAR_ROLES = (ROLE_TRAVELER, ROLE_OWNER, ROLE_GUIDE)
MENDORA_ROLES = (ROLE_TEACHER, ROLE_SCHOOL_OWNER, ROLE_STUDENT)
ROLES = SAFAR_ROLES

PROJECT_SAFARTRIP = "safartrip"
PROJECT_MENDORA = "mendora"
PROJECT_BOTH = "both"
PROJECT_LABELS = {
    PROJECT_SAFARTRIP: "🌍 SafarTrip",
    PROJECT_MENDORA: "🎓 Mendora",
}

ROLE_LABELS = {
    ROLE_TRAVELER: "✈️ Sayohatchi",
    ROLE_OWNER: "🏡 Joy egasi",
    ROLE_GUIDE: "🧭 Gid",
    ROLE_TEACHER: "👩‍🏫 O'qituvchi",
    ROLE_SCHOOL_OWNER: "🏫 Rahbar",
    ROLE_STUDENT: "🎓 Talaba",
}

BTN_TRAVELER = "✈️ Sayohatchiman"
BTN_OWNER = "🏡 Joyim bor (mehmon uyi, dacha, mehmonxona)"
BTN_GUIDE = "🧭 Gidman"
BTN_TEACHER = "👩‍🏫 O'qituvchiman"
BTN_SCHOOL_OWNER = "🏫 Maktab yoki o'quv markaz rahbariman"
BTN_STUDENT = "🎓 Talaba / boshqa"
BTN_PROJECT_SAFARTRIP = "✈️ SafarTrip (sayohat)"
BTN_PROJECT_MENDORA = "🎓 Mendora (o'qituvchilar uchun AI)"
BTN_PROJECT_BOTH = "✨ Ikkalasi ham qiziq"
BTN_SHARE_PHONE = "📱 Raqamni yuborish"
BTN_SITE = "🌐 safartrip.uz"
BTN_SITE_MENDORA = "🌐 mendora.tech"
BTN_CHECK = "✅ Tekshirish"

FOUNDER_URL = "https://t.me/anvarovic06"
FOUNDER_HANDLE = "@anvarovic06"

GREETING = (
    "Assalomu alaykum! SafarTrip'ga xush kelibsiz 👋\n"
    "Quyidagilardan birini tanlang:"
)
GREETING_MENDORA = (
    "Mendora'ga xush kelibsiz! 🎓\n"
    "Quyidagilardan birini tanlang:"
)
PICK_PROJECT = "Qaysi loyiha qiziq? Quyidagilardan birini tanlang:"
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


def roles_for(project: str) -> tuple[str, ...]:
    if project == PROJECT_MENDORA:
        return MENDORA_ROLES
    return SAFAR_ROLES


def project_label(project: str) -> str:
    return PROJECT_LABELS.get(project, html.escape(project))


def _contact_line(handle: str, *, founder: bool) -> str:
    username = handle[1:] if handle.startswith("@") else handle
    shown = handle if handle.startswith("@") else f"@{handle}"
    label = "Savollar bo'lsa, asoschiga yozing" if founder else "Savollar bo'lsa, yozing"
    return (
        f"{label}: "
        f'<a href="https://t.me/{html.escape(username)}">{html.escape(shown)}</a>'
    )


def _founder_line(contact: str | None = None) -> str:
    handle = contact or FOUNDER_HANDLE
    if handle == FOUNDER_HANDLE:
        return (
            "Savollar bo'lsa, asoschiga yozing: "
            f'<a href="{FOUNDER_URL}">{FOUNDER_HANDLE}</a>'
        )
    return _contact_line(handle, founder=True)


def thanks_traveler(
    name: str,
    promo_code: str,
    promo_text: str,
    contact: str | None = None,
) -> str:
    return (
        f"Rahmat, <b>{html.escape(name)}</b>! 🎉\n\n"
        f"Promo-kod: <code>{html.escape(promo_code)}</code>\n"
        f"{html.escape(promo_text)}\n\n"
        f"{_founder_line(contact)}"
    )


def thanks_owner(name: str, contact: str | None = None) -> str:
    return (
        f"Rahmat, <b>{html.escape(name)}</b>! 🏡\n\n"
        "SafarTrip jamoasi tez orada siz bilan bog'lanadi va joyingizni qo'shadi.\n\n"
        f"{_founder_line(contact)}"
    )


def thanks_guide(name: str, contact: str | None = None) -> str:
    return (
        f"Rahmat, <b>{html.escape(name)}</b>! 🧭\n\n"
        "SafarTrip jamoasi tez orada siz bilan bog'lanadi va sizni gidlar ro'yxatiga qo'shadi.\n\n"
        f"{_founder_line(contact)}"
    )


def thanks_mendora(
    name: str,
    role: str,
    promo_code: str,
    promo_text: str,
    contact: str,
) -> str:
    lines = [
        f"Rahmat, <b>{html.escape(name)}</b>! 🎓",
        "",
        "Mendora'da dars rejasi, taqdimot, test va jonli viktorina bir joyda.",
    ]
    if role == ROLE_SCHOOL_OWNER:
        lines.append("Jamoamiz siz bilan bog'lanadi.")
    if promo_code:
        lines.append("")
        lines.append(f"Promo-kod: <code>{html.escape(promo_code)}</code>")
        if promo_text:
            lines.append(html.escape(promo_text))
    lines.append("")
    lines.append(_contact_line(contact, founder=False))
    return "\n".join(lines)


def missing_channels_alert(titles: list[str]) -> str:
    text = "Hali obuna bo'lmadingiz: " + ", ".join(titles)
    if len(text) <= _ALERT_LIMIT:
        return text
    return text[: _ALERT_LIMIT - 1] + "…"


def admin_subscribed(name: str, project: str = PROJECT_SAFARTRIP) -> str:
    return (
        f"✅ {html.escape(name)} kanallarga obuna bo'ldi · {project_label(project)}"
    )


def admin_channel_error(title: str) -> str:
    return (
        f"⚠️ {html.escape(title)} tekshirib bo'lmadi: "
        "bot kanalga admin emas yoki ID noto'g'ri"
    )


def thanks_for(
    role: str,
    name: str,
    promo_code: str,
    promo_text: str,
    contact: str | None = None,
) -> str:
    if role == ROLE_TRAVELER:
        return thanks_traveler(name, promo_code, promo_text, contact)
    if role == ROLE_OWNER:
        return thanks_owner(name, contact)
    if role == ROLE_GUIDE:
        return thanks_guide(name, contact)
    return thanks_traveler(name, promo_code, promo_text, contact)


def thanks_both(
    *,
    name: str,
    safar_role: str,
    mendora_role: str,
    safar_promo: str,
    safar_promo_text: str,
    mendora_promo: str,
    mendora_promo_text: str,
    contact_safar: str,
    contact_mendora: str,
) -> str:
    safar = thanks_for(safar_role, name, safar_promo, safar_promo_text, contact_safar)
    mendora = thanks_mendora(
        name, mendora_role, mendora_promo, mendora_promo_text, contact_mendora
    )
    return f"{safar}\n\n{mendora}"


def admin_lead(
    *,
    is_new: bool,
    role: str,
    full_name: str,
    username: str | None,
    phone: str | None,
    source: str,
    when: str,
    project: str = PROJECT_SAFARTRIP,
) -> str:
    header = "🆕 <b>Yangi ariza</b>" if is_new else "♻️ <b>Ariza yangilandi</b>"
    role_line = ROLE_LABELS.get(role, html.escape(role))
    return (
        f"{header}\n\n"
        f"{project_label(project)}\n"
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


def _count_lines(project: str, pairs: list[tuple[str, int]], *, roles: bool) -> list[str]:
    if not pairs:
        return ["—"]
    if roles:
        rank = {role: index for index, role in enumerate(roles_for(project))}
        ordered = sorted(pairs, key=lambda item: (rank.get(item[0], 99), item[0] or ""))
        return [
            f"{ROLE_LABELS.get(role, html.escape(role or '—'))} — {count}"
            for role, count in ordered
        ]
    return [f"{html.escape(source or '—')} — {count}" for source, count in pairs]


def stats_message(
    total: int,
    today: int,
    by_role: list[tuple[str, int]],
    by_source: list[tuple[str, int]],
    subscribed: int = 0,
    projects: list[dict] | None = None,
) -> str:
    percent = round(subscribed * 100 / total) if total else 0
    lines = [
        "📊 <b>Statistika</b>",
        "",
        f"Jami: <b>{total}</b>",
        f"Bugun: <b>{today}</b>",
        f"Obuna: <b>{subscribed}</b> ({percent}%)",
    ]
    sections = projects
    if sections is None:
        sections = [
            {
                "project": PROJECT_SAFARTRIP,
                "total": total,
                "subscribed": subscribed,
                "by_role": by_role,
                "by_source": by_source,
            }
        ] if total else []
    if not sections:
        lines.append("")
        lines.append("Hali ariza yo'q.")
    for item in sections:
        project = item["project"]
        item_total = item["total"]
        item_subscribed = item["subscribed"]
        item_percent = round(item_subscribed * 100 / item_total) if item_total else 0
        lines.append("")
        lines.append(f"<b>{project_label(project)}</b>")
        lines.append(f"Jami: <b>{item_total}</b>")
        lines.append(f"Obuna: <b>{item_subscribed}</b> ({item_percent}%)")
        lines.append("<b>Rollar</b>")
        lines.extend(_count_lines(project, item["by_role"], roles=True))
        lines.append("<b>Manbalar</b>")
        lines.extend(_count_lines(project, item["by_source"], roles=False))
    lines.append("")
    lines.append("Bugun — Toshkent vaqti bilan.")
    return "\n".join(lines)


def export_caption(count: int) -> str:
    return f"Barcha arizalar: {count} ta."
