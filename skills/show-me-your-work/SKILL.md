---
name: show-me-your-work
description: "Keep a reviewable decision trail for long-running, scheduled, or unattended work: a single-line TSV log (`decisions.tsv`) with one row per decision (`ts | phase | decision | why | evidence | result`)."
metadata:
  version: 1.0.0
  source: "https://github.com/andrew4522-cr/pstack-telemetry"
---

# Show Me Your Work (`/show-me-your-work`)

Maintain one canonical, single-line TSV decision trail (`decisions.tsv`) across autonomous runs so a human operator can audit every fork, verification check, and self-healing repair in under 60 seconds.

---

## 1. Canonical TSV Specification

Header row:
```tsv
ts	phase	decision	why	evidence	result
```

Columns:
- **`ts`**: ISO 8601 UTC timestamp (`YYYY-MM-DDTHH:MM:SSZ`).
- **`phase`**: The workstream or lifecycle stage (`start`, `frame`, `harvest`, `verify_heal`, `inbound_scan`, `pipeline_sync`, `dispatch`, `reflect`, `health_audit`).
- **`decision`**: What was chosen or done, in one plain-spoken sentence (no AI slop or em-dashes).
- **`why`**: The concrete rationale in plain words.
- **`evidence`**: A concrete pointer (`file:line`, report filename, item count, exit code, HTTP status, or DB row count). Never write speculative prose in the evidence column.
- **`result`**: Outcome predicate (`PASS`, `HEALED`, `ISSUES`, `BLOCKED`, `APPLIED`, `OPEN`).

### Cross-Run `start` Row Protocol
Whenever a new agent run appends to an existing `decisions.tsv` written by an earlier run, its first row automatically uses `phase = start`, naming the timestamp range of the prior run's entries and recording the new `run_id` in the `evidence` column.

---

## 2. CLI & Python Usage

```bash
# Log a verified decision checkpoint
pstack-telemetry --log --script "daily_scanner" --phase "verify" --decision "verified 20 <24h opportunities" --why "enforce strict Snowflake ID recency" --evidence "LATEST_20_OPPORTUNITIES.md, count=20" --result "PASS"

# Inspect the last 20 decision rows
pstack-telemetry --tail 20
```

```python
from pstack_telemetry import DecisionLogger

dlog = DecisionLogger("decisions.tsv", script_name="daily_skills_scanner")
dlog.log(
    phase="commit",
    decision="committed 10 fresh tools to daily_intel_report.md",
    why="persist daily intelligence report and update pipeline metrics",
    evidence="report=daily_intel_report.md, total_history=150",
    result="PASS",
)
```
