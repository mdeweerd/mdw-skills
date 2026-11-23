#!/usr/bin/env python3
"""Merge per-skill SkillSpector JSON reports into one multi_skill report.

Usage:
  python3 .github/scripts/merge_skill_reports.py \
      --repo-root .agents/skills --reports-dir reports/by-skill \
      --out reports/skillspector-report.json

The scan job scans each skill directory under the skills root separately
(the recursive multi-skill mode of SkillSpector supports neither --baseline
nor --use-shipped-baseline, but per-skill baselines are how accepted
findings are suppressed). This script reassembles the per-skill JSON
reports into the same "multi_skill" JSON shape that 'skillspector scan
--recursive' produces, so the gate and the report consumers keep an
identical report.

Fail-closed: a skill directory without a report file, an unreadable
report, or a recorded scan error becomes an {"name", "error"} entry,
which the gate treats as a pipeline failure.

Only stdlib. Skill count budget does not apply (no recursive mode
involved).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Mirrors skillspector/nodes/report.py: _RISK_SEVERITY_BANDS and
# _RISK_RECOMMENDATION (v2.13.1), so aggregate risk matches upstream.
RISK_BANDS = [(81, "CRITICAL"), (51, "HIGH"), (21, "MEDIUM")]
RECOMMENDATION = {
    "LOW": "SAFE",
    "MEDIUM": "CAUTION",
    "HIGH": "DO_NOT_INSTALL",
    "CRITICAL": "DO_NOT_INSTALL",
}


def severity_for(score: int) -> str:
    for threshold, band in RISK_BANDS:
        if score >= threshold:
            return band
    return "LOW"


def recommendation_for(severity: str) -> str:
    return RECOMMENDATION.get(severity, "CAUTION")


def skill_dirs(root: Path) -> list[Path]:
    # Same discovery rule as .github/scripts/list_skill_dirs.py and
    # SkillSpector's recursive mode: SKILL.md manifest or an AISOP
    # *.aisop.json bundle.
    out: list[Path] = []
    for p in sorted(root.iterdir()):
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


def load_error(reports_dir: Path, name: str) -> str:
    err_file = reports_dir / f"{name}.error"
    if err_file.is_file():
        try:
            data = json.loads(err_file.read_text(encoding="utf-8"))
            return str(data.get("error") or "scan error")
        except Exception:
            raw = err_file.read_text(encoding="utf-8").strip()
            if raw:
                return raw
    return "scan did not produce a report for this skill"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", default=".agents/skills",
                    help="skills root containing one directory per skill")
    ap.add_argument("--reports-dir", default="reports/by-skill")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    root = Path(args.repo_root)
    reports_dir = Path(args.reports_dir)
    dirs = skill_dirs(root)
    if not dirs:
        print("FATAL: no skill directories found under " + str(root),
              file=sys.stderr)
        return 2

    skills: list[dict] = []
    scanned = 0
    failed: list[str] = []
    max_score = 0

    for d in dirs:
        name = d.name
        report_file = reports_dir / f"{name}.json"
        if not report_file.is_file():
            message = load_error(reports_dir, name)
            skills.append({"name": name, "error": message})
            failed.append(name)
            continue
        try:
            payload = json.loads(report_file.read_text(encoding="utf-8"))
        except Exception as exc:
            skills.append({"name": name, "error": f"unreadable report: {exc}"})
            failed.append(name)
            continue
        if not isinstance(payload, dict):
            skills.append({"name": name, "error": "unexpected report shape"})
            failed.append(name)
            continue

        # Mirror the recursive assembly in skillspector/cli.py: the whole
        # single-skill report body is the entry payload, then the aggregate
        # keys are (re)forced from the scan result.
        entry = dict(payload)
        assessment = payload.get("risk_assessment") or {}
        issues = payload.get("issues") or []
        entry["name"] = str((payload.get("skill") or {}).get("name") or name)
        entry["path"] = name
        try:
            entry["risk_score"] = int(assessment.get("score") or 0)
        except (TypeError, ValueError):
            entry["risk_score"] = 0
        entry["risk_severity"] = str(assessment.get("severity") or "LOW").upper()
        entry["finding_count"] = len(issues)
        entry["execution_successful"] = bool(payload.get("execution_successful", True))
        entry["transitive_finding_count"] = int(payload.get("transitive_finding_count") or 0)
        entry["transitive_sources"] = list(payload.get("transitive_sources") or [])

        if not entry["execution_successful"]:
            failed.append(name)
        else:
            scanned += 1
            max_score = max(max_score, entry["risk_score"])
        skills.append(entry)

    execution_failed = bool(failed)
    aggregate_severity = severity_for(max_score)
    aggregate_recommendation = recommendation_for(aggregate_severity)
    if execution_failed:
        aggregate_recommendation = "DO_NOT_INSTALL"

    transitive_count = sum(
        int(s.get("transitive_finding_count") or 0) for s in skills if "error" not in s
    )
    transitive_sources = sorted(
        {
            str(src)
            for s in skills
            if "error" not in s
            for src in (s.get("transitive_sources") or [])
        }
    )

    combined: dict = {
        "multi_skill": True,
        "skill_count": len(dirs),
        "max_risk_score": max_score,
        "risk_severity": aggregate_severity,
        "execution_successful": not execution_failed,
        "risk_recommendation": aggregate_recommendation,
        "analysis_completeness": {
            "is_complete": not execution_failed,
            "status": "complete" if not execution_failed else "partial",
            "execution_successful": not execution_failed,
        },
        "skills_scanned": scanned,
        "skills_omitted": 0,
        "skills_output_omitted": 0,
        "public_finding_records": len(skills),
        "transitive_finding_count": transitive_count,
        "transitive_sources": transitive_sources,
        "skills": skills,
    }
    combined["report_characters"] = len(json.dumps(combined, indent=2))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(combined, fh, indent=2)
        fh.write("\n")

    total_findings = sum(s.get("finding_count", 0) for s in skills if "error" not in s)
    print(
        f"Merged {len(skills)} skill report(s) into {out}: "
        f"{scanned} scanned, {len(failed)} failed, "
        f"max risk {max_score} ({aggregate_severity}), "
        f"{total_findings} active finding(s)"
    )
    if failed:
        print(f"FAILED SKILLS: {', '.join(failed)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
