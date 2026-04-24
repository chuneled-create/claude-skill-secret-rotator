# Rotate exchange API keys with granular permissions

**Load when:** rotating API credentials for a crypto exchange with
granular permission scopes — BITGET, Binance, Kraken, OKX, Bybit. The
core difference from plain API keys: exchanges let you set Read /
Trade / Transfer / Withdraw permissions independently, and most also
require a **passphrase** (a user-chosen string that becomes part of
the HMAC signature).

## Why this workflow is longer than the others

Exchange credentials have the largest blast radius of any common
secret. A leaked key with Withdraw permission is equivalent to a
leaked wallet. The rotation itself is routine; the permission audit
is the hard part.

## 1. Blast radius analysis (do this first, not last)

Before rotating, understand what an attacker could do with the **old**
key if it leaked. Make this table for your specific old credential:

| Permission | What it allows | Worst case |
| --- | --- | --- |
| Read | GET market data + GET private account data (balances, open orders, history). | Attacker sees your positions; can front-run or copy. No capital moved. |
| Spot Trade | POST orders on spot markets. | Attacker can buy-high / sell-low to drain via bad fills, or pump-and-dump a low-cap pair holding your balance. |
| Futures / Contracts Trade | POST orders on derivatives with leverage. | Attacker opens max-leveraged losing positions → liquidation drains collateral in minutes. |
| Margin | Borrow + trade with borrowed funds. | Same as Futures: over-leveraged loss. |
| Transfer | Move funds between subaccounts / between accounts within the same exchange. | Attacker moves funds to an account they control (possible if the exchange allows transfers to arbitrary UIDs). |
| **Withdraw** | Send funds to an external wallet address. | **Direct theft.** The worst outcome. Often gated by address whitelist, but the whitelist itself is API-manageable on some exchanges. |

If the old key had Withdraw, assume direct theft is possible and treat
this as an active incident: rotate immediately, check the transaction
history for unauthorized withdrawals, and file a support ticket with
the exchange if anything looks off.

## 2. Determine the minimum permissions the new key actually needs

Every script that consumes the key has a finite set of HTTP endpoints
it hits. Map those endpoints to permissions and you get the new key's
permission set.

Process:

1. `grep -rn '<exchange-host>' ~/scripts` to find every call.
2. For each call, note the HTTP method and path.
3. Map each path to the exchange's permission matrix (read their API
   docs — the mapping is public).
4. The union of those permissions is the **minimum** set the new key
   needs.

Example mapping (BITGET):

| Endpoint your code hits | Method | Permission required |
| --- | --- | --- |
| `/api/v2/spot/market/tickers` | GET | none (public — can be signed or unsigned) |
| `/api/v2/spot/account/assets` | GET | Read |
| `/api/v2/earn/loan/ongoing-orders` | GET | Read |
| `/api/v2/earn/loan/debts` | GET | Read |
| `/api/v2/spot/trade/place-order` | POST | Spot Trade |
| `/api/v2/wallet/withdraw` | POST | Withdraw |

If the grep turns up only the first four rows, the new key needs only
**Read**. Granting anything more is giving the attacker more ammunition
the next time a key leaks.

## 3. Passphrase rules (the undocumented part)

Many exchanges require a passphrase as a third factor (along with key
and secret). The passphrase becomes part of the HMAC signature on
every request, so the consumer code and the exchange must agree on the
exact string.

**The problem:** exchanges enforce rules on passphrase characters that
they do **not** document. BITGET, for example, rejects passphrases
containing certain special characters with a generic "invalid
passphrase" error. Coinbase Advanced is stricter about character sets.

**The pragmatic fix:**

- Keep the passphrase simple: letters + digits + underscore. Length 8
  to 32.
- If the exchange rejects a passphrase with no clear error, reduce the
  character set further. Start from `[a-zA-Z0-9]` and retry.
- Store the passphrase only where the API key and secret are stored
  (same `.secrets`, same JSON) — it is a shared secret, not a
  "rememberable password".

## 4. IP whitelist (use it if your topology allows)

Most exchanges let you bind an API key to a list of source IP
addresses. Requests from any other IP are rejected regardless of
signature.

- **Server deployments with static IPs:** always use it. Free extra
  layer.
