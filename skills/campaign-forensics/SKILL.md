---
name: campaign-forensics
description: "Pre-launch viability gate and post-mortem framework for cold outreach campaigns. Use BEFORE launching any cold email, SMS, or LinkedIn outreach campaign to validate unit economics, and AFTER a campaign completes to run a structured post-mortem."
metadata:
  version: 1.0.0
  source: "https://github.com/andrew4522-cr/pstack-telemetry"
---

# Campaign Forensics — Pre-Launch Gate & Post-Mortem Framework

Prevent wasted time and sender reputation by catching non-viable campaigns BEFORE they launch, and extracting durable structural learnings AFTER they run.

---

## Mode 1: Pre-Launch Gate (The 5-Minute Unit Economics Kill Test)

Calculate the revenue ceiling using **conservative** benchmarks:
- Open rate: **25–35%**
- Click-through rate: **1.5–3%** of opens
- Reply rate: **1–3%** of opens
- Conversion rate (click $\rightarrow$ paid): **1–2%**

```
Monthly sends × Open rate × CTR × Conversion rate × Price = Monthly revenue ceiling

6,000 sends × 30% open × 2.5% CTR × 1.5% conversion × $49 = $33/month   -> KILL
6,000 sends × 30% open × 2.5% CTR × 1.5% conversion × $1,500 = $1,012/m -> VIABLE
```

Run via CLI:
```bash
pstack-telemetry --unit-economics 6000 49
pstack-telemetry --unit-economics 6000 1500
```

---

## Mode 2: Pre-Send Infrastructure & Quality Gates

1. **Zero Unreplaced Placeholders:** Block any outbound email, follow-up, or LinkedIn note containing raw template braces (`{first_name}`, `{{company}}`).
2. **Zero Generic/Shared Inboxes:** Never send outreach to generic aliases (`info@`, `careers@`, `support@`, `dataprotection@`, `press@`).
3. **Active Campaign Slot Verification:** Verify via API progress check that started campaigns are `Active` (not silently paused at `0%` due to active-campaign slot limits).
4. **Headline-to-Company Token Verification:** Verify extracted company tokens across all headline separators (`at`, `@`, `-`, `|`) before sending any LinkedIn DM.
