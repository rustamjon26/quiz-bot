"""SafarTrip Telegram lead bot. Polling mode for a Render Background Worker."""

from __future__ import annotations

import logging
import re
import sys
import time
import traceback
import warnings
from datetime import datetime, timedelta, timezone

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import ChatType, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.warnings import PTBUserWarning

import config
import db
import texts

logger = logging.getLogger(__name__)

# Uzbekistan does not observe daylight saving time.
TASHKENT = timezone(timedelta(hours=5))
_UTC_FMT = "%Y-%m-%dT%H:%M:%SZ"
_SOURCE_RE = re.compile(r"^[a-z0-9_-]{1,64}$")

CHOOSING_ROLE, ASKING_NAME, ASKING_PHONE, AWAITING_SUB = range(4)
_SUBSCRIBED_STATUSES = {"member", "administrator", "creator"}
_WARN_INTERVAL = 3600.0
_channel_warn_at: dict[str, float] = {}

# Expected when role buttons live inside a per-chat conversation.
warnings.filterwarnings(
    "ignore",
    message=r".*per_message=False.*CallbackQueryHandler.*",
    category=PTBUserWarning,
)


class _RedactFormatter(logging.Formatter):
    def __init__(self, fmt: str, secrets: list[str]) -> None:
        super().__init__(fmt)
        self._secrets = [secret for secret in secrets if secret]

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        for secret in self._secrets:
            text = text.replace(secret, "***")
        return text


def _configure_logging() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        _RedactFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            [config.BOT_TOKEN],
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def _redact(text: str) -> str:
    if config.BOT_TOKEN:
        return text.replace(config.BOT_TOKEN, "***")
    return text


def normalize_source(payload: str | None, previous: str | None = None) -> str:
    """Use a valid deep-link payload. Otherwise keep the stored source, else 'direct'."""
    if payload:
        cleaned = payload.strip().lower()
        if _SOURCE_RE.fullmatch(cleaned):
            return cleaned
        logger.warning("Ignoring invalid /start payload")
    if previous:
        return previous
    return "direct"


def normalize_name(raw: str) -> str | None:
    name = " ".join(raw.split())
    if len(name) < 2 or len(name) > 60:
        return None
    return name


def _tg_name(user) -> str:
    parts = [user.first_name or "", user.last_name or ""]
    return " ".join(part for part in parts if part).strip()


def _today_bounds_utc() -> tuple[str, str]:
    now = datetime.now(TASHKENT)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return (
        start.astimezone(timezone.utc).strftime(_UTC_FMT),
        end.astimezone(timezone.utc).strftime(_UTC_FMT),
    )


def _format_tashkent(utc_stamp: str) -> str:
    moment = datetime.strptime(utc_stamp, _UTC_FMT).replace(tzinfo=timezone.utc)
    return moment.astimezone(TASHKENT).strftime("%d.%m.%Y %H:%M") + " (Toshkent)"


def _role_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(texts.BTN_TRAVELER, callback_data=f"role:{texts.ROLE_TRAVELER}")],
            [InlineKeyboardButton(texts.BTN_OWNER, callback_data=f"role:{texts.ROLE_OWNER}")],
            [InlineKeyboardButton(texts.BTN_GUIDE, callback_data=f"role:{texts.ROLE_GUIDE}")],
        ]
    )


def _phone_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(texts.BTN_SHARE_PHONE, request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def _site_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(texts.BTN_SITE, url=config.SITE_URL)]]
    )


def _set_state(context: ContextTypes.DEFAULT_TYPE, state: int) -> None:
    context.user_data["state"] = state


def reset_channel_warnings() -> None:
    _channel_warn_at.clear()


def membership_satisfies(member: object) -> bool:
    """Subscribed when status is member/admin/creator, or restricted and still a member."""
    status = getattr(member, "status", None)
    if hasattr(status, "value"):
        status = status.value
    status = str(status or "")
    if status in _SUBSCRIBED_STATUSES:
        return True
    return status == "restricted" and getattr(member, "is_member", False) is True