- **Home / developer machines:** residential IPs usually rotate via
  ISP DHCP every few days. IP whitelisting on a home machine means
  you'll silently lose access next Tuesday morning. Either skip the
  whitelist, or use a VPN with a static IP and whitelist the VPN's
  exit IP.
- **Dynamic DNS:** most exchanges require literal IPs, not hostnames.
  A hostname-based approach does not work with standard dashboards.

## 5. Walkthrough: BITGET

### 5a. Create the new key

Login at `bitget.com` → profile icon → *API Management* → *Create API
Key*.

Form fields:

- **Notes / name:** date-stamped, e.g. `ImpulsoIA-ReadOnly-20260421`.
- **Passphrase:** a simple alphanumeric string (follow section 3).
  Store it in `/tmp/new-bg-passphrase.txt` mode 600.
- **Permissions:** tick **Read only**. Leave Spot Trade, Futures,
  Margin, Transfer, and Withdraw unchecked.
- **IP whitelist:** if you have a static source IP, add it; otherwise
  leave blank.
- **Expiration:** set to 90 days if the dashboard allows it — forces a
  rotation cadence.

Submit. BITGET shows the **API Key** and the **Secret Key** once each.
Copy both into intermediate files:

```bash
touch /tmp/new-bg-key.txt /tmp/new-bg-secret.txt
chmod 600 /tmp/new-bg-key.txt /tmp/new-bg-secret.txt
# Paste API key into /tmp/new-bg-key.txt
# Paste Secret key into /tmp/new-bg-secret.txt
```

Triple-check: the API Key starts with `bg_` and is ~35 chars; the
Secret is a 64-char hex string.

### 5b. Test auth against a private endpoint

```bash
export NEW_API_KEY="$(cat /tmp/new-bg-key.txt | tr -d '[:space:]')"
export NEW_SECRET="$(cat /tmp/new-bg-secret.txt | tr -d '[:space:]')"
export NEW_PASSPHRASE="$(cat /tmp/new-bg-passphrase.txt | tr -d '[:space:]')"

python3 <<'PY'
import os, hmac, hashlib, base64, time, urllib.request, urllib.error, json

ts = str(int(time.time() * 1000))
method = 'GET'
path = '/api/v2/spot/account/assets'
msg = ts + method + path
sig = base64.b64encode(
    hmac.new(os.environ['NEW_SECRET'].encode(),
             msg.encode(), hashlib.sha256).digest()
).decode()

req = urllib.request.Request('https://api.bitget.com' + path)
req.add_header('ACCESS-KEY', os.environ['NEW_API_KEY'])
req.add_header('ACCESS-SIGN', sig)
req.add_header('ACCESS-TIMESTAMP', ts)
req.add_header('ACCESS-PASSPHRASE', os.environ['NEW_PASSPHRASE'])
req.add_header('Content-Type', 'application/json')

try:
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read())
    print(f"HTTP {r.status} code={data.get('code')} msg={data.get('msg')}")
    if data.get('code') == '00000':
        print(f"AUTH_OK ({len(data.get('data', []))} assets)")
    else:
        print("AUTH_FAIL_LOGIC — check passphrase or permissions")
except urllib.error.HTTPError as e:
    print(f"HTTP_ERROR {e.code}: {e.read().decode()[:200]}")
PY
```

Interpretation:

- `AUTH_OK` with N assets → the key has Read and the passphrase is
  correct. Proceed.
- `code=40001` or similar with "Invalid passphrase" → the passphrase
  was rejected. Go back to section 3 and simplify.
- `code=40003` "API key is not valid" → the key is not yet propagated
  (rare; wait 60s) or you mistyped it.
- `HTTP_ERROR 401/403` → wrong signature algorithm or clock skew >30s.

### 5c. Swap the three values in `.secrets`

