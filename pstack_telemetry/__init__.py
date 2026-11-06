"""
pstack-telemetry: Self-Healing Agent Harness, TSV Decision Trails & Pre-Send Governance.
"""

from .core import (
    DecisionLogger,
    PreSendGovernanceGate,
    ReflectEngine,
    PitchPerformanceTracker,
    verify_and_heal_github_markdown,
    extract_safe_first_name,
    is_generic_inbox,
    validate_campaign_unit_economics,
    TSV_HEADER,
)

__version__ = "1.0.0"
__all__ = [
    "DecisionLogger",
    "PreSendGovernanceGate",
    "ReflectEngine",
    "PitchPerformanceTracker",
    "verify_and_heal_github_markdown",
    "extract_safe_first_name",
    "is_generic_inbox",
    "validate_campaign_unit_economics",
    "TSV_HEADER",
]
