# Rotate Gmail App Passwords

**Load when:** rotating a Gmail App Password. These are the 16-character
one-off credentials Gmail issues to apps that can't do OAuth (IMAP
pollers, SMTP senders, legacy clients).

## Pre-requisites

- **2-Factor Authentication must be enabled** on the Google account.
  Without 2FA, the App Passwords page is hidden entirely.
- **Security keys (Yubikey, FIDO2) caveat:** accounts enrolled in
  Advanced Protection, or where the only 2FA method is a physical
  security key, often do **not** expose the App Passwords page at all.
  If `myaccount.google.com/apppasswords` returns "The setting you are
  looking for is not available for your account", App Passwords are
  disabled for your account — you need OAuth instead.
- **Per-account cap:** Gmail allows ~10 active App Passwords per
  account. If you're at the limit, the dashboard will refuse to create
  a new one until you revoke at least one.

## Step by step

### 1. Audit existing App Passwords

At `myaccount.google.com/apppasswords` you'll see a list of active
passwords with a **label** (name you gave them) and a **last used**
timestamp. Before rotating:

- Identify which label corresponds to the consumer you want to rotate.
  Labels drift from reality — `"n8n"` may now be used by `sales-monitor.py`.
  The "last used" timestamp is the ground truth.
- Count current active passwords. If at 10, plan to revoke the old one
  **after** the new one is validated.

### 2. Create the new App Password

Same page → *Select app* (choose "Other") → give it a descriptive
label, e.g. `form-lead-monitor-20260420`. Date-stamped labels make
future audits easier.

Google shows the password **once**, as four groups of four characters
separated by spaces: `abcd efgh ijkl mnop`.

Copy to an intermediate file with mode 600 — do not paste into a chat
prompt:

```bash
touch /tmp/new-gmail-pass.txt && chmod 600 /tmp/new-gmail-pass.txt
# Paste the 16 characters into the file with your editor.
# Decide: with spaces or without spaces, based on the consumer (see
# step 3 below). If unsure, store as shown and strip at load time.
```

### 3. Decide the format — spaces or no spaces

The 16 characters work either way, but **every consumer has a
preference**. Match it exactly or auth silently fails.

| Library / consumer | Expected format |
| --- | --- |
| Python `smtplib` (SMTP_SSL / STARTTLS) | Either works — it strips whitespace internally. |
| Python `imaplib` | Usually works with spaces; some wrappers reject them. |
| Most Node.js SMTP libs (`nodemailer`) | Without spaces. |
| Thunderbird / macOS Mail | Spaces. |
| Legacy Java `javax.mail` | Without spaces. |

If you don't know the consumer's preference, default to **without
spaces** and keep a note of the original format in case you need to
re-introduce spaces.

```bash
# strip spaces
tr -d ' ' < /tmp/new-gmail-pass.txt > /tmp/new-gmail-pass.nospaces
chmod 600 /tmp/new-gmail-pass.nospaces
```

### 4. Test auth — both SMTP and IMAP

Google's SMTP supports two endpoints. Test the one your consumer uses.

**SMTP over SSL (port 465):**

```bash
export GMAIL_USER="your.address@gmail.com"
export NEW_PASS="$(cat /tmp/new-gmail-pass.nospaces)"

python3 <<'PY'
import os, smtplib, sys
try:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as s:
        s.login(os.environ["GMAIL_USER"], os.environ["NEW_PASS"])
    print("SMTP_AUTH_OK")
except smtplib.SMTPAuthenticationError as e:
    print(f"SMTP_AUTH_FAIL: {e}")
    sys.exit(1)
PY
```

**SMTP with STARTTLS (port 587):**

```bash
python3 <<'PY'
import os, smtplib, sys
try:
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as s:
        s.starttls()
        s.login(os.environ["GMAIL_USER"], os.environ["NEW_PASS"])
    print("SMTP_AUTH_OK")
except smtplib.SMTPAuthenticationError as e:
    print(f"SMTP_AUTH_FAIL: {e}")
    sys.exit(1)
PY
```

**IMAP (port 993):**

