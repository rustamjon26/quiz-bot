# SafarTrip lead bot

Telegram bot that collects leads at a SafarTrip stand. Guests pick a role, leave a name, and (only if they have no @username) share a phone number. Each new or updated lead is sent to an admin group. The guest sees a short thank-you in Uzbek.

Python 3.11, [python-telegram-bot](https://docs.python-telegram-bot.org/) 20.7, polling (no webhook).

## BotFather setup

1. Open [@BotFather](https://t.me/BotFather) and send `/newbot`.
2. Display name: `SafarTrip`.
3. Username: something that ends with `bot`, for example `SafarTripLeadsBot`.
4. Copy the token into `BOT_TOKEN`. Do not commit it and do not paste it into chats.
5. Optional, still in BotFather:
   - `/setdescription` — one line guests see before they press Start.
   - `/setabouttext` — short about text on the profile.
   - `/setuserpic` — the SafarTrip logo.
6. Leave privacy mode on (the default). The bot only needs private chats plus commands in the admin group.
7. `/setjoingroups` → Enable, so you can add the bot to the admin group.

Replace `YOUR_BOT_USERNAME` below with the username from step 3, without `@`.

## Local run

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

macOS / Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`, then from the project folder:

```bash
python bot.py
```

Logs should show `SafarTrip lead bot is polling`. Open the bot in a **private** chat and send `/start`. Registration does not run inside the admin group.

Stop the process with Ctrl+C.

## Environment variables

| Name | Required | Default | Purpose |
| --- | --- | --- | --- |
| `BOT_TOKEN` | yes | | Token from BotFather |
| `ADMIN_CHAT_ID` | yes for alerts | | Group chat that receives every lead |
| `ADMIN_IDS` | yes for admin commands | | Comma-separated Telegram user ids, e.g. `111,222` |
| `PROMO_CODE` | no | `SCHOOL21` | Shown to travelers |
| `PROMO_TEXT` | no | `Birinchi bronga chegirma` | Line under the promo code |
| `SITE_URL` | no | `https://safartrip.uz` | Inline button on the thank-you |
| `DB_PATH` | no | `leads.db` | SQLite file path |
| `CHANNELS` | no | empty | Channels the guest must join before the thank-you |

`created_at` and `updated_at` are stored in UTC. `/stats` counts "today" in Asia/Tashkent (UTC+5).

`CHANNELS` is a comma-separated list. Each entry is `chat|Title` or `chat|Title|invite_url`. `chat` is `@username` or a numeric id such as `-1001234567890`. Titles cannot contain `|` or `,`. If the invite URL is omitted, the bot builds `https://t.me/<username>` from the `@username`. A numeric id needs an invite URL. Leave `CHANNELS` empty to skip the step.

```
CHANNELS=@safartrip_uz|SafarTrip,@mendora_en|Mendora,-1001234567890|Yopiq kanal|https://t.me/+AbCdEf
```

## Render Background Worker

The bot must stay running. Use a **Background Worker**, not a Web Service. A free web service sleeps and polling stops.

Python must be **3.11.x**. `python-telegram-bot` 20.7 crashes on Python 3.13 and 3.14 during `Application.builder().build()`. This repo pins 3.11.9 in `.python-version`, `runtime.txt`, and `render.yaml` (`PYTHON_VERSION`).

1. Push this folder to a Git repository and connect it to [Render](https://render.com).
2. **New → Background Worker** (or apply the `render.yaml` blueprint).
3. Runtime: **Python 3.11**. Set the environment variable `PYTHON_VERSION` to `3.11.9`.
4. Build command: `pip install -r requirements.txt`
5. Start command: `python bot.py`
6. Add the environment variables from the table above. Paste the real token only in the Render dashboard. `render.yaml` lists the keys with `sync: false`, so the blueprint does not contain secret values.
7. Deploy. If you changed the Python version on an existing service, use **Clear build cache & deploy**. A normal deploy can keep the old 3.14 environment and the worker will crash again.
8. Send yourself `/start` in private and confirm the admin group gets the lead.

A healthy startup log looks like this:

```text
INFO bot Python 3.11.9 (main, ...)
INFO bot Subscription step is off
INFO bot SafarTrip lead bot is polling
```

`Subscription step is off` appears only when `CHANNELS` is empty. With channels configured, that line lists their titles instead. If the log says `Unsupported Python version, expected 3.11`, the service is not on 3.11.x: set `PYTHON_VERSION=3.11.9` and clear the build cache.

Render's disk is ephemeral: a new deploy or restart can wipe `leads.db`. The admin group message is the source of truth. Use `/export` during the event if you want a file. A paid persistent disk is optional; if you attach one, set `DB_PATH` to a path on that disk (for example `/var/data/leads.db`).

Messages sent while the worker is stopped are delivered when it starts again. Half-finished chats are kept in memory only, so after a restart the guest should press `/start` again. Finished leads are not duplicated.

## How to get ADMIN_CHAT_ID

1. Create a **private** Telegram group, for example `SafarTrip Leads`.
2. Add the bot to the group. It only needs permission to send messages.
3. In the group, send `/start` (privacy mode still lets the bot see commands).
4. In a browser, open `https://api.telegram.org/bot<BOT_TOKEN>/getUpdates` using your real token.
5. Find the group in the JSON: `"chat": {"id": -100xxxxxxxxxx, "title": "SafarTrip Leads", "type": "supergroup"}`.
6. Put that id (including the minus) into `ADMIN_CHAT_ID`.
7. Close the tab. That URL contains the bot token.

Your own user id for `ADMIN_IDS` is `"from": {"id": ...}` in the same JSON, or any id bot such as `@userinfobot` in a private chat. Several admins: `111111,222222`.

Then message the bot in private, finish the flow, and check that the group receives a lead card.

## Deep links for QR codes

Put the full URL into any QR generator. The text after `start=` is stored as the lead source.

- Banner: `https://t.me/YOUR_BOT_USERNAME?start=banner`
- Flyer: `https://t.me/YOUR_BOT_USERNAME?start=flyer`
- Business card: `https://t.me/YOUR_BOT_USERNAME?start=vizitka`
- Stand: `https://t.me/YOUR_BOT_USERNAME?start=stend`

A plain `/start`, or an invalid payload, is stored as `direct`. Opening the bot again without a new payload keeps the previous source, so a later visit does not overwrite `stend` with `direct`.

## What the guest does

1. `/start` — short greeting and three buttons: traveler, property owner, guide.
2. Types their name (2–60 characters).
3. Telegram id and @username are saved automatically. A phone button appears only when there is no @username.
4. The lead is saved and forwarded to the admin group.
5. If `CHANNELS` is set, the guest joins those channels and presses «✅ Tekshirish». The promo code is shown only after that check, and only to travelers. Owners and guides get their usual thank-you. If `CHANNELS` is empty, the thank-you (including the traveler promo) is sent immediately.
6. A guest already marked subscribed who presses `/start` is checked again. Still subscribed: the thank-you, with no form. Missing a channel: the channel buttons again.
7. Someone who has not subscribed yet can press `/start` again. The same row is updated (latest role, name, and source). It does not create a second row.
8. `/cancel` stops the current step. Any other unexpected message tells them to press `/start`.

## Channel subscription

Add the bot as an **administrator** of every channel in `CHANNELS`. No extra rights are required: posting, editing, and deleting can all stay off. `getChatMember` works once the bot is an admin.

If a check fails (the bot is not an admin, the id is wrong, or Telegram errors), that channel counts as joined so a guest at the stand is not stuck. The admin group receives one warning per channel per hour: `⚠️ <title> tekshirib bo'lmadi: bot kanalga admin emas yoki ID noto'g'ri`.

### Private channel id

1. Add the bot as an administrator of the private channel.
2. Publish any post in the channel.
3. Open `https://api.telegram.org/bot<BOT_TOKEN>/getUpdates`.
4. Find `"channel_post" → "chat" → "id"`. It looks like `-100xxxxxxxxxx`.
5. In the channel info, create an invite link (`https://t.me/+...`).
6. Use `-100xxxxxxxxxx|Yopiq kanal|https://t.me/+AbCdEf` in `CHANNELS`.

Public channels can use `@username|Title` with no invite link.

## Admin commands

Only user ids in `ADMIN_IDS` can use these. Everyone else is ignored, with no reply.

- `/stats` — total leads, today's leads (Tashkent), subscribed count and percent, counts by role and by source.
- `/export` — all leads as `safartrip_leads.csv` (UTF-8 with BOM, so Excel shows Uzbek letters), including `subscribed` and `subscribed_at`.

Commands work in private chat and in the admin group.

## Test checklist

1. Bot is an admin of each channel, then restart after setting `CHANNELS`.
2. New traveler: the admin group gets the lead card, and the chat does not show the promo yet.
3. «✅ Tekshirish» before joining shows an alert with the missing titles. The same buttons stay. There is no skip.
4. After joining, «✅ Tekshirish» confirms the subscription and then shows the promo for a traveler.
5. `/start` again shows the thank-you directly. Leave a channel, press `/start`, and the channel step returns.
6. `/stats` shows `Obuna`. `/export` includes `subscribed` and `subscribed_at`.
7. With `CHANNELS` empty, `/start` ends on the thank-you as before.

```bash
python -m unittest test_subscription.py
```

## Files

- `bot.py` — conversation, notifications, admin commands
- `config.py` — environment
- `db.py` — SQLite `leads` table
- `texts.py` — Uzbek copy
- `test_subscription.py` — subscription unit tests
