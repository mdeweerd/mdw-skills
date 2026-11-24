#!/usr/bin/env python3
"""Collect the last commit date of every top-level skill directory.

Usage: python3 .github/scripts/collect_git_dates.py [repo_root] > skill-dates.json
Output: {"<skill-dir-name>": "YYYY-MM-DD", ...}
Only stdlib; run inside the CI checkout where git is available.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def last_commit_date(repo: Path, name: str) -> str:
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", name],
            capture_output=True,
            text=True,
            cwd=repo,
            timeout=30,
        )
    except Exception:
        return ""
    if out.returncode != 0:
        return ""
    return out.stdout.strip()


def skill_dirs(repo: Path) -> list[Path]:
    # Same discovery rule as .github/scripts/list_skill_dirs.py: SKILL.md or AISOP
    # *.aisop.json bundle.
    out: list[Path] = []
    for p in sorted(repo.iterdir()):
        if not p.is_dir():
            continue
        if (p / "SKILL.md").is_file():
            out.append(p)
            continue
        try:
            entries = list(p.iterdir())
        except OSError:
            continue
        if any(
            q.is_file() and q.name.lower().endswith(".aisop.json") for q in entries
        ):
            out.append(p)
    return out


def main() -> int:
    repo = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    dates: dict[str, str] = {}
    for d in skill_dirs(repo):
        dates[d.name] = last_commit_date(repo, d.name)
    json.dump(dates, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
