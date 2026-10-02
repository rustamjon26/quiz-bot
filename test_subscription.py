"""Unit tests for channel subscription. No network and no bot token required."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
import warnings
from types import SimpleNamespace
from unittest.mock import patch

import db
import texts
from config import Channel, parse_channels


def _member(status: str, is_member: bool | None = None):
    return SimpleNamespace(status=status, is_member=is_member)


class ParseTests(unittest.TestCase):
    def test_example_value(self) -> None:
        raw = (
            "@safartrip_uz|SafarTrip,@mendora_en|Mendora,"
            "-1001234567890|Yopiq kanal|https://t.me/+AbCdEf"
        )
        channels = parse_channels(raw)
        self.assertEqual(
            channels,
            (
                Channel("@safartrip_uz", "SafarTrip", "https://t.me/safartrip_uz"),
                Channel("@mendora_en", "Mendora", "https://t.me/mendora_en"),
                Channel(-1001234567890, "Yopiq kanal", "https://t.me/+AbCdEf"),
            ),
        )

    def test_empty_skips_the_step(self) -> None:
        self.assertEqual(parse_channels(""), ())
        self.assertEqual(parse_channels("  ,  "), ())

    def test_numeric_without_invite_is_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            parse_channels("-1001|Yopiq")


class MembershipTests(unittest.TestCase):
    def test_status_mapping(self) -> None:
        from bot import membership_satisfies

        for status in ("member", "administrator", "creator"):
            self.assertTrue(membership_satisfies(_member(status)), status)
        self.assertTrue(membership_satisfies(_member("restricted", is_member=True)))
        self.assertFalse(membership_satisfies(_member("restricted", is_member=False)))
        self.assertFalse(membership_satisfies(_member("restricted", is_member=None)))
        self.assertFalse(membership_satisfies(_member("left")))
        self.assertFalse(membership_satisfies(_member("kicked")))
        enum_status = SimpleNamespace(value="member")
        self.assertTrue(membership_satisfies(SimpleNamespace(status=enum_status)))


class AlertTests(unittest.TestCase):
    def test_missing_titles(self) -> None:
        self.assertEqual(
            texts.missing_channels_alert(["SafarTrip", "Mendora"]),
            "Hali obuna bo'lmadingiz: SafarTrip, Mendora",
        )

    def test_alert_is_capped(self) -> None:
        text = texts.missing_channels_alert(["Kanal"] * 40)
        self.assertLessEqual(len(text), 200)
        self.assertTrue(text.startswith("Hali obuna bo'lmadingiz:"))


class MigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.directory.name, "leads.db")

    def tearDown(self) -> None:
        self.directory.cleanup()

    def _legacy_db(self) -> None:
        conn = sqlite3.connect(self.path)
        conn.execute(
            """
            CREATE TABLE leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL UNIQUE,
                username TEXT,
                full_name TEXT NOT NULL,
                tg_name TEXT,
                phone TEXT,
                role TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO leads (
                telegram_id, username, full_name, tg_name, phone, role, source,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (7, "ali", "G'anisher", "Ali", None, "traveler", "stend", "t0", "t0"),
        )
        conn.commit()
        conn.close()

    def test_migration_is_idempotent_and_keeps_rows(self) -> None:
        self._legacy_db()
        db.init_db(self.path)
        db.init_db(self.path)
        row = db.get_lead(7)
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["full_name"], "G'anisher")
        self.assertEqual(row["subscribed"], 0)
        self.assertIsNone(row["subscribed_at"])
        conn = sqlite3.connect(self.path)
        names = [item[1] for item in conn.execute("PRAGMA table_info(leads)")]
        conn.close()
        self.assertEqual(names.count("subscribed"), 1)
        self.assertEqual(names.count("subscribed_at"), 1)

    def test_mark_survives_upsert_and_export(self) -> None:
        db.init_db(self.path)
        db.upsert_lead(
            telegram_id=7,
            username="ali",
            full_name="Ali",
            tg_name="Ali",
            phone=None,
            role="traveler",
            source="stend",
        )
        self.assertTrue(db.mark_subscribed(7))
        self.assertFalse(db.mark_subscribed(7))
        stamped = db.get_lead(7)["subscribed_at"]
        db.upsert_lead(
            telegram_id=7,
            username="ali",
            full_name="Vali",
            tg_name="Ali",
            phone=None,
            role="guide",
            source="flyer",
        )
        row = db.get_lead(7)
        self.assertEqual(row["full_name"], "Vali")
        self.assertEqual(row["subscribed"], 1)
        self.assertEqual(row["subscribed_at"], stamped)
        payload, count = db.export_csv()
        text = payload.decode("utf-8-sig")
        self.assertTrue(payload.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(count, 1)
        self.assertIn("subscribed,subscribed_at", text.replace("\r\n", "\n").split("\n")[0])
        data = db.stats("2000-01-01T00:00:00Z", "2100-01-01T00:00:00Z")
        self.assertEqual(data["subscribed"], 1)
        db.clear_subscription(7)
        self.assertEqual(db.get_lead(7)["subscribed"], 0)
        self.assertEqual(db.get_lead(7)["subscribed_at"], stamped)
        self.assertEqual(db.stats("2000-01-01T00:00:00Z", "2100-01-01T00:00:00Z")["subscribed"], 0)


class _FakeBot:
    def __init__(self, members: dict) -> None:
        self.members = members
        self.sent: list[dict] = []

    async def get_chat_member(self, chat, user_id):
        outcome = self.members[chat]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)


class CheckTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        from bot import reset_channel_warnings

        reset_channel_warnings()
        self.channels = (
            Channel("@safartrip_uz", "SafarTrip", "https://t.me/safartrip_uz"),
            Channel("@mendora_en", "Mendora", "https://t.me/mendora_en"),
        )

    async def test_missing_and_api_error(self) -> None:
        from bot import check_subscriptions

        bot = _FakeBot(
            {
                "@safartrip_uz": _member("left"),
                "@mendora_en": RuntimeError("chat not found"),
            }
        )
        with patch("config.CHANNELS", self.channels), patch("config.ADMIN_CHAT_ID", -100):
            with self.assertLogs("bot", level="ERROR"):
                missing = await check_subscriptions(bot, 7)
                missing_again = await check_subscriptions(bot, 7)
        self.assertEqual(missing, ["SafarTrip"])
        self.assertEqual(missing_again, ["SafarTrip"])
        self.assertEqual(len(bot.sent), 1)
        self.assertIn("Mendora", bot.sent[0]["text"])
        self.assertIn("tekshirib bo'lmadi", bot.sent[0]["text"])
        self.assertNotIn("<Mendora>", bot.sent[0]["text"])

    async def test_warning_repeats_after_an_hour(self) -> None:
        import bot as bot_module

        fake = _FakeBot({"@safartrip_uz": RuntimeError("down"), "@mendora_en": _member("member")})
        with patch("config.CHANNELS", self.channels), patch("config.ADMIN_CHAT_ID", -100):
            with self.assertLogs("bot", level="ERROR"):
                await bot_module.check_subscriptions(fake, 7)
                bot_module._channel_warn_at["@safartrip_uz"] = 0
                await bot_module.check_subscriptions(fake, 7)
        self.assertEqual(len(fake.sent), 2)

    async def test_all_joined(self) -> None:
        from bot import check_subscriptions

        bot = _FakeBot(
            {
                "@safartrip_uz": _member("creator"),
                "@mendora_en": _member("restricted", is_member=True),
            }
        )
        with patch("config.CHANNELS", self.channels), patch("config.ADMIN_CHAT_ID", -100):
            missing = await check_subscriptions(bot, 7)
        self.assertEqual(missing, [])
        self.assertEqual(bot.sent, [])


class FlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.directory.name, "leads.db")
        db.init_db(self.path)
        self.channels = (
            Channel("@safartrip_uz", "SafarTrip", "https://t.me/safartrip_uz"),
        )

    def tearDown(self) -> None:
        self.directory.cleanup()

    def _context(self, bot):
        return SimpleNamespace(args=[], user_data={}, bot=bot)

    def _user(self, uid=7, username="ali"):
        return SimpleNamespace(id=uid, username=username, first_name="Ali", last_name=None)

    def _message(self, person, replies: list):
        async def reply_text(text, **kwargs):
            replies.append({"text": text, **kwargs})
            return self._message(person, replies)

        async def edit_reply_markup(**kwargs):
            replies.append({"edit": kwargs})

        message = SimpleNamespace(
            text=None,
            from_user=person,
            reply_text=reply_text,
            edit_reply_markup=edit_reply_markup,
        )
        return message

    async def test_promo_waits_for_subscription(self) -> None:
        from bot import AWAITING_SUB, _finish

        person = self._user()
        replies: list = []
        message = self._message(person, replies)
        context = self._context(_FakeBot({}))
        context.user_data.update({"role": "traveler", "full_name": "Ali", "source": "stend"})
        update = SimpleNamespace(effective_message=message, effective_user=person)
        with patch("config.CHANNELS", self.channels):
            state = await _finish(update, context, phone=None, remove_keyboard=False)
        self.assertEqual(state, AWAITING_SUB)
        blob = " ".join(item.get("text", "") for item in replies)
        self.assertIn("Tekshirish", blob)
        self.assertNotIn("SCHOOL21", blob)
        self.assertEqual(db.get_lead(7)["subscribed"], 0)

    async def test_empty_channels_still_shows_promo(self) -> None:
        from bot import ConversationHandler, _finish

        person = self._user()
        replies: list = []
        message = self._message(person, replies)
        context = self._context(_FakeBot({}))
        context.user_data.update({"role": "traveler", "full_name": "Ali", "source": "stend"})
        update = SimpleNamespace(effective_message=message, effective_user=person)
        with patch("config.CHANNELS", ()):
            state = await _finish(update, context, phone=None, remove_keyboard=False)
        self.assertEqual(state, ConversationHandler.END)
        blob = " ".join(item.get("text", "") for item in replies)
        self.assertIn("SCHOOL21", blob)

    async def test_check_keeps_buttons_until_joined(self) -> None:
        from bot import AWAITING_SUB, on_check

        person = self._user()
        answers: list = []

        async def answer(text=None, show_alert=False):
            answers.append((text, show_alert))

        query = SimpleNamespace(
            data="sub:check",
            message=self._message(person, []),
            answer=answer,
        )
        update = SimpleNamespace(callback_query=query, effective_user=person, effective_message=None)
        context = self._context(
            _FakeBot({"@safartrip_uz": _member("left")})
        )
        context.user_data.update({"role": "owner", "full_name": "<b>Ali</b>"})
        with patch("config.CHANNELS", self.channels), patch("config.ADMIN_CHAT_ID", None):
            state = await on_check(update, context)
        self.assertEqual(state, AWAITING_SUB)
        self.assertEqual(answers, [("Hali obuna bo'lmadingiz: SafarTrip", True)])
        self.assertEqual(db.get_lead(7), None)

    async def test_check_then_thanks_and_admin_note(self) -> None:
        from bot import ConversationHandler, on_check

        db.upsert_lead(
            telegram_id=7,
            username="ali",
            full_name="<b>Ali</b>",
            tg_name="Ali",
            phone=None,
            role="traveler",
            source="stend",
        )
        person = self._user()
        replies: list = []
        edits: list = []

        async def answer(text=None, show_alert=False):
            return None

        async def edit_message_text(text, **kwargs):
            edits.append(text)

        query = SimpleNamespace(
            data="sub:check",
            message=self._message(person, replies),
            answer=answer,
            edit_message_text=edit_message_text,
        )
        update = SimpleNamespace(callback_query=query, effective_user=person)
        bot = _FakeBot({"@safartrip_uz": _member("member")})
        context = self._context(bot)
        context.user_data.update({"role": "traveler", "full_name": "<b>Ali</b>"})
        with patch("config.CHANNELS", self.channels), patch("config.ADMIN_CHAT_ID", -100):
            state = await on_check(update, context)
        self.assertEqual(state, ConversationHandler.END)
        self.assertEqual(edits, [texts.SUBSCRIBED_OK])
        blob = " ".join(item.get("text", "") for item in replies)
        self.assertIn("SCHOOL21", blob)
        self.assertIn("&lt;b&gt;Ali&lt;/b&gt;", blob)
        self.assertEqual(db.get_lead(7)["subscribed"], 1)
        self.assertTrue(bot.sent)
        self.assertIn("&lt;b&gt;Ali&lt;/b&gt;", bot.sent[-1]["text"])
        self.assertNotIn("<b>Ali</b>", bot.sent[-1]["text"])


class AppTests(unittest.TestCase):
    def test_handlers_register(self) -> None:
        import bot as bot_module

        with warnings.catch_warnings(record=True) as caught:
            with patch.object(bot_module.config, "BOT_TOKEN", "123456:TEST"):
                app = bot_module.build_application()
        self.assertFalse([item for item in caught if "per_message" in str(item.message)])
        self.assertEqual(len(app.handlers[0]), 5)


if __name__ == "__main__":
    unittest.main()
