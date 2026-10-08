"""Folder layout shared by the builder, the mock services and the evaluation."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SAMPLES = DATA / "samples"
SEED = DATA / "seed"
INVOICES = DATA / "invoices"
WORKFLOWS = ROOT / "workflows"
RESULTS = ROOT / "results"
JS = Path(__file__).resolve().parent / "js"
RUNTIME = ROOT / ".runtime"
AI_CACHE = ROOT / "eval-cache" / "ai"

WORKFLOW_SLUGS = (
    "lead-intake",
    "supplier-invoice",
    "support-triage",
    "kpi-digest",
    "purchase-approval",
    "content-repurpose",
)