```bash
python3 <<'PY'
import os, imaplib, sys
try:
    m = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    m.login(os.environ["GMAIL_USER"], os.environ["NEW_PASS"])
    m.select("INBOX")
    print("IMAP_AUTH_OK")
    m.logout()
except imaplib.IMAP4.error as e:
    print(f"IMAP_AUTH_FAIL: {e}")
    sys.exit(1)
PY
```

Only proceed to the swap when every flavour your consumer uses returns
`*_AUTH_OK`.

### 5. Back up `.secrets` and swap

```bash
cp ~/.secrets ~/.secrets.bak-gmail-rotation-$(date +%Y%m%d-%H%M)
```

Swap with format-preservation (see `rotate-api-keys.md` step 3 for the
generic pattern). For Gmail App Passwords you usually have one of:

```
GMAIL_APP_PASSWORD="dezu ewtw rmxl bwgx"     # quoted, with spaces
GMAIL_APP_PASSWORD="dezuewtwrmxlbwgx"        # quoted, no spaces
export GMAIL_APP_PASSWORD=dezuewtwrmxlbwgx   # export, no quotes
```

Preserve whichever form the file already uses. If the consumer expects
spaces, keep spaces in the file.

### 6. Smoke test every consumer

Most Gmail-using consumers are either polling daemons (IMAP) or
schedulers (SMTP). For both:

- Reload the service so it re-reads `.secrets`:

  ```bash
  launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.yourorg.<service>.plist
  launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.yourorg.<service>.plist
  ```

- Tail the log and confirm a successful cycle:

  ```bash
  tail -f ~/Library/Logs/com.yourorg.<service>.log
  ```

For IMAP pollers, wait for one full poll cycle (usually 30s–2min). For
SMTP schedulers, trigger a test email if the service has a dry-run
mode; otherwise wait until the next scheduled run.

### 7. Revoke the old App Password

Once every consumer has completed at least one successful cycle with
the new password, revoke the old one at `myaccount.google.com/apppasswords`
→ click the trash icon next to the old label.

After revoking, Google usually kills active sessions for that password
within a minute. If any consumer was holding the old password in
memory, expect the next attempt to fail with `Invalid credentials`
(535-5.7.8).

### 8. Document

```
2026-04-20 14:08 — GMAIL_APP_PASSWORD_IMPULSO rotated
  old label in Google: form-lead-monitor (revoked ~14:20)
  new label in Google: form-lead-monitor-20260420 (active)
  old value: ytpx****ftzy
  new value: juxt****
  format: with spaces (consumer is imaplib wrapper)
  backup: ~/.secrets.bak-gmail-rotation-20260420-1408
  validated consumers:
    - form-lead-monitor.py (IMAP poll, PID 83343)
    - auto-followup.py (SMTP daily)
    - clientes/impulso-ia-test/email_config.json (embedded)
```

## Common mistakes and fixes

**Copying the password with spaces into a consumer that strips them
wrong.** `smtplib` is forgiving; a Java SMTP library may not be. If
auth succeeds in your test but the consumer fails in production, first
suspect the format and try the other variant.

**Forgetting the embedded copy in a client JSON.** Multi-tenant setups
often keep a copy in `clientes/<slug>/email_config.json`. Rotating
only `.secrets` leaves the JSON pointing at the revoked password. Grep
for the old masked value **before** revoking.

**Hitting the 10-password cap.** If creating a new password returns
"You've reached the maximum number of App Passwords", you must revoke
one first — but **not the one you're trying to rotate**. Revoke
something else that's truly unused.

**Assuming the label is accurate.** Labels are the operator's memory,
not Google's source of truth. Trust the "last used" timestamp when
resolving which password belongs to which consumer.

## Real example (masked)

In a 2026-04-20 rotation, a Gmail App Password `ezpl****tbme` was
hardcoded inside `autofirm_outreach.py` (not in `.secrets`). The
initial audit missed it because the `grep -r GMAIL_APP_PASSWORD` only
matched variable names; the hardcoded string was stored as a plain
literal with no variable prefix. It was caught by a second grep using
the first 6 characters of the value directly. Lesson: after auditing
by name, do a second pass grepping by value prefix for each secret
being rotated.
