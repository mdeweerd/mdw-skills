#!/usr/bin/env python3
"""Print the skill directories under the given root, one per line.

A directory is a skill when it contains a SKILL.md, or when it directly
contains an AISOP structured-skill manifest (*.aisop.json). This is the
same discovery rule as SkillSpector's recursive multi-skill mode, so the
per-skill scan loop covers exactly the skills the recursive mode would
scan (neither more, which would fail closed on non-skill directories, nor
less, which would silently skip skills).

Usage: python3 .github/scripts/list_skill_dirs.py [skills-root]
"""
from __future__ import annotations

import sys
from pathlib import Path


def skill_dir_names(root: Path) -> list[str]:
    out: list[str] = []
    for p in sorted(root.iterdir()):
        if not p.is_dir():
            continue
        if (p / "SKILL.md").is_file():
            out.append(p.name)
            continue
        try:
            entries = list(p.iterdir())
        except OSError:
            continue
        if any(
            q.is_file() and q.name.lower().endswith(".aisop.json") for q in entries
        ):
            out.append(p.name)
    return out


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".agents/skills").resolve()
    for name in skill_dir_names(root):
        print(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
