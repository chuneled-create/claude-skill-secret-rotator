# Rotate API keys (generic / Anthropic / OpenAI)

**Load when:** rotating a standard API key — Anthropic, OpenAI, Stripe,
SendGrid, or anything matching the `sk-*` / `pk-*` pattern. This is
also the fallback workflow for any provider not covered by a more
specific file.

## Pre-requisites

- Dashboard access to the provider with permission to create and revoke
  keys.
- A private (authenticated) endpoint you can hit from the shell to
  validate the new key. A minimal list endpoint or a small priced call
  is usually fine.
- Backup of `~/.secrets` (or equivalent canonical store) already taken
  during the audit phase.

## Step by step

### 1. Generate the new key, keep the old one active

In the provider dashboard:

- **Anthropic:** `console.anthropic.com/settings/keys` → *Create Key*.
  Scope it to the same workspace as the old one. Copy the new key
  **once** — it is shown exactly once.
- **OpenAI:** `platform.openai.com/api-keys` → *Create new secret key*.
  Same one-shot copy behaviour.
- **Stripe:** `dashboard.stripe.com/apikeys` → *Create secret key*.
  Live keys are shown once; restricted keys can be regenerated but the
  new value is also one-shot.
- **SendGrid:** `app.sendgrid.com/settings/api_keys` → *Create API Key*
  with the same permissions as the old one. One-shot copy.
- **Generic:** find the API keys section, create a new key, copy once.

Do **not** revoke the old one yet. You will need both side by side for
a minute.

Write the new key to an intermediate file with mode 600 — never paste
it straight into a prompt (clipboard collision, see
`common-pitfalls.md` #1):

```bash
touch /tmp/new-key.txt && chmod 600 /tmp/new-key.txt
# Paste the key into the file with your editor.
```

### 2. Test auth against a private endpoint

Before touching `.secrets`, confirm the new key authenticates. For
Anthropic:

```bash
NEW_KEY="$(cat /tmp/new-key.txt | tr -d '[:space:]')"

curl -s -w '\nHTTP %{http_code}\n' \
  -H "x-api-key: ${NEW_KEY}" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  https://api.anthropic.com/v1/messages \
  -d '{"model":"claude-haiku-4-5-20251001","max_tokens":8,
       "messages":[{"role":"user","content":"ping"}]}'
```

Interpretation:

- `HTTP 200` with a message body → auth OK.
- `HTTP 400` with `credit_balance_too_low` → **auth OK**, the account
  simply has no credits. This is a valid pass for the rotation step;
  fix the billing separately.
- `HTTP 401 / 403` → the key is wrong, rejected, or not yet propagated.
  Do not proceed.

For OpenAI:

```bash
curl -s -H "Authorization: Bearer ${NEW_KEY}" \
  https://api.openai.com/v1/models | head -c 200
```

For any other provider: pick the smallest authenticated GET endpoint in
their docs. Avoid `/health` or any endpoint that returns 200 without
reading the key.

### 3. Back up `.secrets` and swap

```bash
cp ~/.secrets ~/.secrets.bak-<provider>-rotation-$(date +%Y%m%d-%H%M)
```

Swap the value. Preserve the **exact format** the file uses — if every
other line starts with `export`, keep it; if values are quoted, keep
the quotes. A quick way:

```bash
# Export so the child python process can read it via os.environ.
export NEW_KEY="$(cat /tmp/new-key.txt | tr -d '[:space:]')"

# inspect current line
grep -n '^\(export \)\?ANTHROPIC_API_KEY' ~/.secrets

# in-place swap with Python (avoids sed escaping headaches)
python3 <<'PY'
import os, re, pathlib
p = pathlib.Path.home() / ".secrets"
c = p.read_text()
new = os.environ["NEW_KEY"]
c_new = re.sub(r'^(export\s+)?ANTHROPIC_API_KEY=.*$',
               rf'\1ANTHROPIC_API_KEY={new}', c, flags=re.M)
if c_new == c:
    raise SystemExit("ABORT: no line matched ANTHROPIC_API_KEY — check format")
p.write_text(c_new)
print("swap OK")
PY
bash -n ~/.secrets && echo "syntax OK"
```

Verify line count is unchanged:

```bash
wc -l ~/.secrets ~/.secrets.bak-*  # should match for the active file
```

### 4. Smoke test every consumer

For each script that reads the key, do an end-to-end call that exercises
the same code path production uses — not just an `import`. If the
project uses a central loader (e.g. `lib.load_secrets()`), reload it
explicitly so the subprocess gets the new env:

```bash
python3 -c "
import sys; sys.path.insert(0, 'scripts')
import lib; lib._secrets_loaded = False; lib.load_secrets()
# then call the specific function that uses the key
"
```

### 5. Wait, then revoke the old key

Wait for the longest scheduler cycle to tick over once with the new
key (usually minutes to a few hours). If your ecosystem has cron jobs
that run every 2h, wait 2h. If everything is KeepAlive daemons, one
smoke test cycle is enough.

Then revoke the old key in the provider dashboard. For Anthropic:
console → API Keys → *Revoke* on the old row. For OpenAI, same flow.

### 6. Document

Append to the audit log:

```
2026-04-20 12:59 — ANTHROPIC_API_KEY rotated
  old: sk-a****SgAA  (revoked in console)
  new: sk-a****WL**  (active in ~/.secrets)
  backup: ~/.secrets.bak-anthropic-20260420-1259
  validated consumers: lib.ask_haiku via server.py /api/anthropic
```

## Common mistakes and fixes

**Trusting `/health` as an auth test.** A 200 from `/health` proves
nothing about the key. Use an endpoint that reads the key; see step 2.

**Swapping before testing.** If the new key is wrong, you now have a
broken `.secrets` and no production key. Always test first, swap
second.

**Revoking before the next cron cycle.** A daily scheduler that hasn't
run since the swap still uses the old key via process memory. Revoking
can surface a failure hours later. Wait one full cycle of the longest
schedule.

## Real example (masked)

During a 2026-04-20 rotation, the `credit_balance_too_low` response
initially looked like a failure — the test curl returned HTTP 400. A
closer read of the body showed the error was a billing signal, not an
auth signal. The rotation proceeded; the `400 credit_balance_too_low`
was the correct "auth is fine" outcome for a depleted account. Lesson:
read the error body, not just the status code.
