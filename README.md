# mdw-skills

Generic, reusable AI agent skills. Each skill is a self-contained directory
that can be copied into the `.agents/skills/` directory of any project or
agent environment.

## Skills

| Skill | Purpose |
|---|---|
| ai-act-ui-transparency | EU AI Act (Regulation (EU) 2024/1689) design requirements for conversational AI UIs: interaction transparency (Art. 50(1)), prohibited practices (Art. 5), generated-content labelling (Art. 50(2)-(4)) |

## Repository structure

```
.agents/skills/
├── README.md                      <- rules for the skills of this repository
└── <skill-name>/
    ├── SKILL.md
    └── LICENSE
```

## Security

Every push, every pull request, a manual trigger and a monthly schedule run a
SkillSpector (NVIDIA/SkillSpector) security scan of every skill
(.github/workflows/skills-scan.yml). The pipeline fails when a scan errors
(fail closed) or when an active finding is at or above the gate severity
(GATE_MIN_SEVERITY, default HIGH). A skill may carry a committed
.skillspector-baseline.yaml to suppress accepted findings before scoring.

Latest scan result (auto-updated on main by the pipeline):
<a href="https://cdn.jsdelivr.net/gh/mdeweerd/mdw-skills@main/docs/skillspector-report.html" target="skillspector-report">Skills security report (SkillSpector dashboard)</a>
(served from the repo via the jsdelivr GitHub domain, so the page renders
with its scripts; the raw-content equivalent is
https://raw.githubusercontent.com/mdeweerd/mdw-skills/main/docs/skillspector-report.html)

## Repository rules (binding)

1. Each skill lives in `.agents/skills/<skill-name>/` and contains at least `SKILL.md` (agentskills.io format, English) and `LICENSE` (complete, unaltered).
2. Every skill is distributed under the Skill Protection License: CC BY-ND 4.0 with additional restrictions. The full terms, permitted use and indemnities are in the LICENSE file of each skill directory, and in the LICENSE file at the root of this repository.
3. The LICENSE file travels with the skill: copying or exporting a skill without its complete LICENSE text is a breach of the license.
4. Republication of a skill on any platform or service that republishes or distributes AI agent skills (marketplace, registry, directory, rating or ranking service, or equivalent) requires the prior written authorization of the copyright holder. Platforms must not modify the skills and must not be remunerated for modifying or republishing them.
   - Breach of the republication prohibition: EUR 200 (two hundred euros) per day and per skill, without prior formal notice (mise en demeure), payable to mdeweerd or to the company he designates.
   - A modified skill containing instructions to report information to an external service (for example skill rating or telemetry): EUR 2,000 (two thousand euros) per day and per skill, without prior formal notice.
5. Any use without platform republication is permitted, including effective use in open-source projects and internal projects.
6. Skills are generic: no company, project or client references.
