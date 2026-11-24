#!/usr/bin/env python3
"""Generate a single-file HTML dashboard from a SkillSpector JSON report.

Usage:
  python3 .github/scripts/generate_report_page.py \
      --report reports/skillspector-report.json \
      --dates reports/skill-dates.json \
      --out public/

Produces public/index.html. --previous-url is optional: when given and
reachable, findings already present in that previously published report are
marked as known and only new fingerprints are flagged "NEW" (on GitHub
Actions there is no Pages URL, so it is normally omitted). Only stdlib.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SEV_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def fetch_previous(url: str | None, timeout: int = 20) -> dict | None:
    if not url:
        return None
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def previous_fingerprints(previous: dict | None) -> dict[str, set]:
    """Map skill name -> set of match fingerprints in the previous report."""
    result: dict[str, set] = {}
    if not previous:
        return result
    for skill in previous.get("skills") or []:
        if not isinstance(skill, dict) or "error" in skill:
            continue
        fps: set = set()
        for issue in skill.get("issues") or []:
            fp = issue.get("match_fingerprint") or issue.get("finding_id")
            if fp:
                fps.add(str(fp))
        result[str(skill.get("name") or skill.get("path") or "")] = fps
    return result


def issue_key(issue: dict) -> str:
    return str(issue.get("match_fingerprint") or issue.get("finding_id") or "")


def build_data(report: dict, dates: dict[str, str], previous: dict | None,
               env: dict[str, str]) -> dict:
    prev_fps = previous_fingerprints(previous)
    skills_out = []
    total_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    total_new = 0

    for skill in report.get("skills") or []:
        if not isinstance(skill, dict):
            continue
        name = str(skill.get("name") or skill.get("path") or "?")
        if "error" in skill and skill["error"]:
            skills_out.append({
                "name": name,
                "path": str(skill.get("path") or ""),
                "error": str(skill["error"]),
                "risk_score": 0,
                "risk_severity": "LOW",
                "last_commit": dates.get(name, ""),
                "counts": {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0},
                "new_count": 0,
                "issues": [],
            })
            continue
        known = prev_fps.get(name)
        counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        issues_out = []
        new_count = 0
        for issue in skill.get("issues") or []:
            sev = str(issue.get("severity", "LOW")).upper()
            if sev not in counts:
                sev = "LOW"
            counts[sev] += 1
            total_counts[sev] += 1
            loc = issue.get("location") or {}
            is_new = known is None or issue_key(issue) not in known
            if is_new:
                new_count += 1
            issues_out.append({
                "id": str(issue.get("id") or "?"),
                "severity": sev,
                "category": str(issue.get("category") or ""),
                "pattern": str(issue.get("pattern") or ""),
                "file": str(loc.get("file") or "?"),
                "start_line": loc.get("start_line"),
                "finding": str(issue.get("finding") or ""),
                "explanation": str(issue.get("explanation") or ""),
                "remediation": str(issue.get("remediation") or ""),
                "code_snippet": str(issue.get("code_snippet") or ""),
                "confidence": issue.get("confidence"),
                "is_new": is_new,
            })
        issues_out.sort(key=lambda i: (SEV_ORDER.get(i["severity"], 9), i["file"], i["id"]))
        total_new += new_count
        skills_out.append({
            "name": name,
            "path": str(skill.get("path") or ""),
            "error": None,
            "risk_score": int(skill.get("risk_score") or 0),
            "risk_severity": str(skill.get("risk_severity") or "LOW").upper(),
            "last_commit": dates.get(name, "") or dates.get(str(skill.get("path") or ""), ""),
            "counts": counts,
            "new_count": new_count,
            "issues": issues_out,
        })

    issues_total = sum(total_counts.values())
    run_id = env.get("GITHUB_RUN_ID", "")
    run_url = ""
    if run_id:
        run_url = (f"{env.get('GITHUB_SERVER_URL', 'https://github.com')}"
                   f"/{env.get('GITHUB_REPOSITORY', '')}"
                   f"/actions/runs/{run_id}")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pipeline": {
            "url": run_url,
            "sha": env.get("GITHUB_SHA", "")[:10],
            "branch": env.get("GITHUB_REF_NAME", ""),
            "id": run_id,
        },
        "previous_available": previous is not None,
        "overall": {
            "skill_count": len(skills_out),
            "max_risk_score": int(report.get("max_risk_score") or 0),
            "risk_severity": str(report.get("risk_severity") or "LOW").upper(),
            "recommendation": str(report.get("risk_recommendation") or ""),
            "total_findings": issues_total,
            "total_new": total_new,
            "counts": total_counts,
        },
        "skills": skills_out,
    }


def risk_color(score: int) -> str:
    if score >= 80:
        return "#c62828"
    if score >= 60:
        return "#e65100"
    if score >= 40:
        return "#f9a825"
    if score >= 20:
        return "#7cb342"
    return "#2e7d32"


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Skills security report</title>
<style>
:root { --border:#ddd; --bg:#f6f7f9; }
* { box-sizing: border-box; }
body { font-family: -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
       margin: 0; background: var(--bg); color: #222; }
header { background: #1f2d3d; color: #fff; padding: 14px 22px; }
header h1 { margin: 0 0 4px; font-size: 20px; }
header .meta { font-size: 12.5px; opacity: .85; }
header a { color: #9fc1ff; }
main { padding: 16px 22px 40px; }
.cards { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 14px; }
.card { background: #fff; border: 1px solid var(--border); border-radius: 8px;
        padding: 10px 14px; min-width: 110px; }
.card .k { font-size: 11px; text-transform: uppercase; color: #777; letter-spacing: .04em; }
.card .v { font-size: 22px; font-weight: 600; margin-top: 2px; }
.controls { display: flex; flex-wrap: wrap; gap: 12px; align-items: center;
            background: #fff; border: 1px solid var(--border); border-radius: 8px;
            padding: 10px 12px; margin-bottom: 12px; }
.controls input[type=search] { padding: 6px 10px; border: 1px solid var(--border);
        border-radius: 6px; width: 240px; font-size: 13px; }
.controls label { font-size: 13px; display: inline-flex; align-items: center; gap: 5px;
                  cursor: pointer; user-select: none; }
.chip { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 11px;
        font-weight: 600; color: #fff; vertical-align: 1px; }
table { border-collapse: collapse; width: 100%; background: #fff;
       border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
th, td { padding: 7px 10px; text-align: left; font-size: 13px; }
thead th { background: #eef1f5; border-bottom: 2px solid var(--border); cursor: pointer;
           white-space: nowrap; user-select: none; }
thead th.sorted::after { content: " \\2193"; }
tbody tr.row { border-bottom: 1px solid #eceff3; cursor: pointer; }
tbody tr.row:hover { background: #f4f7fc; }
tbody tr.row.open { background: #eef3fb; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
.skill-name { font-weight: 600; }
.skill-path { color: #888; font-size: 11.5px; margin-left: 6px; }
.risk { font-weight: 700; }
tr.detail > td { background: #fbfcfe; border-bottom: 2px solid var(--border);
                padding: 12px 14px; }
.issue { border-left: 3px solid #ccc; background: #fff; border: 1px solid #e3e7ee;
         border-left-width: 3px; border-radius: 6px; padding: 10px 12px; margin-bottom: 10px; }
.issue h4 { margin: 0 0 6px; font-size: 13.5px; display: flex; gap: 8px;
            align-items: center; flex-wrap: wrap; }
.issue h4 code { background: #f0f2f6; padding: 1px 5px; border-radius: 4px;
                 font-size: 12px; }
.issue .loc { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 12px;
              color: #555; margin-bottom: 6px; }
.issue p { margin: 4px 0; font-size: 12.5px; line-height: 1.45; }
.issue pre { background: #f6f8fa; border: 1px solid #e3e7ee; padding: 8px;
             overflow-x: auto; font-size: 12px; border-radius: 5px; margin: 6px 0; }
.badge-new { background: #c62828; color: #fff; font-size: 10px; padding: 1px 7px;
             border-radius: 9px; font-weight: 700; letter-spacing: .05em; }
.err { color: #c62828; font-style: italic; }
footer { color: #888; font-size: 12px; margin-top: 12px; }
.hidden { display: none; }
</style>
</head>
<body>
<header>
  <h1>Skills security report &mdash; mdw-skills</h1>
  <div class="meta" id="meta"></div>
</header>
<main>
  <div class="cards" id="cards"></div>
  <div class="controls">
    <input type="search" id="search" placeholder="Filter skills or findings&hellip;">
    <label><input type="checkbox" class="sev" value="CRITICAL" checked> <span class="chip" style="background:#c62828">CRITICAL</span></label>
    <label><input type="checkbox" class="sev" value="HIGH" checked> <span class="chip" style="background:#e65100">HIGH</span></label>
    <label><input type="checkbox" class="sev" value="MEDIUM" checked> <span class="chip" style="background:#f9a825">MEDIUM</span></label>
    <label><input type="checkbox" class="sev" value="LOW" checked> <span class="chip" style="background:#7cb342">LOW</span></label>
    <label><input type="checkbox" id="newonly"> new findings only</label>
  </div>
  <table id="tbl">
    <thead><tr>
      <th data-sort="name">Skill</th>
      <th data-sort="last_commit">Last change</th>
      <th data-sort="risk_score" class="num">Risk</th>
      <th data-sort="new_count" class="num">New</th>
      <th data-sort="CRITICAL" class="num">C</th>
      <th data-sort="HIGH" class="num">H</th>
      <th data-sort="MEDIUM" class="num">M</th>
      <th data-sort="LOW" class="num">L</th>
      <th data-sort="total" class="num">Findings</th>
    </tr></thead>
    <tbody id="tbody"></tbody>
  </table>
  <footer id="footer"></footer>
</main>
<script>
const DATA = __DATA__;
const SEVCOLOR = {CRITICAL:"#c62828", HIGH:"#e65100", MEDIUM:"#f9a825", LOW:"#7cb342"};
let sortKey = "risk_score", sortAsc = false, openRow = null;

const esc = s => String(s ?? "").replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

function sevChips(counts) {
  return ["CRITICAL","HIGH","MEDIUM","LOW"].map(s =>
    counts[s] ? `<span class="chip" style="background:${SEVCOLOR[s]}">${counts[s]}</span>` :
    `<span class="chip" style="background:#cfd4dc">${counts[s] ?? 0}</span>`).join(" ");
}
function riskColor(score) {
  if (score >= 80) return "#c62828";
  if (score >= 60) return "#e65100";
  if (score >= 40) return "#f9a825";
  if (score >= 20) return "#7cb342";
  return "#2e7d32";
}
function fmtDate(iso) {
  if (!iso) return "\u2014";
  return iso.slice(0, 10);
}
function total(skill) { return skill.counts.CRITICAL + skill.counts.HIGH +
                               skill.counts.MEDIUM + skill.counts.LOW; }

function visibleIssues(skill) {
  const sevs = new Set([...document.querySelectorAll(".sev:checked")].map(c => c.value));
  const q = document.getElementById("search").value.trim().toLowerCase();
  const newOnly = document.getElementById("newonly").checked;
  return skill.issues.filter(i => {
    if (!sevs.has(i.severity)) return false;
    if (newOnly && !i.is_new) return false;
    if (q) {
      const hay = (skill.name + " " + skill.path + " " + i.id + " " + i.category +
        " " + i.pattern + " " + i.finding + " " + i.explanation + " " + i.file).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

function skillVisible(skill) {
  const issues = visibleIssues(skill);
  const q = document.getElementById("search").value.trim().toLowerCase();
  if (!issues.length) {
    return q && (skill.name + " " + skill.path).toLowerCase().includes(q) &&
           skill.error;
  }
  return true;
}

function issueHtml(i) {
  const sev = `<span class="chip" style="background:${SEVCOLOR[i.severity]}">${i.severity}</span>`;
  const isNew = i.is_new ? ` <span class="badge-new">NEW</span>` : "";
  const rule = `<code>${esc(i.id)}</code>`;
  const cat = i.category ? ` <span style="color:#888;font-weight:400">(${esc(i.category)})</span>` : "";
  const loc = `<div class="loc">${esc(i.file)}:${esc(i.start_line ?? "?")}</div>`;
  const snippet = i.code_snippet ? `<pre>${esc(i.code_snippet)}</pre>` : "";
  const expl = i.explanation ? `<p>${esc(i.explanation)}</p>` : "";
  const rem = i.remediation ? `<p><b>Remediation:</b> ${esc(i.remediation)}</p>` : "";
  const matched = i.finding ? `<p><b>Match:</b> <code>${esc(i.finding)}</code></p>` : "";
  return `<div class="issue" style="border-left-color:${SEVCOLOR[i.severity]}">
    <h4>${sev}${isNew}${rule}${cat}</h4>${loc}${snippet}${matched}${expl}${rem}</div>`;
}

function render() {
  const tbody = document.getElementById("tbody");
  const rows = [];
  const shown = DATA.skills.filter(skillVisible);
  shown.sort((a, b) => {
    let va, vb;
    if (sortKey === "name") { va = a.name.toLowerCase(); vb = b.name.toLowerCase(); }
    else if (sortKey === "last_commit") { va = a.last_commit; vb = b.last_commit; }
    else if (sortKey === "risk_score") { va = a.risk_score; vb = b.risk_score; }
    else if (sortKey === "new_count") { va = a.new_count; vb = b.new_count; }
    else if (sortKey === "total") { va = total(a); vb = total(b); }
    else { va = a.counts[sortKey] ?? 0; vb = b.counts[sortKey] ?? 0; }
    return (va < vb ? -1 : va > vb ? 1 : 0) * (sortAsc ? 1 : -1);
  });
  for (const s of shown) {
    const issues = visibleIssues(s);
    const riskCol = riskColor(s.risk_score);
    const name = `<span class="skill-name">${esc(s.name)}</span>` +
      (s.path ? `<span class="skill-path">${esc(s.path)}</span>` : "");
    const err = s.error ? `<span class="err"> &mdash; scan error: ${esc(s.error)}</span>` : "";
    const tr = `<tr class="row" data-skill="${esc(s.name)}">
      <td>${name}${err}</td>
      <td>${fmtDate(s.last_commit)}</td>
      <td class="num"><span class="risk" style="color:${riskCol}">${s.risk_score}</span></td>
      <td class="num">${s.new_count ? `<b style="color:#c62828">${s.new_count}</b>` : "0"}</td>
      <td class="num">${s.counts.CRITICAL || ""}</td>
      <td class="num">${s.counts.HIGH || ""}</td>
      <td class="num">${s.counts.MEDIUM || ""}</td>
      <td class="num">${s.counts.LOW || ""}</td>
      <td class="num">${total(s)}</td></tr>`;
    const detail = (openRow === s.name && issues.length)
      ? `<tr class="detail"><td colspan="9">${issues.map(issueHtml).join("")}</td></tr>`
      : "";
    rows.push(tr + detail);
  }
  tbody.innerHTML = rows.join("") ||
    `<tr><td colspan="9" style="text-align:center;color:#999;padding:20px">No skill matches the current filters.</td></tr>`;
  document.getElementById("footer").textContent =
    `${shown.length} of ${DATA.skills.length} skills shown. ` +
    `Findings per skill are collapsed; click a row to expand. ` +
    (DATA.previous_available
      ? "NEW = not present in the previously published report."
      : "No previous report found: every finding is considered NEW.");
}

function renderHeader() {
  const o = DATA.overall;
  const p = DATA.pipeline;
  const link = p.url ? `pipeline <a href="${esc(p.url)}">#${esc(p.id)} (${esc(p.sha)})</a>` : "";
  document.getElementById("meta").innerHTML =
    `Generated ${esc(DATA.generated_at)} &middot; branch ${esc(p.branch)} &middot; ${link}`;
  const cards = [
    ["Skills", o.skill_count, "#1f2d3d"],
    ["Findings", o.total_findings, "#c62828"],
    ["New", o.total_new, "#c62828"],
    ["Critical", o.counts.CRITICAL, SEVCOLOR.CRITICAL],
    ["High", o.counts.HIGH, SEVCOLOR.HIGH],
    ["Medium", o.counts.MEDIUM, SEVCOLOR.MEDIUM],
    ["Low", o.counts.LOW, SEVCOLOR.LOW],
    ["Max risk", o.max_risk_score, riskColor(o.max_risk_score)],
  ];
  document.getElementById("cards").innerHTML = cards.map(([k, v, c]) =>
    `<div class="card"><div class="k">${k}</div><div class="v" style="color:${c}">${v}</div></div>`).join("");
}

document.querySelectorAll("thead th").forEach(th => {
  th.addEventListener("click", () => {
    const key = th.dataset.sort;
    if (sortKey === key) { sortAsc = !sortAsc; }
    else { sortKey = key; sortAsc = (key === "name" || key === "last_commit"); }
    document.querySelectorAll("thead th").forEach(t => t.classList.remove("sorted"));
    th.classList.add("sorted");
    render();
  });
});
document.getElementById("tbody").addEventListener("click", ev => {
  const tr = ev.target.closest("tr.row");
  if (!tr) return;
  const name = tr.dataset.skill;
  openRow = (openRow === name) ? null : name;
  render();
});
document.getElementById("search").addEventListener("input", render);
document.getElementById("newonly").addEventListener("change", render);
document.querySelectorAll(".sev").forEach(c => c.addEventListener("change", render));
renderHeader();
render();
</script>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--dates", default="")
    ap.add_argument("--previous-url", default="")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.report, encoding="utf-8") as fh:
        report = json.load(fh)
    dates: dict[str, str] = {}
    if args.dates and Path(args.dates).is_file():
        with open(args.dates, encoding="utf-8") as fh:
            dates = json.load(fh)

    previous = fetch_previous(args.previous_url)
    data = build_data(report, dates, previous, dict(os.environ))

    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = HTML_TEMPLATE.replace("__DATA__", payload)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"Dashboard written to {out_dir / 'index.html'} "
          f"({data['overall']['skill_count']} skills, "
          f"{data['overall']['total_findings']} findings, "
          f"{data['overall']['total_new']} new)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