```bash
cp ~/.secrets ~/.secrets.bak-bitget-rotation-$(date +%Y%m%d-%H%M)

python3 <<'PY'
import os, re, pathlib
p = pathlib.Path.home() / ".secrets"
c = p.read_text()
pairs = {
    'BITGET_API_KEY':    os.environ['NEW_API_KEY'],
    'BITGET_SECRET_KEY': os.environ['NEW_SECRET'],
    'BITGET_PASSPHRASE': os.environ['NEW_PASSPHRASE'],
}
out = c
for var, val in pairs.items():
    pat = rf'^({re.escape(var)}\s*=\s*)"[^"]*"'
    if not re.search(pat, out, flags=re.M):
        # fallback for unquoted format
        pat = rf'^(export\s+)?({re.escape(var)}=).*$'
        out = re.sub(pat, rf'\1\2{val}', out, flags=re.M)
    else:
        out = re.sub(pat, lambda m, v=val: m.group(1) + '"' + v + '"',
                     out, flags=re.M)
if out == c:
    raise SystemExit("ABORT: no variables replaced — check file format")
p.write_text(out)
print("swap OK, line count:", out.count('\n'))
PY

bash -n ~/.secrets && echo "syntax OK"
```

### 5d. Smoke test every consumer

For each script that uses BITGET, trigger a real call against one of
the production endpoints:

```bash
# Example: a script that fetches balances
python3 -c "
import sys; sys.path.insert(0, 'scripts')
import lib; lib._secrets_loaded = False; lib.load_secrets()
# import and call the specific function
"
```

Repeat for each consumer. Don't skip any — a consumer with a
hardcoded endpoint not covered by your audit will surface here.

### 5e. Wait for the longest scheduler cycle

If the consumers are cron jobs that run every 2h, wait 2h. If they are
KeepAlive daemons, a successful smoke test is enough. Revoking before
the longest cycle risks hours of silent failure before the next
scheduled run.

### 5f. Revoke the old key

Back at *API Management* → find the old key row → *Delete*. The old
key is dead immediately on the server side.

### 5g. Document

```
2026-04-21 12:36 — BITGET credentials rotated
  old: bg_7****a3e3  (Withdraw + Trade + Transfer + Read + 3 others)
  new: bg_8****8d74  (Read only)
  ip whitelist: none (home machine, residential IP)
  backup: ~/.secrets.bak-bitget-rotation-20260421-1236
  validated consumers:
    - e1-economista.py (balance + loans)
    - nexo-monitor.py (price + 24h change)
    - jarvis.py (price ticker)
  endpoints hit: /spot/market/tickers, /spot/account/assets,
                 /earn/loan/ongoing-orders, /earn/loan/debts (all GET)
  revoke time in Bitget dashboard: 2026-04-21 12:55
```

### 5h. Cleanup

Once the rotation is documented and the old key is revoked, purge the
intermediate files and environment variables. Leaving them around is
a persistent secret leak on shared machines — the new key values are
still in those files.

```bash
unset NEW_API_KEY NEW_SECRET NEW_PASSPHRASE
rm /tmp/new-bg-key.txt /tmp/new-bg-secret.txt /tmp/new-bg-passphrase.txt
```

See `workflows/common-pitfalls.md` for related cleanup pitfalls that
apply across all rotation types.

## Common mistakes and fixes

**Over-provisioning out of habit.** Ticking "all permissions" because
it's faster than reading your own code. Fix: always run the mapping
in section 2 before creating the key.

**Forgetting the passphrase is a third secret.** A correctly-rotated
key + secret with the wrong passphrase looks identical to a bad key
to most error handlers. First thing to suspect when auth fails
post-swap is the passphrase.

**Treating IP whitelist as fire-and-forget.** On residential ISPs it
will break you silently when your public IP rotates. Fix: only
whitelist from stable network locations, or accept the operational
cost of updating the whitelist weekly.

**Skipping the old-key revocation.** It's easy to stop after the new
key works. Then months later you discover the old key, with Withdraw,
still sitting in the provider dashboard. Revoking it is part of the
rotation, not an optional step.

## Real example (masked)

During a 2026-04-21 rotation, the old BITGET key had **all seven
permissions active**, including Withdraw, and no IP whitelist — the
worst-case profile for a leaked credential. The consumer audit
revealed only GET calls to four endpoints. The new key was created
with Read-only and a fresh alphanumeric passphrase; auth tested
successfully against `/spot/account/assets` before any `.secrets`
change. Full rotation (create → test → swap → smoke test across three
scripts → wait for the next `nexo-monitor.py` 2h cycle → revoke)
completed in about 20 minutes. The old key was then additionally
purged from git history via `git-filter-repo` in a separate pass.
