---
name: secret-rotator
description: "Rotate credentials safely in repositories and production systems. Activate when user mentions rotating API keys, Gmail app passwords, Telegram bot tokens, exchange API credentials (like BITGET/Binance), or any secret that lives in .secrets files or config JSONs. Also activate when user discusses credential exposure in git history, recent leaks, or security audits of their codebase."
---

# Secret Rotator

A skill that walks through credential rotations with battle-tested
workflows for common credential types. Built on six real rotations in
production (Anthropic API key, 2 Gmail App Passwords, 2 Telegram bot
tokens, 1 BITGET exchange credential set) with no production
regressions.

## When to activate

Activate this skill when the user:

- **Reports exposure** of credentials in git history, logs, config files,
  Slack/Discord, or any non-private channel.
- **Plans preventive rotation** (compliance, hygiene, project end, team
  change).
- **Ran a secrets audit** and found old, orphaned, or over-permissioned
  keys.
- **Is onboarding a legacy environment** (previous owner, freelancer,
  acquired project).
- **Asks to "rotate X"**, "rotate X token", "change my API key", "my
  token is leaked".

Do **not** activate for: generating new keys without rotation intent,
theoretical cryptography questions, or code reviews with no rotation
planned.

## Non-negotiable principles

Every workflow in this skill follows these five principles. If one is
broken, stop and reassess.

1. **Back up before any change.** Typical:
   `cp ~/.secrets ~/.secrets.bak-<reason>-<YYYYMMDD-HHMM>`. No backup →
   no rollback.
2. **Validate the new before revoking the old.** Never rotate into the
   dark. Keep the old credential alive until the new one is proven in
   every consumer.
3. **Map every consumer before rotating.** `.secrets`, client JSON
   configs, n8n workflow credentials, LaunchAgent/systemd environment
   variables, hardcoded secrets in scripts. Auditing by variable name
   is not enough — audit by actual usage with recursive grep and import
   tracing.
4. **Test auth against a real private endpoint, not `/health`.** Hit an
   endpoint that your real consumers hit (balance, account, authenticated
   ping). Public endpoints with an API-key header often return 200 even
   when the key is invalid.
5. **Document the rotation in an auditable log.** Fields: date, operator,
   masked-before, masked-after, backup path, list of validated consumers.
   Keep this doc outside the repo so old values never get committed.

**Operational rule that shapes everything above:** move secrets through
files with mode 600 (`/tmp/creds.txt`), never through the clipboard.
Shared clipboards lose values silently when any other copy happens
mid-flow (a URL, a prompt, a shell command).

## Referenced workflows

Load only the workflow that matches the credential type in play. Each
has a "Load when" line so Claude knows when to pull it into context.

- **[workflows/audit-before-rotation.md](workflows/audit-before-rotation.md)**
  — Load when the user wants to assess what secrets exist, where they
  live, and who consumes them (pre-rotation mapping).

- **[workflows/rotate-api-keys.md](workflows/rotate-api-keys.md)**
  — Load when rotating standard API keys: Anthropic, OpenAI, Stripe,
  SendGrid, or any `sk-*`/`pk-*` pattern. Also the generic fallback for
  any provider not covered by a more specific workflow.

- **[workflows/rotate-gmail-app-passwords.md](workflows/rotate-gmail-app-passwords.md)**
  — Load when rotating a Gmail App Password (requires 2FA on the
  account). 16-char string — some consumers expect the format with
  spaces (`xxxx xxxx xxxx xxxx`), others without (`xxxxxxxxxxxxxxxx`).
  Match the consumer's expectation.

- **[workflows/rotate-telegram-bot-tokens.md](workflows/rotate-telegram-bot-tokens.md)**
  — Load when rotating a Telegram bot token via BotFather (`/revoke` or
  bot re-creation flow).

- **[workflows/rotate-exchange-keys-with-permissions.md](workflows/rotate-exchange-keys-with-permissions.md)**
  — Load when rotating exchange API credentials with granular
  permissions: BITGET, Binance, Kraken. Includes the Withdraw/Transfer
  blast-radius analysis. Passphrase rules vary by provider — e.g.
  BITGET rejects certain character sets, so pick a simple alphanumeric
  passphrase that both the provider and the consumer can handle.

- **[workflows/common-pitfalls.md](workflows/common-pitfalls.md)**
  — Reference when something feels off or the standard flow hits
  friction. Preemptively useful for first-time rotators. Top errors
  from real incidents with their fixes.

## Standard flow

For any rotation, follow this order:

1. **Audit** → `audit-before-rotation.md` to map consumers.
2. **Specific workflow** for the credential type.
3. **Backup** `.secrets` and any config file with the secret embedded.
4. **Generate the new key** in the provider dashboard. Leave the old one
   active.
5. **Test auth** against a real private endpoint with the new key.
6. **Swap** in `.secrets` preserving the exact format the file uses
   (with/without `export`, with/without quotes — see pitfall #4 in
   `common-pitfalls.md`).
7. **Smoke test** every consumer (scripts, bots, services) with the new
   credential.
8. **Wait N minutes** so any scheduler that runs every X minutes picks
   up the new credential cleanly. Choose N based on the longest schedule
   (e.g. if a job runs every 2h, wait 2h before revoking).
9. **Revoke the old key** in the provider dashboard.
10. **Document** the rotation with masked-before/after, date, backup
    path, and validated consumers.

## When something fails

- **Before the swap** → no impact. Fix and retry.
- **After the swap but before smoke test** → roll back from backup:
  `cp ~/.secrets.bak-<timestamp> ~/.secrets`. Reload services.
- **After smoke test fails in one consumer** → do not revoke the old
  key. Diagnose the specific consumer — the secret may be hardcoded in
  a second location (JSON config, n8n credential).
- **After revoking the old key** → active incident. The new key should
  work; if it doesn't, generate another new key and retry the full
  workflow.

## Scope (v1)

- Pre-rotation audit
- Rotation by credential type (API keys, Gmail, Telegram, exchanges)
- Pitfalls and recovery

## Roadmap (v2)

- Git history cleaning with `git-filter-repo` after rotation
- Compliance checklists (SOC 2, ISO 27001)
- Vault manager integrations (1Password, Doppler, Infisical)
- Scheduled rotation cadence (monthly/quarterly)
- Incident response playbooks

## License

MIT. See [LICENSE](LICENSE).
