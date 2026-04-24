# Common pitfalls

**Load when:** the standard rotation flow is hitting friction and you
need to diagnose fast. Also preemptive reading for first-time
rotators. Every entry below is taken from a real incident.

## Pitfall 1 — Clipboard collision

**What happens:** you copy a fresh API key from a provider dashboard.
Moments later, before pasting it into a file, you copy something else
— a prompt, a URL, a shell command. The key is gone from the
clipboard. You paste what you think is the key; it's actually the
prompt.

Two common variants:

- **Human-in-the-loop:** you copy the key, then copy a chat message
  to paste into a different window. The second copy wipes the first.
- **Tool-mediated:** a curl command or editor plugin quietly puts
  output into the clipboard (macOS pbcopy integrations) and
  overwrites a credential you copied a moment ago.

**Why it's sneaky:** most consumers give a generic 401 or "invalid
credential" error. The error doesn't tell you "the value you pasted
was a prompt", so you assume the key itself is bad and go back to
the dashboard to generate another one — and the cycle repeats.

**Fix:**

```bash
# Right after generating the key in the dashboard, paste it into a
# mode-600 file, not into a chat or editor buffer that might later
# get copied.
touch /tmp/new-key.txt && chmod 600 /tmp/new-key.txt
# Open the file, paste once, save.
# Work off the file from then on:
export NEW_KEY="$(cat /tmp/new-key.txt | tr -d '[:space:]')"
```

Delete the file at the end of the rotation:

```bash
unset NEW_KEY
rm /tmp/new-key.txt
```

## Pitfall 2 — Auditing by name, not by usage

**What happens:** you `grep -r VAR_NAME` across the codebase, find
every reference to the variable name, and assume you've mapped all
consumers. You rotate. Production breaks in a corner where the secret
was **hardcoded as a literal** with no variable prefix, or where a
config JSON took precedence over the env var you updated.

**Fix:** after the variable-name grep, do a **value-prefix grep** for
each active secret. Mask the value to the first 6–10 characters and
grep recursively:

```bash
grep -rnF "<first-10-chars-of-value>" ~/code \
  --exclude-dir=.git --exclude-dir=node_modules \
  --exclude-dir=__pycache__ --exclude-dir=.venv
```

And if the project supports multiple credential sources (env var +
JSON config + vault), read the loading code to see which takes
precedence. The one that loses the precedence contest is dead
fallback — rotating it alone changes nothing.

## Pitfall 3 — Rotating before mapping consumers

**What happens:** the user has a sense of where the secret is used
("just `.secrets`, right?") and rotates without an audit. Five
minutes later a scheduled job fails with 401; twenty minutes later a
multi-tenant client bot goes silent because the secret was also in
their JSON config; an hour later an n8n workflow surfaces the same
failure during its cron run.

**Fix:** always run `workflows/audit-before-rotation.md` first. The
yield is a consumer table. Rotations without a consumer table are
gambling.

If you already rotated and now things are breaking, the recovery is:

1. Revert `.secrets` from backup.
2. Reload services.
3. Restore the old credential's precedence.
4. **Do the audit you skipped.**
5. Try again.

## Pitfall 4 — Format preservation

**What happens:** you swap a secret in `.secrets` with `sed`, but the
file has mixed formats:

```
export ANTHROPIC_API_KEY=sk-ant-...    # no quotes, with export
GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"    # quotes, no export
BITGET_API_KEY="bg_8..."              # quotes, no export
```

Your `sed` adds or removes quotes, or strips the `export`, or
introduces a stray character. Bash now fails to parse `.secrets` and
every service that loads it starts with empty environment.

**Fix:**

- Before swapping, inspect the exact line: `grep -n '^VAR' ~/.secrets`.
  Note the format.
- Use Python with an explicit regex that preserves quotes and `export`
  (see `rotate-api-keys.md` step 3).
- After swapping, **always** run the sanity check:

  ```bash
  bash -n ~/.secrets && echo "syntax OK" || echo "SYNTAX ERROR — ROLLBACK"
  wc -l ~/.secrets ~/.secrets.bak-*  # line count must be preserved
  ```

- If the syntax check fails, immediately restore from backup and
  retry with a smaller diff.

## Pitfall 5 — Revoking before validating the new credential

**What happens:** you swap `.secrets`, the new key looks good, and
you immediately revoke the old one in the provider dashboard. Then
the next cron cycle runs and **one** consumer fails — the one you
forgot to smoke-test. The old key is gone, so you can't roll back.
The new key is fine, but the failing consumer points at a different
source (JSON config, n8n, hardcoded literal) you missed.

This is especially painful with Telegram, where there is no
coexistence window at all — once you tap Revoke in BotFather, the old
token is dead instantly.

**Fix:**

- Smoke test every consumer you identified in the audit. **Every**
  one, not a sample.
- For credentials with a coexistence window (API keys, Gmail App
  Passwords), wait for the longest scheduler cycle to complete with
  the new credential before revoking.
- For credentials without a coexistence window (Telegram): stage
  every swap in advance (editor windows open, commands queued),
  revoke, then swap in parallel as fast as possible. Budget for
  minutes of silence.
- If you discover a missed consumer only after revoking: generate a
  new credential, swap it everywhere including the missed consumer,
  and move on. Don't try to un-revoke — it's not a supported
  operation on any provider.

## Bonus — Passphrase rule discovery (exchanges)

Some exchanges — BITGET is the known case — silently reject
passphrases containing certain special characters. The dashboard
accepts the passphrase when you set it; auth fails at runtime with a
generic "invalid passphrase" error.

**Fix:** when the dashboard accepts a passphrase but auth fails,
simplify the passphrase character set before blaming the signature.
Start from `[a-zA-Z0-9]` only. If that works, add characters back one
class at a time (`_`, then `-`, then punctuation) until you find the
one the exchange rejects — you've just reverse-engineered their
undocumented ruleset.

## When everything is on fire

If a rotation has cascaded into multiple consumers failing, stop
making more changes. The checklist:

1. Roll back `.secrets` from the most recent `.bak-*` timestamped
   backup.
2. Reload all consumers (`launchctl bootout/bootstrap`, `systemctl restart`,
   container restart — whatever applies).
3. Verify old credentials still work against at least one consumer.
4. **Now** diagnose what went wrong — while production is stable on
   the pre-rotation state.
5. Retry the rotation only after you've found the root cause, not
   "just one more time to see".
