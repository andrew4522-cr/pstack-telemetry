---
name: reflect
description: "Run a three-lens post-execution reflection audit (Judgment, Tooling, Divergent) over active transcripts, `decisions.tsv` logs, scheduled tasks, and SQLite state. Stages concrete skill and `AGENTS.md` improvements behind an explicit approval gate."
metadata:
  version: 1.0.0
  source: "https://github.com/andrew4522-cr/pstack-telemetry"
---

# Reflect (`/reflect`): Three-Lens Self-Healing Loop

Mine execution logs, `decisions.tsv` trails, scheduled task statuses, and SQLite state for durable operational learnings, then route them into structural code checks or approval-gated edits to `SKILL.md` / `AGENTS.md`.

---

## 1. The Three Reviewer Lenses

1. **Judgment Lens:**
   - Evaluates candidate scoring, anti-repetition filters, lead qualification accuracy, and single-angle positioning rules.
2. **Tooling & Reliability Lens:**
   - Audits scheduled task exit codes, silent exception blocks, truncated LLM URLs, API retries, and database synchronization.
3. **Divergent / First-Principles Lens (`encode-lessons-in-structure`):**
   - Identifies whether a recurring lesson should be enforced directly in Python code (e.g. `verify_and_heal_github_markdown` or `PreSendGovernanceGate`) rather than adding prose instructions that an LLM might ignore.

---

## 2. Non-Negotiable Approval Gate

**`reflect` asks before it edits any skill or `AGENTS.md` file.**
- All proposed rule or skill modifications are staged in:
  - JSON queue: `reflect_proposals.json`
  - Human-readable report: `REFLECT_REPORT.md`
- No target `SKILL.md` or `AGENTS.md` file is mutated until explicitly approved via `--apply <PROPOSAL_ID>`.

---

## 3. Running `/reflect`

```bash
# 1. Run the 3-lens reflection audit and generate REFLECT_REPORT.md
pstack-telemetry --reflect

# 2. Apply a specific approved proposal (or ALL) after user approval
pstack-telemetry --apply PROP-001
```
