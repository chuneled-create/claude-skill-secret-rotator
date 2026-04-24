# Audit before rotation

**Load when:** the user wants to assess what secrets exist, where they
live, and who consumes them — before any rotation decision.

## Objective

Produce a single table that maps every secret to every consumer and its
current status. Rotating without this table is guessing.

## Pre-requisites

- Shell access to the host where the services run.
- Read access to `.secrets` and any config files that might contain
  embedded credentials (client JSONs, `.env`, `.env.local`, n8n exports).
- `grep`, `find`, `sqlite3`, `curl`, and — if applicable — the n8n API
  token (to list stored credentials).

## Step by step

### 1. Inventory the baseline

List every secret currently in your canonical store:

```bash
grep -E '^(export )?[A-Z_][A-Z0-9_]*=' ~/.secrets \
  | sed -E 's/^(export )?([A-Z_][A-Z0-9_]*)=.*/\2/' \
  | sort -u
```

Also check `.env`, `.env.local`, and any file the app loads at startup.
Record one row per variable name.

### 2. Find the same values anywhere else on disk

The variable name is only half the story. The **value** may also live
hardcoded in a script or JSON config:

```bash
# Replace PATTERN with a known prefix of the secret (masked).
# For each active secret, run once.
grep -rnF "<first-10-chars-of-value>" ~/code \
  --exclude-dir=.git --exclude-dir=node_modules \
  --exclude-dir=__pycache__ --exclude-dir=.venv
```

Every hit outside `~/.secrets` is a consumer that will break on rotation
unless you update it too.

### 3. Check n8n credentials (if you use n8n)

```bash
source ~/.secrets
curl -s -H "X-N8N-API-KEY: ${N8N_API_KEY}" \
  http://localhost:5678/api/v1/credentials \
  | python3 -c "import sys,json; \
    [print(c['id'], c['name'], c['type']) for c in json.load(sys.stdin)['data']]"
```

Each row is a separate copy of a credential that rotation must update.

### 4. Check process and LaunchAgent environment variables

Some services have credentials pinned in their plist `EnvironmentVariables`
block rather than loading `.secrets` at runtime:

```bash
grep -l -r "BITGET\|GMAIL\|TELEGRAM" ~/Library/LaunchAgents/ 2>/dev/null
```

For a running process, inspect its environment without killing it.
This is platform-dependent:

```bash
# Linux: reliable, no privilege needed for own processes
cat /proc/<PID>/environ | tr '\0' '\n' | grep -E '^(SECRET|API|TOKEN)'

# macOS: /proc is absent. SIP blocks env inspection for most processes.
# For processes you own, launchctl is the most reliable path:
sudo launchctl procinfo <PID> | grep -i -E 'secret|api|token'

# Alternative on macOS: list file descriptors (sometimes reveals paths
# to config files that hold credentials, which is adjacent signal):
lsof -p <PID> | grep -i -E 'secret|config|\.env'
```

Do not rely on `ps` for env inspection — flags vary across macOS /
BSD / GNU and most combinations will silently omit env output under
SIP.

### 5. Identify actual consumers, not suspected ones

For each secret, run `grep -rn VAR_NAME` across the scripts directory
and follow imports. Two things matter:

- **Which script reads it at runtime** (not just references the name).
- **Which HTTP endpoints / SDK calls it hits** — this determines the
  minimum permissions the rotated credential needs.

## Output: the mapping table

Build one table per audit. Rows are secrets, columns are status.

| Secret | Consumers (scripts + JSONs + n8n) | Endpoints hit | Status |
| --- | --- | --- | --- |
| `ANTHROPIC_API_KEY` | `lib.py::ask_haiku` via `server.py /api/anthropic` | `api.anthropic.com/v1/messages` | ACTIVE |
| `BITGET_API_KEY` | `e1-economista.py`, `nexo-monitor.py`, `jarvis.py` | `/spot/market/tickers` (public), `/spot/account/assets`, `/earn/loan/*` | ACTIVE (Read-only, rotated) |
| `GMAIL_APP_PASSWORD_IMPULSO` | `form-lead-monitor.py`, `auto-followup.py`, `clientes/X/email_config.json` | IMAP + SMTP Google | ACTIVE |

Keep this table in a doc **outside** the repo so you can paste masked
values without leaking them into git history.

## Verification

Before calling the audit complete:

- Every `.secrets` line has at least one consumer identified. A secret
  with zero consumers is either dead code (candidate for removal) or an
  audit miss.
- Every hardcoded value found in step 2 is either (a) pointing to the
  same secret store or (b) a rotation target in its own right.
- Every n8n credential of type "generic" or "http-auth" is cross-matched
  with `.secrets`. Orphans there are frequent.

## Common mistakes and fixes

**Audit by name, not by usage.** You find `INSTAGRAM_ACCESS_TOKEN` in
`.secrets` and in `clientes/demo/cm_config.json` under the key
`instagram_access_token`. You conclude they are the same credential and
plan one rotation. Reality: the client JSON may be consulted first
(`cm_config.json` wins over env var), and `.secrets` is dead fallback.
Fix: read the consumer code to see which source it actually loads.

**Stopping at the repo.** The canonical store, client configs, and n8n
are three independent copies. Audit all three or you'll rotate in one
place and break the others.

**Not recording endpoints hit.** Without the endpoint list, you'll
re-generate the key with the same over-broad permissions next time. The
audit is where you capture "this script only does GET, so Read-only is
enough."

## Concrete example (masked)

During a real secrets audit, an Instagram access token living at
`clientes/<slug>/cm_config.json` was initially flagged as "old / likely
unused" because it shared a directory with retired content. After
reading `scripts/cm/publicador.py`, it turned out that file was checked
**before** the `.secrets` env var — so the JSON token was the actual
production credential and the `.secrets` one was the dead fallback.
Rotating the env var would have changed nothing; the JSON was the
target. The audit caught this only because step 5 was done.
