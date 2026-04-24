# Secret Rotator

`Battle-tested` · `MIT` · `Claude Skill`

A Claude skill that walks through credential rotations step by step.
Covers pre-rotation audit, type-specific workflows (API keys, Gmail App
Passwords, Telegram bot tokens, exchange credentials with granular
permissions), and the pitfalls that make rotations go wrong in the real
world.

Built for developers and solo operators who run their own services,
keep secrets in `~/.secrets` or JSON configs, and have occasionally
leaked a key into git history at 2am. The workflows assume you are
managing your own infrastructure — not a large team with a vault
manager, not a toy side-project. Somewhere in between.

## Installation

Clone into your Claude skills directory:

```bash
mkdir -p ~/.claude/skills
cd ~/.claude/skills
git clone https://github.com/chuneled-create/claude-skill-secret-rotator.git secret-rotator
```

The skill is picked up automatically on the next Claude Code / Claude
Desktop restart. Verify it loaded:

```bash
ls -la ~/.claude/skills/secret-rotator/SKILL.md
```

No other setup is required. The skill is plain markdown plus a YAML
frontmatter — no dependencies, no runtime.

## Usage

The skill activates automatically when you mention rotation work in
natural language. Example prompts:

```
I need to rotate my Anthropic API key because I think it leaked
into a Slack channel.
```

```
Found my old Gmail app password in a commit from 2 months ago.
Help me rotate it safely.
```

```
My BITGET keys have Withdraw permission and I don't trust who saw
the repo. I want to downgrade permissions and rotate.
```

When triggered, Claude will load the relevant workflow from this repo
and walk you through the steps — backup, test, swap, smoke test, wait,
revoke, document. Each workflow has a "Load when" line in `SKILL.md`
so Claude pulls only the one that matches your credential type.

## What's included

| File | Purpose |
| --- | --- |
| `SKILL.md` | The skill manifest: activation triggers, five non-negotiable principles, and the standard 10-step flow. |
| `workflows/audit-before-rotation.md` | Map every secret and every consumer before you rotate anything. |
| `workflows/rotate-api-keys.md` | Generic `sk-*`/`pk-*` API keys — Anthropic, OpenAI, Stripe, SendGrid, and the fallback for anything else. |
| `workflows/rotate-gmail-app-passwords.md` | Gmail App Passwords with 2FA, including the with-spaces / without-spaces format trap. |
| `workflows/rotate-telegram-bot-tokens.md` | Telegram bot tokens via BotFather, including multi-tenant JSON updates. |
| `workflows/rotate-exchange-keys-with-permissions.md` | Exchange credentials with granular permissions (BITGET, Binance, Kraken). The one with the blast-radius analysis and the Withdraw trap. |
| `workflows/common-pitfalls.md` | The top five errors we actually hit — clipboard collisions, audit-by-name, rotating before mapping consumers — and their fixes. |
| `LICENSE` | MIT. |

## Scope (v1)

- Pre-rotation audit
- Rotation by credential type
- Recovery from common failure modes

## Roadmap (v2)

- Git history cleaning with `git-filter-repo` after rotation
- Compliance checklists (SOC 2, ISO 27001)
- Vault manager integrations (1Password, Doppler, Infisical)
- Scheduled rotation cadence (monthly/quarterly)
- Incident response playbooks

## Contributing

Issues and PRs welcome. Useful contributions:

- A new workflow for a credential type not yet covered (AWS, GCP,
  Cloudflare API tokens, etc.)
- A real-world pitfall with masked reproduction steps and the fix
- Translations of the workflows to other languages

Open an issue first if you want to discuss the shape of a workflow
before writing it.

## License

MIT. See [LICENSE](LICENSE).
