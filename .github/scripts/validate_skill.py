#!/usr/bin/env python3
"""
Validate SKILL.md: frontmatter parses as YAML, required keys are
present, and every `workflows/<file>.md` reference in the body has a
matching file on disk.

Exits non-zero on the first failure so CI surfaces a real error code.
"""

import pathlib
import re
import sys
from typing import NoReturn

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
SKILL = ROOT / "SKILL.md"
WORKFLOWS_DIR = ROOT / "workflows"

REQUIRED_FRONTMATTER_KEYS = {"name", "description", "license"}


def fail(msg: str) -> NoReturn:
    print(f"::error::{msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    if not SKILL.is_file():
        fail(f"SKILL.md not found at {SKILL}")

    text = SKILL.read_text(encoding="utf-8")

    fm_match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not fm_match:
        fail("SKILL.md is missing a YAML frontmatter block delimited by ---")

    try:
        fm = yaml.safe_load(fm_match.group(1))
    except yaml.YAMLError as exc:
        fail(f"SKILL.md frontmatter is not valid YAML: {exc}")

    if not isinstance(fm, dict):
        fail("SKILL.md frontmatter must parse to a mapping")

    missing = REQUIRED_FRONTMATTER_KEYS - fm.keys()
    if missing:
        fail(
            "SKILL.md frontmatter is missing required keys: "
            + ", ".join(sorted(missing))
        )

    print(
        "SKILL.md frontmatter OK (name='{}', license='{}')".format(
            fm["name"], fm["license"]
        )
    )

    body = text[fm_match.end():]
    refs = sorted(
        set(re.findall(r"workflows/([a-z0-9][a-z0-9\-]*\.md)", body))
    )

    if not refs:
        fail("SKILL.md does not reference any workflow files")

    missing_files = [r for r in refs if not (WORKFLOWS_DIR / r).is_file()]
    if missing_files:
        fail(
            "SKILL.md references workflow files that do not exist on disk: "
            + ", ".join(missing_files)
        )

    print(f"All {len(refs)} referenced workflow files exist:")
    for r in refs:
        print(f"  - workflows/{r}")


if __name__ == "__main__":
    main()
