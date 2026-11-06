import tempfile
import unittest
from pathlib import Path

from pstack_telemetry import (
    DecisionLogger,
    PitchPerformanceTracker,
    PreSendGovernanceGate,
    ReflectEngine,
    extract_safe_first_name,
    is_generic_inbox,
    validate_campaign_unit_economics,
    verify_and_heal_github_markdown,
)


class TestPstackTelemetry(unittest.TestCase):
    def test_decision_logger_and_cross_run_start_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            tsv = Path(tmp) / "decisions.tsv"
            run1 = DecisionLogger(tsv_path=tsv, script_name="scanner", run_id="run-001")
            run1.log("harvest", "harvested 25 items", "daily sweep", "count=25", "PASS")

            run2 = DecisionLogger(tsv_path=tsv, script_name="scanner", run_id="run-002")
            run2.log("commit", "=committed +10 items", "save output", "count=10", "PASS")

            rows = DecisionLogger.read_recent(tsv, limit=10)
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0]["phase"], "harvest")
            # Second row must be an automatic cross-run `start` boundary row
            self.assertEqual(rows[1]["phase"], "start")
            self.assertEqual(rows[1]["result"], "OPEN")
            # Formula injection must be sanitized with leading apostrophe
            self.assertTrue(rows[2]["decision"].startswith("'="))

    def test_pre_send_governance_and_recursive_learning(self):
        with tempfile.TemporaryDirectory() as tmp:
            learned_path = Path(tmp) / "learned_generic_prefixes.json"
            gate = PreSendGovernanceGate(learned_prefixes_path=learned_path)

            # 1. Block generic inboxes & unreplaced placeholders
            res1 = gate.validate_outbound_message(
                recipient_email="info@acme.com",
                subject="Hi {first_name}",
                body="Quick question about {company}",
                contact_name="Operations Lead",
            )
            self.assertFalse(res1["valid"])
            self.assertEqual(res1["safe_first_name"], "there")

            # 2. Auto-heal placeholders
            healed, repairs = gate.heal_placeholders(
                "Hi {first_name}, saw {company} is scaling.",
                contact_name="Sarah Jenkins",
                company_name="Stripe",
            )
            self.assertEqual(healed, "Hi Sarah, saw Stripe is scaling.")
            self.assertEqual(len(repairs), 2)

            # 3. Recursive learning of a new generic prefix
            self.assertFalse(is_generic_inbox("customdesk@acme.com", learned_path))
            gate.learn_generic_token(prefix="customdesk", salutation_token="customdesk")
            self.assertTrue(is_generic_inbox("customdesk@acme.com", learned_path))
            self.assertEqual(extract_safe_first_name("Customdesk", default="there", learned_prefixes_path=learned_path), "there")

    def test_verify_and_heal_github_markdown(self):
        raw_md = (
            "### 1. owner/repo (https://github.com/repo)\n"
            "### 2. [acme/toolkit](https://github.com/toolkit) — fast agent\n"
        )
        healed, count, repairs = verify_and_heal_github_markdown(raw_md)
        self.assertEqual(count, 2)
        self.assertIn("[owner/repo](https://github.com/owner/repo)", healed)
        self.assertIn("[acme/toolkit](https://github.com/acme/toolkit)", healed)
        self.assertNotIn("\u2014", healed)
        self.assertGreaterEqual(len(repairs), 3)

    def test_reflect_engine_approval_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            tsv = tmp_path / "decisions.tsv"
            props = tmp_path / "reflect_proposals.json"
            report = tmp_path / "REFLECT_REPORT.md"
            agents_md = tmp_path / "AGENTS.md"
            agents_md.write_text("# Agent Rules\n", encoding="utf-8")

            engine = ReflectEngine(tsv_path=tsv, proposals_path=props, report_path=report)
            engine.stage_proposal(
                proposal_id="PROP-001",
                lens="Tooling Reviewer",
                target_file=str(agents_md),
                title="Enforce TSV logging",
                rationale="Prevent silent unattended runs",
                section_to_append="## Telemetry\n- Always log to decisions.tsv.",
            )
            # Target file must NOT be mutated before explicit approval
            self.assertNotIn("Always log to decisions.tsv", agents_md.read_text(encoding="utf-8"))

            engine.run_reflection()
            self.assertTrue(report.exists())

            engine.apply_proposal("PROP-001")
            self.assertIn("Always log to decisions.tsv", agents_md.read_text(encoding="utf-8"))

    def test_unit_economics_kill_gate(self):
        kill_res = validate_campaign_unit_economics(monthly_sends=6000, product_price=49.0)
        self.assertFalse(kill_res["viable"])
        self.assertEqual(kill_res["verdict"], "KILL")

        viable_res = validate_campaign_unit_economics(monthly_sends=6000, product_price=1500.0)
        self.assertTrue(viable_res["viable"])
        self.assertEqual(viable_res["verdict"], "VIABLE")


if __name__ == "__main__":
    unittest.main()