def _subscribe_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(channel.title, url=channel.url)]
        for channel in config.CHANNELS
    ]
    rows.append([InlineKeyboardButton(texts.BTN_CHECK, callback_data="sub:check")])
    return InlineKeyboardMarkup(rows)


async def check_subscriptions(bot, user_id: int) -> list[str]:
    """Return titles the user still needs to join. A failed lookup counts as joined."""
    missing: list[str] = []
    for channel in config.CHANNELS:
        try:
            member = await bot.get_chat_member(channel.chat, user_id)
        except Exception as exc:
            logger.error(
                "Channel check failed chat=%s: %s",
                channel.chat,
                _redact(f"{type(exc).__name__}: {exc}"),
            )
            await _warn_channel_once(bot, channel)
            continue
        if not membership_satisfies(member):
            missing.append(channel.title)
    return missing


async def _warn_channel_once(bot, channel) -> None:
    key = str(channel.chat)
    now = time.monotonic()
    last = _channel_warn_at.get(key)
    if last is not None and now - last < _WARN_INTERVAL:
        return
    _channel_warn_at[key] = now
    if config.ADMIN_CHAT_ID is None:
        return
    try:
        await bot.send_message(
            chat_id=config.ADMIN_CHAT_ID,
            text=texts.admin_channel_error(channel.title),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as exc:
        logger.error("Channel warning failed: %s", _redact(f"{type(exc).__name__}: {exc}"))


async def _prompt_subscribe(message, *, remove_keyboard: bool) -> None:
    markup = _subscribe_keyboard()
    if not remove_keyboard:
        await message.reply_text(texts.SUBSCRIBE_PROMPT, reply_markup=markup)
        return
    sent = await message.reply_text(
        texts.SUBSCRIBE_PROMPT,
        reply_markup=ReplyKeyboardRemove(),
    )
    try:
        await sent.edit_reply_markup(reply_markup=markup)
    except Exception as exc:
        logger.error(
            "Could not attach channel buttons: %s",
            _redact(f"{type(exc).__name__}: {exc}"),
        )
        await message.reply_text(texts.SUBSCRIBE_PROMPT, reply_markup=markup)


async def _notify_subscribed(context: ContextTypes.DEFAULT_TYPE, name: str) -> None:
    if config.ADMIN_CHAT_ID is None:
        return
    try:
        await context.bot.send_message(
            chat_id=config.ADMIN_CHAT_ID,
            text=texts.admin_subscribed(name),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as exc:
        logger.error("Subscription note failed: %s", _redact(f"{type(exc).__name__}: {exc}"))


def _complete_lead(row: dict | None) -> bool:
    return bool(
        row
        and row.get("subscribed")
        and row.get("full_name")
        and row.get("role") in texts.ROLES
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat = update.effective_chat
    message = update.effective_message
    user = update.effective_user
    if chat is None or chat.type != ChatType.PRIVATE or message is None or user is None:
        return ConversationHandler.END

    payload = context.args[0] if context.args else None
    previous = None
    try:
        existing = db.get_lead(user.id)
    except Exception:
        logger.exception("Could not read lead telegram_id=%s", user.id)
        existing = None
    if existing:
        previous = existing.get("source")

    if config.CHANNELS and _complete_lead(existing):
        return await _recheck_returning(message, context, existing, user.id)

    context.user_data.clear()
    context.user_data["source"] = normalize_source(payload, previous)
    _set_state(context, CHOOSING_ROLE)
    await message.reply_text(texts.GREETING, reply_markup=_role_keyboard())
    return CHOOSING_ROLE


async def _recheck_returning(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    existing: dict,
    user_id: int,
) -> int:
    """Subscribed guests skip the form. A failed re-check shows the channel step again."""
    role = existing["role"]
    name = existing["full_name"]
    context.user_data.clear()
    context.user_data["role"] = role
    context.user_data["full_name"] = name
    context.user_data["source"] = existing.get("source") or "direct"
    try:
        missing = await check_subscriptions(context.bot, user_id)
    except Exception:
        logger.exception("Subscription re-check failed telegram_id=%s", user_id)
        missing = []
    if not missing:
        try:
            await _deliver_thanks(message, role, name, remove_keyboard=False)
        except Exception:
            logger.error("Thank-you message failed:\n%s", _redact(traceback.format_exc()))
            await message.reply_text(texts.ERROR)
        context.user_data.clear()
        return ConversationHandler.END
    try:
        db.clear_subscription(user_id)
    except Exception:
        logger.exception("Could not clear subscription telegram_id=%s", user_id)
    _set_state(context, AWAITING_SUB)
    await _prompt_subscribe(message, remove_keyboard=False)
    return AWAITING_SUB


async def on_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.data is None:
        return CHOOSING_ROLE
    await query.answer()
    role = query.data.split(":", 1)[1]
    if role not in texts.ROLES:
        _set_state(context, CHOOSING_ROLE)
        return CHOOSING_ROLE
    context.user_data["role"] = role
    _set_state(context, ASKING_NAME)
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        logger.info("Role keyboard was already cleared")
    if query.message is not None:
        await query.message.reply_text(texts.ASK_NAME, reply_markup=ReplyKeyboardRemove())
    return ASKING_NAME


async def on_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    user = update.effective_user
    if message is None or message.text is None or user is None:
        return ASKING_NAME
    name = normalize_name(message.text)
    if name is None:
        await message.reply_text(texts.NAME_INVALID)
        return ASKING_NAME
    context.user_data["full_name"] = name
    if user.username:
        return await _finish(update, context, phone=None, remove_keyboard=False)
    _set_state(context, ASKING_PHONE)
    await message.reply_text(texts.ASK_PHONE, reply_markup=_phone_keyboard())
    return ASKING_PHONE


async def on_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    user = update.effective_user
    if message is None or message.contact is None or user is None:
        return ASKING_PHONE
    contact = message.contact
    if contact.user_id != user.id:
        await message.reply_text(texts.PHONE_WRONG)
        return ASKING_PHONE
    phone = (contact.phone_number or "").strip()
    if not phone:
        await message.reply_text(texts.PHONE_NEED_BUTTON)
        return ASKING_PHONE
    return await _finish(update, context, phone=phone, remove_keyboard=True)


async def on_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return AWAITING_SUB
    role = context.user_data.get("role")
    name = context.user_data.get("full_name")
    if role not in texts.ROLES or not name:
        await query.answer()
        if query.message is not None:
            await query.message.reply_text(texts.ERROR)
        context.user_data.clear()
        return ConversationHandler.END
    try:
        missing = await check_subscriptions(context.bot, user.id)
    except Exception:
        logger.exception("Subscription check failed telegram_id=%s", user.id)
        missing = []
    if missing:
        await query.answer(texts.missing_channels_alert(missing), show_alert=True)
        return AWAITING_SUB
    await query.answer()
    try:
        if db.mark_subscribed(user.id):
            await _notify_subscribed(context, name)
    except Exception:
        logger.exception("Could not mark subscription telegram_id=%s", user.id)
    if query.message is not None:
        try:
            await query.edit_message_text(
                texts.SUBSCRIBED_OK,
                reply_markup=InlineKeyboardMarkup([]),
            )
        except Exception:
            logger.info("Could not edit the subscription message")
        try:
            await _deliver_thanks(query.message, role, name, remove_keyboard=False)
        except Exception:
            logger.error("Thank-you message failed:\n%s", _redact(traceback.format_exc()))
            await query.message.reply_text(texts.ERROR)
    context.user_data.clear()
    return ConversationHandler.END


async def on_check_outside(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Answer a Tekshirish tap that arrives after the conversation already ended."""
    if update.callback_query is not None:
        await update.callback_query.answer()


async def on_phone_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is not None:
        await update.message.reply_text(texts.PHONE_NEED_BUTTON)
    return ASKING_PHONE


async def _finish(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    phone: str | None,
    remove_keyboard: bool,
) -> int:
    message = update.effective_message
    user = update.effective_user
    role = context.user_data.get("role")
    name = context.user_data.get("full_name")
    source = context.user_data.get("source") or "direct"
    if message is None or user is None or role not in texts.ROLES or not name:
        if message is not None:
            await message.reply_text(texts.ERROR)
        context.user_data.clear()
        return ConversationHandler.END

    try:
        is_new, updated_at = db.upsert_lead(
            telegram_id=user.id,
            username=user.username,
            full_name=name,
            tg_name=_tg_name(user),
            phone=phone,
            role=role,
            source=source,
        )
    except Exception:
        logger.exception("Could not save lead telegram_id=%s", user.id)
        await message.reply_text(texts.ERROR)
        context.user_data.clear()
        return ConversationHandler.END

    logger.info(
        "Saved lead telegram_id=%s role=%s source=%s new=%s",
        user.id,
        role,
        source,
        is_new,
    )
    await _notify_admin(
        context,
        is_new=is_new,
        role=role,
        full_name=name,
        username=user.username,
        phone=phone,
        source=source,
        updated_at=updated_at,
    )
    if config.CHANNELS:
        _set_state(context, AWAITING_SUB)
        try:
            await _prompt_subscribe(message, remove_keyboard=remove_keyboard)
        except Exception:
            logger.error("Subscription prompt failed:\n%s", _redact(traceback.format_exc()))
            await message.reply_text(texts.ERROR)
            context.user_data.clear()
            return ConversationHandler.END
        return AWAITING_SUB
    try:
        await _deliver_thanks(message, role, name, remove_keyboard=remove_keyboard)
    except Exception:
        logger.error("Thank-you message failed:\n%s", _redact(traceback.format_exc()))
        try:
            await message.reply_text(texts.ERROR)
        except Exception:
            logger.error("Could not send the fallback error reply")
    context.user_data.clear()
    return ConversationHandler.END


async def _deliver_thanks(message, role: str, name: str, *, remove_keyboard: bool) -> None:
    text = texts.thanks_for(role, name, config.PROMO_CODE, config.PROMO_TEXT)
    preview = {"disable_web_page_preview": True}
    if remove_keyboard:
        await message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=ReplyKeyboardRemove(),
            **preview,
        )
        try:
            await message.reply_text(texts.SITE_HINT, reply_markup=_site_keyboard())
        except Exception as exc:
            logger.error("Site button failed: %s", _redact(f"{type(exc).__name__}: {exc}"))
        return
    await message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=_site_keyboard(),
        **preview,
    )


async def _notify_admin(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    is_new: bool,
    role: str,
    full_name: str,
    username: str | None,
    phone: str | None,
    source: str,
    updated_at: str,
) -> None:
    if config.ADMIN_CHAT_ID is None:
        return
    text = texts.admin_lead(
        is_new=is_new,
        role=role,
        full_name=full_name,
        username=username,
        phone=phone,
        source=source,
        when=_format_tashkent(updated_at),
    )
    try:
        await context.bot.send_message(
            chat_id=config.ADMIN_CHAT_ID,
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as exc:
        logger.error("Admin notification failed: %s", _redact(f"{type(exc).__name__}: {exc}"))


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    message = update.effective_message
    if message is not None:
        await message.reply_text(texts.CANCELLED, reply_markup=ReplyKeyboardRemove())
    elif update.callback_query is not None:
        await update.callback_query.answer()
    return ConversationHandler.END


async def on_unexpected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is not None:
        await query.answer()
    elif (
        update.effective_message is not None
        and update.effective_chat is not None
        and update.effective_chat.type == ChatType.PRIVATE
    ):
        hint = texts.SUB_HINT if context.user_data.get("state") == AWAITING_SUB else texts.IN_FLOW_UNKNOWN
        await update.effective_message.reply_text(hint)
    state = context.user_data.get("state", CHOOSING_ROLE)
    return state if isinstance(state, int) else CHOOSING_ROLE


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_admin(update.effective_user.id if update.effective_user else None):
        return
    message = update.effective_message
    if message is None:
        return
    start_utc, end_utc = _today_bounds_utc()
    data = db.stats(start_utc, end_utc)
    await message.reply_text(
        texts.stats_message(
            data["total"],
            data["today"],
            data["by_role"],
            data["by_source"],
            subscribed=data["subscribed"],
        ),
        parse_mode=ParseMode.HTML,
    )


async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_admin(update.effective_user.id if update.effective_user else None):
        return
    message = update.effective_message
    if message is None:
        return
    try:
        payload, count = db.export_csv()
        await message.reply_document(
            document=InputFile(payload, filename="safartrip_leads.csv"),
            caption=texts.export_caption(count),
        )
    except Exception as exc:
        logger.error("CSV export failed: %s", _redact(f"{type(exc).__name__}: {exc}"))
        await message.reply_text(texts.ERROR)


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    message = update.effective_message
    if chat is None or chat.type != ChatType.PRIVATE or message is None:
        return
    await message.reply_text(texts.UNKNOWN)


def _error_text(context_error: BaseException | None) -> str:
    if context_error is None:
        return "unknown"
    rendered = "".join(
        traceback.format_exception(type(context_error), context_error, context_error.__traceback__)
    )
    return _redact(rendered)


def _user_id(update: object) -> int | None:
    if isinstance(update, Update) and update.effective_user is not None:
        return update.effective_user.id
    return None


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled error user_id=%s\n%s", _user_id(update), _error_text(context.error))
    if not isinstance(update, Update):
        return
    chat = update.effective_chat
    message = update.effective_message
    if chat is None or chat.type != ChatType.PRIVATE or message is None:
        return
    try:
        await message.reply_text(texts.ERROR)
    except Exception:
        logger.error("Could not send the error reply")


def build_application() -> Application:
    role_handler = CallbackQueryHandler(on_role, pattern=r"^role:(traveler|owner|guide)$")
    conversation = ConversationHandler(
        entry_points=[CommandHandler("start", start, filters=filters.ChatType.PRIVATE)],
        states={
            CHOOSING_ROLE: [role_handler],
            ASKING_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, on_name),
                role_handler,
            ],
            ASKING_PHONE: [
                MessageHandler(filters.CONTACT, on_phone),
                MessageHandler(filters.TEXT & ~filters.COMMAND, on_phone_text),
                role_handler,
            ],
            AWAITING_SUB: [
                CallbackQueryHandler(on_check, pattern=r"^sub:check$"),
            ],
        },
        fallbacks=[
            CommandHandler("start", start, filters=filters.ChatType.PRIVATE),
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(on_unexpected),
            MessageHandler(filters.ALL, on_unexpected),
        ],
        allow_reentry=True,
        per_message=False,
    )
    application = Application.builder().token(config.BOT_TOKEN).build()
    application.add_handler(CommandHandler("stats", stats_cmd))
    application.add_handler(CommandHandler("export", export_cmd))
    application.add_handler(conversation)
    application.add_handler(CallbackQueryHandler(on_check_outside, pattern=r"^sub:check$"))
    application.add_handler(MessageHandler(filters.ALL, unknown))
    application.add_error_handler(on_error)
    return application


def main() -> None:
    _configure_logging()
    logger.info("Python %s", sys.version)
    if sys.version_info[:2] < (3, 10) or sys.version_info[:2] > (3, 12):
        logger.warning("Unsupported Python version, expected 3.11")
    config.validate()
    db.init_db(config.DB_PATH)
    if config.ADMIN_CHAT_ID is None:
        logger.warning("ADMIN_CHAT_ID is empty; new leads will not be forwarded")
    if not config.ADMIN_IDS:
        logger.warning("ADMIN_IDS is empty; /stats and /export are disabled")
    if config.CHANNELS:
        logger.info(
            "Subscription channels: %s",
            ", ".join(channel.title for channel in config.CHANNELS),
        )
    else:
        logger.info("Subscription step is off")
    logger.info("SafarTrip lead bot is polling")
    build_application().run_polling(
        allowed_updates=[Update.MESSAGE, Update.CALLBACK_QUERY],
    )


if __name__ == "__main__":
    main()
