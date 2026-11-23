#!/usr/bin/env python3
"""CI gate for the SkillSpector report.

Usage: python3 .github/scripts/check_gate.py reports/skillspector-report.json

Exit codes:
  0  no active finding at or above the gate severity
  1  at least one active finding at or above the gate severity
  2  report unreadable or a skill scan errored (fail closed)

Gate severity is controlled by the GATE_MIN_SEVERITY environment variable
(LOW | MEDIUM | HIGH | CRITICAL, default HIGH).
"""
from __future__ import annotations

import json
import os
import sys

ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def gate_severity() -> str:
    raw = os.environ.get("GATE_MIN_SEVERITY", "HIGH").upper()
    return raw if raw in ORDER else "HIGH"


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: check_gate.py <report.json>", file=sys.stderr)
        return 2
    threshold = ORDER[gate_severity()]
    try:
        with open(sys.argv[1], encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:  # unreadable report -> fail closed
        print(f"GATE FAIL: cannot read report: {exc}", file=sys.stderr)
        return 2

    skills = data.get("skills") or []
    important: list[tuple] = []
    errors: list[str] = []
    total = 0
    for skill in skills:
        if not isinstance(skill, dict):
            continue
        if "error" in skill and skill["error"]:
            errors.append(f"{skill.get('name', '?')}: {skill['error']}")
            continue
        issues = skill.get("issues") or []
        total += len(issues)
        for issue in issues:
            sev = str(issue.get("severity", "LOW")).upper()
            if ORDER.get(sev, 0) >= threshold:
                loc = issue.get("location") or {}
                important.append(
                    (
                        skill.get("name", "?"),
                        sev,
                        str(issue.get("id", "?")),
                        str(loc.get("file", "?")),
                        str(loc.get("start_line", "?")),
                    )
                )

    if errors:
        print("GATE FAIL: skill scan errors (fail closed):")
        for e in errors:
            print(f"  - {e}")
        return 2

    if important:
        print(
            f"GATE FAIL: {len(important)} active finding(s) at or above "
            f"{gate_severity()} (total active findings: {total}):"
        )
        for name, sev, rule, fname, line in important[:80]:
            print(f"  - {name}: [{sev}] {rule} ({fname}:{line})")
        if len(important) > 80:
            print(f"  ... and {len(important) - 80} more")
        return 1

    print(f"GATE PASS: no active finding at or above {gate_severity()} "
          f"(total active findings: {total})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
