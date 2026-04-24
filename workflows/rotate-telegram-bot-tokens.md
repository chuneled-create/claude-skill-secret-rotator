# Rotate Telegram bot tokens

**Load when:** rotating a Telegram bot token. Telegram issues tokens
via BotFather, an interactive chat interface; there is no web dashboard
and no API for rotation.

## Pre-requisites

- Access to the Telegram account that owns the bot (BotFather scopes
  tokens to the creator).
- The bot's username or chat handle — you need it to find the bot in
  BotFather's `/mybots` list.
- All consumers of the token identified in advance. **Telegram has no
  coexistence window** — the moment you revoke, the old token is dead.
  See the warning in step 3.

## Step by step

### 1. Open BotFather and locate the bot

In Telegram (phone or desktop), search for `@BotFather` and open the
chat.

```
You: /mybots
BotFather: [list of your bots as buttons]
You: (tap the bot you want to rotate)
BotFather: [management menu: API Token, Edit Bot, Bot Settings, ...]
```

### 2. Warning: no coexistence window

Tap *API Token*. BotFather shows the current token and a button
labelled *Revoke current token*.

**Once you tap Revoke, the old token is immediately invalid.** Unlike
Anthropic or Gmail, there is no "both active for a minute" period.
Every consumer holding the old token must be ready to receive the new
one **before** you revoke.

Therefore the standard flow is inverted for Telegram:

1. Prepare the swap in advance (locate `.secrets` lines, client JSONs,
   n8n credentials).
2. Have the swap commands staged (edited in an editor, ready to save).
3. Tap Revoke.
4. Paste the new token into the pre-staged files immediately.
5. Reload consumers.
6. Validate.

Budget a few minutes of expected bot silence. For user-facing bots,
consider announcing scheduled maintenance beforehand.

### 3. Revoke and capture the new token

Tap *Revoke current token*. BotFather replies with the new token in
the format `<bot_id>:<base64url>` (example shape:
`8679681838:AAFnxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`).

Copy the new token directly from the Telegram message into an
intermediate file:

```bash
touch /tmp/new-tg-token.txt && chmod 600 /tmp/new-tg-token.txt
# Paste into the file with your editor. Do not retype — the token is
# one typo away from being wrong.
```

### 4. Validate the new token

```bash
export NEW_TOKEN="$(cat /tmp/new-tg-token.txt | tr -d '[:space:]')"
curl -s "https://api.telegram.org/bot${NEW_TOKEN}/getMe" | python3 -m json.tool
```

Expected output includes `"ok": true` and the bot's identity (`id`,
`username`, `first_name`). Anything else — especially `"ok": false,
"description": "Unauthorized"` — means the token is wrong; stop and
re-copy from BotFather.

Confirm the old token now returns 401:

```bash
curl -s "https://api.telegram.org/bot<OLD_TOKEN>/getMe" | python3 -m json.tool
# Expected: {"ok": false, "error_code": 401, ...}
```

### 5. Swap in `.secrets` and all embedded copies

```bash
cp ~/.secrets ~/.secrets.bak-telegram-rotation-$(date +%Y%m%d-%H%M)
```

Swap the variable the same way as any other secret, preserving format.
Then find every additional copy and update it:

```bash
# Old masked value, first 10 chars:
grep -rnF "<first-10-chars-of-old-token>" ~/code \
  --exclude-dir=.git --exclude-dir=node_modules
```

Typical hit locations for multi-tenant setups:

- `~/.secrets` (canonical)
- `clientes/<slug>/telegram_config.json`
- n8n credentials (list via API, update via dashboard or POST)
- `.env` in any sub-project

Every location must be updated **before** consumers try to authenticate
with the stale old value.

### 6. Reload consumers

Telegram bots consume tokens in one of two modes:

**Long polling** — the bot process calls `getUpdates` in a loop.
Restarting the process is enough:

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.yourorg.<bot>.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.yourorg.<bot>.plist
```

**Webhook** — Telegram pushes updates to an HTTPS endpoint. The bot
side doesn't hold the token in memory the same way, but the webhook
registration itself is token-scoped. You must re-register:

```bash
# clear stale webhook registered under the old token (best-effort; the
# old token is already dead so this will fail with 401 — that's expected)
curl -s "https://api.telegram.org/bot<OLD_TOKEN>/deleteWebhook"

# register the webhook under the new token
curl -s "https://api.telegram.org/bot${NEW_TOKEN}/setWebhook" \
  -d "url=https://your.webhook.url/telegram"
```

Verify the webhook is set:

```bash
curl -s "https://api.telegram.org/bot${NEW_TOKEN}/getWebhookInfo" | python3 -m json.tool
```

### 7. Smoke test

Send a message to the bot from your personal Telegram account. For
long-polling bots, the response should arrive within seconds. For
webhook bots, check the webhook endpoint log to confirm the update
was received and processed.

### 8. Document

```
2026-04-19 21:37 — TELEGRAM_BOT_TOKEN rotated
  old: 8679681838:AAF6****pGHg (revoked in BotFather)
  new: 8679681838:AAFn****D6TA (active in .secrets)
  bot username: @impulsoia_ops_bot
  mode: long polling
  backup: ~/.secrets.bak-telegram-rotation-20260419-2137
  validated consumers:
    - lib.py::send_telegram (used by 80 agents)
    - n8n credential "telegram-bot-impulsoia"
  note: bot_id unchanged (8679681838), tail differs
```

## Common mistakes and fixes

**Revoking before staging the swap.** This is the classic Telegram
mistake: you click Revoke, then realise you haven't opened `.secrets`
in an editor yet. The bot is silent for however long it takes you to
find and update every copy. Fix: open every target file before
tapping Revoke.

**Missing a client JSON.** Multi-tenant setups stash the token in
`clientes/<slug>/telegram_config.json`. The canonical `.secrets` gets
rotated, the JSON doesn't, and the client's bot goes dark. Fix: grep
by value prefix (step 5) before revoking.

**Forgetting the webhook re-registration.** The webhook URL is stored
by Telegram's side keyed to the token. When you rotate the token,
Telegram doesn't automatically re-bind the old webhook. For webhook
bots you must call `setWebhook` with the new token or the bot will
silently receive no updates.

**Ignoring bot_id inertia.** The numeric prefix before the colon
(`8679681838`) is the bot's persistent ID and does **not** change
with rotation. Only the tail changes. This can confuse grep-based
audits: searching for `8679681838` will still match after rotation —
use the tail characters (`AAFn****D6TA` vs `AAF6****pGHg`) to tell
the tokens apart.

## Real example (masked)

During a 2026-04-19 rotation, the `TELEGRAM_BOT_TOKEN` was stored in
both `.secrets` and in an n8n credential (`telegram-bot-impulsoia`).
The shell-level swap was done in seconds, but the n8n credential was
not updated until the bot started returning 401 — roughly 12 minutes
of silence on three automation workflows. Fix adopted going forward:
run the n8n credential grep **before** pressing Revoke, so every
target is ready to update in parallel.
