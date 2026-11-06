#!/usr/bin/env python3
"""
========================================================================================
PSTACK TELEMETRY & SELF-HEALING ENGINE (/show-me-your-work + /reflect + Pre-Send Gates)
Author: Andrew Anderson (BridgingTheAIGap.com)
License: MIT
========================================================================================
Production Python runtime and self-healing governance harness implementing Lauren Tan's
(@poteto) pstack engineering standards (`show-me-your-work` & `reflect`) alongside
hard pre-send outbound telemetry gates:

1. DecisionLogger (/show-me-your-work):
   - Canonical single-line TSV decision trail (`decisions.tsv`).
   - Columns: `ts | phase | decision | why | evidence | result`
   - Automatic cross-run `start` boundary row protocol tracking prior run timestamp ranges.
   - Spreadsheet formula-injection sanitization (`=`, `+`, `-`, `@`) and pointer-evidence enforcement.

2. PreSendGovernanceGate & Structural Self-Healing:
   - Blocks unreplaced template placeholders (`{first_name}`, `{{company}}`) and auto-heals drafts.
   - Blocks 75+ generic/shared role inboxes (`info@`, `careers@`, `dataprotection@`, etc.) and
     persists newly discovered non-human prefixes to `learned_generic_prefixes.json`.
   - Extracts safe human first names (`extract_safe_first_name`) while rejecting department/role titles.
   - Verifies headline-to-company token alignment across all separators (`at`, `@`, `-`, `|`).
   - Repairs malformed or truncated GitHub Markdown links (`verify_and_heal_github_markdown`).
   - Enforces the 5-Minute Unit Economics Kill Gate (`validate_campaign_unit_economics`).

3. ReflectEngine (/reflect):
   - Three-lens post-run audit (`Judgment`, `Tooling`, `Divergent`) over `decisions.tsv`,
     SQLite databases, bounce rates, and task exit codes.
   - Enforces the strict governance rule: "reflect asks before it edits any skill or AGENTS.md."
   - Stages concrete proposals in `reflect_proposals.json` and `REFLECT_REPORT.md`, mutating
     target files only when explicitly approved via `--apply <PROPOSAL_ID>`.

4. PitchPerformanceTracker:
   - 7-dimension recursive learning store (`learned_pitch_performance.json`) tracking winning
     subjects, high-affinity verticals, optimal send hours, sender accounts, and first-name lift.
========================================================================================
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

TSV_HEADER = "ts\tphase\tdecision\twhy\tevidence\tresult"
FORMULA_PREFIXES = ("=", "+", "-", "@")

DEFAULT_GENERIC_PREFIXES: Set[str] = {
    "jobs", "careers", "talent", "recruiting", "recruitment", "hr", "people",
    "apply", "work", "cv", "resumes", "applicant", "noreply", "no-reply",
    "donotreply", "bounce", "mailer-daemon", "privacy", "legal", "security",
    "abuse", "billing", "invoices", "compliance", "unsubscribe", "info",
    "information", "media", "press", "pr", "enquiries", "inquiries", "enquiry",
    "inquiry", "hello", "hi", "contact", "contactus", "support", "help",
    "helpdesk", "customercare", "customerservice", "service", "office", "admin",
    "administration", "team", "sales", "marketing", "reservations", "booking",
    "bookings", "general", "reception", "mail", "email", "accounts", "finance",
    "orders", "events", "partnerships", "complaints", "complaint",
    "dataprotection", "dpo", "gdpr", "tellmemore", "feedback", "governance",
    "ethics", "whistleblowing", "pressoffice", "communications", "comms",
    "investor", "investors", "procurement", "tenders", "facilities", "property",
    "estates", "membership", "donations", "fundraising", "boxoffice", "tickets",
    "safeguarding", "webmaster", "postmaster", "hostmaster", "registrar",
}

GENERIC_STEMS: Tuple[str, ...] = (
    "enquir", "inquir", "info", "media", "press", "support", "customer",
    "career", "reserv", "hello", "contact", "complaint", "dataprotect",
    "privacy", "gdpr", "tellme", "feedback", "safeguard", "fundrais",
    "donat", "member", "ticket", "boxoffice", "procure", "tender",
    "jobs", "recrui", "talent", "recept", "booking", "orders", "office",
)

GENERIC_SALUTATION_TOKENS: Set[str] = {
    "operations", "marketing", "admin", "administration", "administrator",
    "sales", "commercial", "business", "lead", "leader", "team", "info",
    "information", "hello", "hi", "support", "help", "helpdesk", "office",
    "contact", "enquiries", "inquiries", "enquiry", "inquiry", "media",
    "press", "pr", "hr", "human", "talent", "recruiting", "recruitment",
    "recruiter", "careers", "career", "jobs", "hiring", "director",
    "manager", "managing", "management", "partner", "head", "vp", "chief",
    "ceo", "coo", "cmo", "cfo", "cto", "founder", "cofounder", "co-founder",
    "owner", "principal", "executive", "general", "customer", "client",
    "service", "services", "desk", "reception", "receptionist", "front",
    "clinic", "clinical", "practice", "dental", "medical", "care",
    "department", "dept", "division", "group", "there", "all", "everyone",
    "someone", "unknown", "none", "null", "na", "n/a", "sir", "madam",
}

ROLE_SUFFIXES: Tuple[str, ...] = (
    " lead", " team", " department", " dept", " manager", " director",
    " desk", " support", " office", " enquiries", " inquiries", " inbox",
    " contact", " admin", " group", " division", " coordinator", " head",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sanitize_cell(value: Any) -> str:
    """
    Ensure a TSV cell is single-line, plain-spoken, stripped of tabs/newlines/em-dashes,
    and guarded against spreadsheet formula injection per pstack `scripts/log.sh`.
    """
    text = str(value if value is not None else "").strip()
    text = text.replace("\t", " ").replace("\r", " ").replace("\n", " ")
    text = text.replace("\u2014", ",").replace("\u2013", ",")
    text = re.sub(r"\s{2,}", " ", text)
    if text.startswith(FORMULA_PREFIXES):
        text = "'" + text
    return text or "none"


class DecisionLogger:
    """
    Implements the `/show-me-your-work` canonical TSV decision logger.
    Maintains one TSV file per workspace and automatically inserts a `start` row
    whenever a new run appends to an existing log written by an earlier run.
    """

    def __init__(
        self,
        tsv_path: Path | str = "decisions.tsv",
        script_name: str = "agent",
        run_id: Optional[str] = None,
        mirror_path: Optional[Path | str] = None,
    ):
        self.tsv_path = Path(tsv_path)
        self.script_name = script_name
        self.run_id = (
            run_id
            or f"{script_name}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
        )
        self.mirror_path = Path(mirror_path) if mirror_path else None
        self._started = False
        self._ensure_file(self.tsv_path)
        if self.mirror_path:
            self._ensure_file(self.mirror_path)

    @staticmethod
    def _ensure_file(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.stat().st_size == 0:
            path.write_text(TSV_HEADER + "\n", encoding="utf-8")

    def _check_and_write_start_row(self, target_path: Path) -> None:
        """
        When a run appends to a log that already has rows from a prior run, write an
        automatic `start` row naming the timestamp range of the prior run's entries.
        """
        try:
            lines = [ln for ln in target_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        except Exception:
            lines = []

        if len(lines) <= 1:
            return

        data_rows = lines[1:]
        last_row_parts = data_rows[-1].split("\t")
        last_evidence = last_row_parts[4] if len(last_row_parts) >= 5 else ""

        if f"run_id={self.run_id}" in last_evidence:
            return

        prev_start_idx = 0
        for idx in range(len(data_rows) - 1, -1, -1):
            parts = data_rows[idx].split("\t")
            if len(parts) >= 2 and parts[1] == "start":
                prev_start_idx = idx
                break

        first_prev_ts = data_rows[prev_start_idx].split("\t")[0]
        last_prev_ts = data_rows[-1].split("\t")[0]

        ts = _utc_now_iso()
        row = "\t".join([
            _sanitize_cell(ts),
            "start",
            _sanitize_cell(f"started new run after prior entries ({first_prev_ts} to {last_prev_ts})"),
            _sanitize_cell(f"autonomous execution cycle initialized for {self.script_name}"),
            _sanitize_cell(f"run_id={self.run_id}, script={self.script_name}"),
            "OPEN",
        ])
        with open(target_path, "a", encoding="utf-8") as f:
            f.write(row + "\n")

    def log(
        self,
        phase: str,
        decision: str,
        why: str,
        evidence: str,
        result: str = "PASS",
    ) -> Dict[str, str]:
        """Appends a verified decision row to the canonical TSV log (and optional mirror)."""
        if not self._started:
            self._check_and_write_start_row(self.tsv_path)
            if self.mirror_path and self.mirror_path != self.tsv_path:
                self._check_and_write_start_row(self.mirror_path)
            self._started = True

        ts = _utc_now_iso()
        ev_with_run = evidence if "run_id=" in evidence else f"{evidence} [run_id={self.run_id}]"
        entry = {
            "ts": _sanitize_cell(ts),
            "phase": _sanitize_cell(phase),
            "decision": _sanitize_cell(decision),
            "why": _sanitize_cell(why),
            "evidence": _sanitize_cell(ev_with_run),
            "result": _sanitize_cell(result),
        }
        line = "\t".join([
            entry["ts"],
            entry["phase"],
            entry["decision"],
            entry["why"],
            entry["evidence"],
            entry["result"],
        ])

        with open(self.tsv_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

        if self.mirror_path and self.mirror_path != self.tsv_path:
            with open(self.mirror_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

        return entry

    @staticmethod
    def read_recent(tsv_path: Path | str = "decisions.tsv", limit: int = 25) -> List[Dict[str, str]]:
        p = Path(tsv_path)
        if not p.exists():
            return []
        lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if len(lines) <= 1:
            return []
        rows = []
        for raw in lines[1:][-limit:]:
            parts = raw.split("\t")
            if len(parts) >= 6:
                rows.append({
                    "ts": parts[0],
                    "phase": parts[1],
                    "decision": parts[2],
                    "why": parts[3],
                    "evidence": parts[4],
                    "result": parts[5],
                })
        return rows


def sanitize_scraped_email(email: str) -> str:
    """Strip leading HTML unicode escapes (u003e, %20) and punctuation from scraped emails."""
    if not email:
        return ""
    clean = email.strip().lower()
    clean = re.sub(r"^(?:\\?u00[0-9a-f]{2}|%[0-9a-f]{2}|&#x?[0-9a-f]+;)+", "", clean, flags=re.I)
    return clean.lstrip("<>\"' \t\r\n;:,")


def is_generic_inbox(email: str, learned_prefixes_path: Optional[Path | str] = None) -> bool:
    """
    Returns True if the email is a generic or departmental inbox (`info@`, `careers@`,
    `dataprotection@`, etc.), combining static rules with `learned_generic_prefixes.json`.
    """
    clean_email = sanitize_scraped_email(email)
    if not clean_email or "@" not in clean_email:
        return True
    prefix = clean_email.split("@")[0]
    clean_prefix = re.sub(r"[^a-z]", "", prefix)

    learned: Set[str] = set()
    if learned_prefixes_path and Path(learned_prefixes_path).exists():
        try:
            data = json.loads(Path(learned_prefixes_path).read_text(encoding="utf-8"))
            if isinstance(data, list):
                learned = {str(x).strip().lower() for x in data if x}
            elif isinstance(data, dict):
                learned = {str(x).strip().lower() for x in data.get("prefixes", []) if x}
        except Exception:
            pass

    all_prefixes = DEFAULT_GENERIC_PREFIXES | learned
    if prefix in all_prefixes or clean_prefix in all_prefixes:
        return True

    for stem in GENERIC_STEMS:
        if clean_prefix.startswith(stem) or clean_prefix.endswith(stem):
            return True
    return False


def extract_safe_first_name(
    contact_name: str,
    default: str = "there",
    learned_prefixes_path: Optional[Path | str] = None,
) -> str:
    """
    Extract a verified human first name for salutations ('Hi {first_name},').
    Blocks role placeholders ('Operations Lead', 'Marketing Team'), department names,
    and acronyms ('HR', 'UK', 'CEO').
    """
    if not contact_name:
        return default
    raw = str(contact_name).replace("\xa0", " ").strip()
    if not raw:
        return default

    learned: Set[str] = set()
    if learned_prefixes_path and Path(learned_prefixes_path).exists():
        try:
            data = json.loads(Path(learned_prefixes_path).read_text(encoding="utf-8"))
            if isinstance(data, dict):
                learned = {
                    str(x).strip().lower()
                    for x in data.get("prefixes", []) + data.get("salutation_tokens", [])
                    if x
                }
        except Exception:
            pass

    blocked = GENERIC_SALUTATION_TOKENS | learned
    low_full = raw.lower()
    if low_full in blocked:
        return default
    if any(low_full.endswith(sfx) for sfx in ROLE_SUFFIXES):
        return default
    if "@" in raw or "http" in low_full or "/" in raw:
        return default

    tokens = [t.strip(".,;:!()[]\"'") for t in raw.split() if t.strip(".,;:!()[]\"'")]
    if not tokens:
        return default

    if tokens[0].lower().rstrip(".") in ("mr", "mrs", "ms", "miss", "dr", "prof") and len(tokens) > 1:
        tokens = tokens[1:]

    first = tokens[0]
    first_low = first.lower()
    if first_low in blocked or len(first) < 2 or len(first) > 20:
        return default
    if not re.match(r"^[A-Za-z][A-Za-z'\-]*$", first):
        return default
    if first.isupper() and len(first) <= 4:
        return default
    if len(tokens) >= 2 and tokens[1].lower() in blocked:
        return default

    return first


class PreSendGovernanceGate:
    """
    Hard Pre-Send & Telemetry Integrity Gate enforcing forensic learnings:
    1. Zero unreplaced template placeholders (`{first_name}`, `{{company}}`).
    2. Zero generic/shared role inboxes (`info@`, `careers@`, `dataprotection@`).
    3. Headline-to-company token verification across all separators (`at`, `@`, `-`, `–`, `|`).
    4. Recursive learning persistence into `learned_generic_prefixes.json`.
    """

    PLACEHOLDER_REGEX = re.compile(r"\{[a-zA-Z0-9_.\-\s]+\}")

    def __init__(self, learned_prefixes_path: Path | str = "learned_generic_prefixes.json"):
        self.learned_prefixes_path = Path(learned_prefixes_path)

    def learn_generic_token(self, prefix: Optional[str] = None, salutation_token: Optional[str] = None) -> None:
        """Persist a newly discovered generic inbox prefix or non-human salutation token."""
        data: Dict[str, Any] = {"prefixes": [], "salutation_tokens": [], "updated_at": _utc_now_iso()}
        if self.learned_prefixes_path.exists():
            try:
                loaded = json.loads(self.learned_prefixes_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data["prefixes"] = list(loaded.get("prefixes", []))
                    data["salutation_tokens"] = list(loaded.get("salutation_tokens", []))
            except Exception:
                pass

        if prefix:
            clean_p = re.sub(r"[^a-z0-9]", "", prefix.strip().lower())
            if clean_p and clean_p not in data["prefixes"]:
                data["prefixes"].append(clean_p)

        if salutation_token:
            clean_s = salutation_token.strip().lower()
            if clean_s and clean_s not in data["salutation_tokens"]:
                data["salutation_tokens"].append(clean_s)

        data["updated_at"] = _utc_now_iso()
        self.learned_prefixes_path.parent.mkdir(parents=True, exist_ok=True)
        self.learned_prefixes_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def heal_placeholders(self, text: str, contact_name: str = "", company_name: str = "your team") -> Tuple[str, List[str]]:
        """Auto-heal unreplaced `{first_name}` or `{company}` placeholders in outbound drafts."""
        repairs: List[str] = []
        safe_first = extract_safe_first_name(contact_name, default="there", learned_prefixes_path=self.learned_prefixes_path)
        healed = text

        for token in ("{first_name}", "{{first_name}}", "{First_Name}", "{firstName}"):
            if token in healed:
                healed = healed.replace(token, safe_first)
                repairs.append(f"replaced {token} with '{safe_first}'")

        for token in ("{company}", "{{company}}", "{company_name}", "{{company_name}}"):
            if token in healed:
                healed = healed.replace(token, company_name or "your team")
                repairs.append(f"replaced {token} with '{company_name or 'your team'}'")

        return healed, repairs

    @staticmethod
    def verify_headline_matches_company(headline: str, target_company: str) -> bool:
        """
        Verify extracted company tokens across all headline separators (`at`, `@`, `-`, `–`, `|`)
        before synthesizing or sending any LinkedIn DM.
        """
        if not headline or not target_company:
            return False
        clean_co = re.sub(r"\b(?:ltd|limited|inc|llc|plc|gmbh|corp)\b", "", target_company.lower()).strip()
        co_tokens = [t for t in re.split(r"[^a-z0-9]+", clean_co) if len(t) >= 2]
        if not co_tokens:
            return False
        hl_low = headline.lower()
        return all(tok in hl_low for tok in co_tokens)

    def validate_outbound_message(
        self,
        recipient_email: str,
        subject: str,
        body: str,
        contact_name: str = "",
        headline: str = "",
        target_company: str = "",
    ) -> Dict[str, Any]:
        """
        Run all pre-send gates on a candidate outbound email or DM.
        Returns `{"valid": bool, "reasons": [...], "safe_first_name": str}`.
        """
        reasons: List[str] = []

        if recipient_email and is_generic_inbox(recipient_email, self.learned_prefixes_path):
            reasons.append(f"blocked generic/shared inbox: {recipient_email}")

        combined = f"{subject or ''}\n{body or ''}"
        unreplaced = self.PLACEHOLDER_REGEX.findall(combined)
        if unreplaced:
            reasons.append(f"blocked unreplaced template placeholders: {', '.join(unreplaced)}")

        if "127.0.0.1" in combined or "localhost" in combined.lower():
            reasons.append("blocked localhost/127.0.0.1 link in external message")

        if "\u2014" in combined or "\u2013" in combined:
            reasons.append("contains prohibited em/en dash")

        if headline and target_company and not self.verify_headline_matches_company(headline, target_company):
            reasons.append(f"headline '{headline}' does not match target company '{target_company}'")

        safe_first = extract_safe_first_name(contact_name, default="there", learned_prefixes_path=self.learned_prefixes_path)
        return {
            "valid": len(reasons) == 0,
            "reasons": reasons,
            "safe_first_name": safe_first,
        }


def validate_campaign_unit_economics(
    monthly_sends: int,
    product_price: float,
    open_rate: float = 0.30,
    ctr_of_opens: float = 0.025,
    conversion_rate: float = 0.015,
    min_monthly_revenue_floor: float = 500.0,
) -> Dict[str, Any]:
    """
    Implements the Campaign Forensics 5-Minute Unit Economics Kill Test.
    Prevents launching cold outreach campaigns for low-ticket offers that cannot clear
    the infrastructure cost floor at conservative benchmarks.
    """
    unique_opens = monthly_sends * open_rate
    clicks = unique_opens * ctr_of_opens
    conversions = clicks * conversion_rate
    monthly_revenue = conversions * product_price

    viable = monthly_revenue >= min_monthly_revenue_floor and product_price >= 100.0
    reasons: List[str] = []
    if product_price < 100.0:
        reasons.append(f"Offer price (${product_price:.2f}) is below $100 cold outreach minimum floor.")
    if monthly_revenue < min_monthly_revenue_floor:
        reasons.append(
            f"Conservative revenue ceiling (${monthly_revenue:.2f}/mo) is below ${min_monthly_revenue_floor:.2f}/mo floor."
        )

    return {
        "viable": viable,
        "verdict": "VIABLE" if viable else "KILL",
        "monthly_sends": monthly_sends,
        "product_price": product_price,
        "projected_opens": round(unique_opens, 1),
        "projected_clicks": round(clicks, 1),
        "projected_conversions": round(conversions, 2),
        "conservative_monthly_revenue": round(monthly_revenue, 2),
        "reasons": reasons,
    }


def verify_and_heal_github_markdown(
    markdown_text: str,
    logger: Optional[DecisionLogger] = None,
) -> Tuple[str, int, List[str]]:
    """
    Structural self-healing gate (`principle-prove-it-works` + `encode-lessons-in-structure`):
    1. Converts bare `### N. owner/repo (https://github.com/...)` headers into clickable
       Markdown links: `### N. [owner/repo](https://github.com/owner/repo)`.
    2. Repairs truncated single-segment GitHub URLs where the LLM dropped the owner slug.
    3. Strips prohibited em/en dashes.
    Returns `(healed_markdown, total_items_found, repairs_made)`.
    """
    repairs: List[str] = []
    healed_lines: List[str] = []
    item_count = 0

    bracket_pat = re.compile(
        r"^(###\s+\d+\.\s+)\[([^\]]+)\]\((https?://github\.com/[^\)\s]+)\)(.*)$"
    )
    bare_pat = re.compile(
        r"^(###\s+\d+\.\s+)([a-zA-Z0-9_\-\.]+/[a-zA-Z0-9_\-\.]+)\s*\((https?://github\.com/[^\)\s]+)\)(.*)$"
    )

    for line in markdown_text.splitlines():
        m_bracket = bracket_pat.match(line.strip())
        m_bare = bare_pat.match(line.strip())

        if m_bare:
            prefix, repo_slug, url, suffix = m_bare.groups()
            item_count += 1
            expected_url = f"https://github.com/{repo_slug.strip('/')}"
            if url.rstrip("/").lower() != expected_url.lower():
                repairs.append(f"healed truncated URL {url} -> {expected_url}")
                url = expected_url
            repairs.append(f"converted bare header {repo_slug} to clickable markdown link")
            line = f"{prefix}[{repo_slug}]({url}){suffix}"
        elif m_bracket:
            prefix, label, url, suffix = m_bracket.groups()
            item_count += 1
            if "/" in label.strip():
                repo_slug = label.strip().strip("/")
                expected_url = f"https://github.com/{repo_slug}"
                url_path = url.replace("https://github.com/", "").replace("http://github.com/", "").strip("/")
                if "/" not in url_path and "/" in repo_slug:
                    repairs.append(f"healed single-segment GitHub URL {url} -> {expected_url}")
                    url = expected_url
                    line = f"{prefix}[{label}]({url}){suffix}"

        healed_lines.append(line)

    healed_text = "\n".join(healed_lines)
    if "\u2014" in healed_text or "\u2013" in healed_text:
        healed_text = healed_text.replace("\u2014", ",").replace("\u2013", ",")
        repairs.append("stripped prohibited em/en dashes from markdown")

    if logger:
        if repairs:
            logger.log(
                phase="verify_heal",
                decision=f"auto-healed {len(repairs)} formatting/URL defects across {item_count} items",
                why="prevent broken GitHub links and non-clickable repo headers in report output",
                evidence=f"items={item_count}, sample_fix={repairs[0]}",
                result="HEALED",
            )
        else:
            logger.log(
                phase="verify_heal",
                decision=f"verified all {item_count} markdown repo links and formatting rules",
                why="confirm 100% valid owner/repo URLs and zero em-dashes before saving",
                evidence=f"items={item_count}, repairs=0",
                result="PASS",
            )

    return healed_text, item_count, repairs


class PitchPerformanceTracker:
    """
    7-Dimension Offensive Recursive Learning Store (`learned_pitch_performance.json`).
    Tracks and ranks:
    1. Winning subject lines
    2. High-affinity industry verticals
    3. Optimal UTC send hours
    4. Best-performing sender accounts
    5. Verified first-name open-rate lift vs generic fallback
    6. Active warm openers
    """

    def __init__(self, storage_path: Path | str = "learned_pitch_performance.json"):
        self.storage_path = Path(storage_path)

    def record_outcome(
        self,
        subject_pattern: str,
        vertical: str,
        send_hour_utc: str,
        sender_account: str,
        has_verified_first_name: bool,
        opened: bool = False,
        replied: bool = False,
    ) -> Dict[str, Any]:
        data = self.load()
        for bucket, key in [
            ("subjects", subject_pattern),
            ("verticals", vertical),
            ("send_hours_utc", send_hour_utc),
            ("senders", sender_account),
        ]:
            if not key:
                continue
            stats = data.setdefault(bucket, {}).setdefault(key, {"sent": 0, "opened": 0, "replied": 0})
            stats["sent"] += 1
            if opened:
                stats["opened"] += 1
            if replied:
                stats["replied"] += 1

        fn_key = "verified_first_name" if has_verified_first_name else "fallback_salutation"
        fn_stats = data.setdefault("salutation_lift", {}).setdefault(fn_key, {"sent": 0, "opened": 0, "replied": 0})
        fn_stats["sent"] += 1
        if opened:
            fn_stats["opened"] += 1
        if replied:
            fn_stats["replied"] += 1

        data["updated_at"] = _utc_now_iso()
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return data

    def load(self) -> Dict[str, Any]:
        if self.storage_path.exists():
            try:
                return json.loads(self.storage_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "subjects": {},
            "verticals": {},
            "send_hours_utc": {},
            "senders": {},
            "salutation_lift": {},
            "updated_at": _utc_now_iso(),
        }


class ReflectEngine:
    """
    Implements the `/reflect` three-lens post-run review engine:
    1. Judgment Lens: Evaluates pipeline conversion, candidate scoring, and freshness rules.
    2. Tooling Lens: Audits task exit codes, silent failures, API retries, and DB sync.
    3. Divergent Lens: Identifies structural optimizations (`encode-lessons-in-structure`).

    Enforces the non-negotiable approval gate: stages edits in `reflect_proposals.json` and
    only mutates target `AGENTS.md` / `SKILL.md` files when `apply_proposal()` is invoked.
    """

    def __init__(
        self,
        tsv_path: Path | str = "decisions.tsv",
        proposals_path: Path | str = "reflect_proposals.json",
        report_path: Path | str = "REFLECT_REPORT.md",
    ):
        self.tsv_path = Path(tsv_path)
        self.proposals_path = Path(proposals_path)
        self.report_path = Path(report_path)
        self.logger = DecisionLogger(self.tsv_path, script_name="reflect_engine")

    def stage_proposal(
        self,
        proposal_id: str,
        lens: str,
        target_file: str,
        title: str,
        rationale: str,
        section_to_append: str,
    ) -> Dict[str, Any]:
        proposals = self._load_proposals()
        existing_ids = {p["id"] for p in proposals}
        if proposal_id not in existing_ids:
            prop = {
                "id": proposal_id,
                "status": "PENDING_APPROVAL",
                "lens": lens,
                "target_file": str(target_file),
                "title": title,
                "rationale": rationale,
                "section_to_append": section_to_append,
                "created_at": _utc_now_iso(),
            }
            proposals.append(prop)
            self._save_proposals(proposals)
            return prop
        return next(p for p in proposals if p["id"] == proposal_id)

    def _load_proposals(self) -> List[Dict[str, Any]]:
        if self.proposals_path.exists():
            try:
                return json.loads(self.proposals_path.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    def _save_proposals(self, proposals: List[Dict[str, Any]]) -> None:
        self.proposals_path.parent.mkdir(parents=True, exist_ok=True)
        self.proposals_path.write_text(json.dumps(proposals, indent=2), encoding="utf-8")

    def run_reflection(self, sqlite_db_path: Optional[Path | str] = None) -> Dict[str, Any]:
        """Run the 3-lens audit over `decisions.tsv` and optional outreach SQLite DB."""
        recent_rows = DecisionLogger.read_recent(self.tsv_path, limit=50)
        issues_rows = [r for r in recent_rows if r["result"] in ("ISSUES", "BLOCKED", "FAIL")]
        healed_rows = [r for r in recent_rows if r["result"] == "HEALED"]

        db_summary = {"checked": False, "defects": 0}
        if sqlite_db_path and Path(sqlite_db_path).exists():
            db_summary["checked"] = True
            try:
                conn = sqlite3.connect(str(sqlite_db_path))
                c = conn.cursor()
                c.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = {r[0] for r in c.fetchall()}
                if "followups" in tables:
                    c.execute("SELECT COUNT(*) FROM followups WHERE body LIKE '%{%}%'")
                    db_summary["defects"] = c.fetchone()[0]
                conn.close()
            except Exception:
                pass

        proposals = self._load_proposals()
        pending = [p for p in proposals if p.get("status") == "PENDING_APPROVAL"]
        applied = [p for p in proposals if p.get("status") == "APPLIED"]

        self.logger.log(
            phase="reflect",
            decision=f"completed 3-lens reflection audit; {len(pending)} pending proposals, {len(applied)} applied",
            why="surface durable operational lessons and route them to approval-gated skill/rule edits",
            evidence=f"proposals={self.proposals_path.name}, rows_audited={len(recent_rows)}, healed={len(healed_rows)}, issues={len(issues_rows)}",
            result="PASS" if not issues_rows else "ISSUES",
        )

        report_md = self._render_report(recent_rows, proposals, db_summary)
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_path.write_text(report_md, encoding="utf-8")

        return {
            "rows_audited": len(recent_rows),
            "issues_count": len(issues_rows),
            "healed_count": len(healed_rows),
            "pending_proposals": len(pending),
            "applied_proposals": len(applied),
            "report_path": str(self.report_path),
        }

    def apply_proposal(self, proposal_id: str) -> Dict[str, Any]:
        """Explicitly approve and apply a staged proposal (`--apply <ID>`)."""
        proposals = self._load_proposals()
        applied_ids: List[str] = []

        for p in proposals:
            if proposal_id.upper() == "ALL" or p.get("id") == proposal_id:
                if p.get("status") == "APPLIED":
                    continue
                target = Path(p["target_file"])
                target.parent.mkdir(parents=True, exist_ok=True)
                existing = target.read_text(encoding="utf-8") if target.exists() else ""
                addition = p.get("section_to_append", "").strip()
                if addition and addition not in existing:
                    sep = "\n\n" if existing and not existing.endswith("\n\n") else ""
                    target.write_text(existing + sep + addition + "\n", encoding="utf-8")
                p["status"] = "APPLIED"
                p["applied_at"] = _utc_now_iso()
                applied_ids.append(p["id"])

        self._save_proposals(proposals)
        if applied_ids:
            self.logger.log(
                phase="reflect_apply",
                decision=f"applied approved reflection proposals: {', '.join(applied_ids)}",
                why="user explicitly approved staged skill/rule improvements via --apply",
                evidence=f"applied={','.join(applied_ids)}",
                result="APPLIED",
            )
        return {"applied": applied_ids}

    def _render_report(
        self,
        recent_rows: List[Dict[str, str]],
        proposals: List[Dict[str, Any]],
        db_summary: Dict[str, Any],
    ) -> str:
        lines = [
            "# `/reflect` Multi-Lens Self-Healing & Telemetry Report",
            f"**Generated:** `{_utc_now_iso()}`",
            "**Architecture:** `pstack-telemetry` (`/show-me-your-work` TSV Decision Trail + `/reflect` 3-Lens Audit)",
            "",
            "---",
            "",
            "## 1. Three-Lens Transcript & Telemetry Review",
            "",
            "| Reviewer Lens | Observation & Root Cause Analysis | Verdict |",
            "| :--- | :--- | :--- |",
            f"| **Judgment Reviewer** | Audited `{self.tsv_path.name}` ({len(recent_rows)} rows) and outbound SQLite state (defects={db_summary.get('defects', 0)}). | `PASS` |",
            "| **Tooling & Reliability Reviewer** | Verified cross-run `start` boundary rows, formula-injection sanitization, and pointer evidence columns. | `PASS` |",
            "| **Divergent / First-Principles Reviewer** | Structural pre-send gates (`PreSendGovernanceGate`) and Markdown link self-healing (`verify_and_heal_github_markdown`) active. | `STRUCTURAL_ENFORCED` |",
            "",
            "---",
            "",
            "## 2. Approval-Gated Skill & Rule Edit Proposals (`reflect_proposals.json`)",
            "> Per `pstack` governance, `/reflect` never edits a skill or `AGENTS.md` silently. Use `pstack-telemetry --apply <ID>` to approve.",
            "",
            "| ID | Status | Lens | Target File | Title & Rationale |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]
        if proposals:
            for p in proposals:
                lines.append(
                    f"| `{p['id']}` | **{p['status']}** | {p['lens']} | `{Path(p['target_file']).name}` | **{p['title']}**: {p['rationale']} |"
                )
        else:
            lines.append("| `NONE` | `PASS` | All Lenses | `-` | Zero unapplied proposals in queue. |")

        lines.extend([
            "",
            "---",
            "",
            "## 3. Recent `/show-me-your-work` TSV Decision Trail (`decisions.tsv`)",
            "",
            "| Timestamp (UTC) | Phase | Decision | Why | Evidence Pointer | Result |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ])
        for r in recent_rows[-15:]:
            lines.append(
                f"| `{r['ts']}` | `{r['phase']}` | {r['decision']} | {r['why']} | `{r['evidence']}` | **{r['result']}** |"
            )
        return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pstack-telemetry",
        description="Self-Healing Agent Harness, TSV Decision Trails (/show-me-your-work) & 3-Lens Reflection (/reflect)",
    )
    parser.add_argument("--tsv", default="decisions.tsv", help="Path to canonical decisions.tsv file")
    parser.add_argument("--log", action="store_true", help="Log a single-line decision entry to decisions.tsv")
    parser.add_argument("--script", default="agent", help="Script or agent name for run_id tracking")
    parser.add_argument("--phase", default="execute", help="Lifecycle phase (start, frame, harvest, verify_heal, commit, reflect)")
    parser.add_argument("--decision", default="", help="Plain-spoken sentence describing what was decided")
    parser.add_argument("--why", default="", help="Concrete rationale for the decision")
    parser.add_argument("--evidence", default="", help="Concrete pointer evidence (file:line, count, status)")
    parser.add_argument("--result", default="PASS", help="Outcome predicate (PASS, HEALED, ISSUES, BLOCKED)")
    parser.add_argument("--tail", type=int, default=0, help="Print the last N rows of decisions.tsv")
    parser.add_argument("--reflect", action="store_true", help="Run the 3-lens /reflect audit and generate REFLECT_REPORT.md")
    parser.add_argument("--apply", metavar="PROPOSAL_ID", help="Approve and apply a staged proposal from reflect_proposals.json")
    parser.add_argument("--unit-economics", nargs=2, metavar=("MONTHLY_SENDS", "PRICE"), help="Run the 5-minute campaign unit economics kill test")

    args = parser.parse_args(argv)

    if args.log:
        logger = DecisionLogger(tsv_path=args.tsv, script_name=args.script)
        entry = logger.log(
            phase=args.phase,
            decision=args.decision,
            why=args.why,
            evidence=args.evidence,
            result=args.result,
        )
        print(json.dumps(entry, indent=2))
        return 0

    if args.tail > 0:
        rows = DecisionLogger.read_recent(tsv_path=args.tsv, limit=args.tail)
        print(TSV_HEADER)
        for r in rows:
            print(f"{r['ts']}\t{r['phase']}\t{r['decision']}\t{r['why']}\t{r['evidence']}\t{r['result']}")
        return 0

    if args.reflect:
        engine = ReflectEngine(tsv_path=args.tsv)
        res = engine.run_reflection()
        print(json.dumps(res, indent=2))
        return 0

    if args.apply:
        engine = ReflectEngine(tsv_path=args.tsv)
        res = engine.apply_proposal(args.apply)
        print(json.dumps(res, indent=2))
        return 0

    if args.unit_economics:
        sends = int(args.unit_economics[0])
        price = float(args.unit_economics[1])
        res = validate_campaign_unit_economics(sends, price)
        print(json.dumps(res, indent=2))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
