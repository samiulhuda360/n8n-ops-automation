"""Builds every workflow JSON file in workflows/ from the definitions in opsflow/flows."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from opsflow.flows import (
    content_repurpose,
    error_handler,
    kpi_digest,
    lead_intake,
    purchase_approval,
    supplier_invoice,
    support_triage,
)
from opsflow.n8n import Flow
from opsflow.paths import WORKFLOWS

BUILDERS: dict[str, Callable[[], Flow]] = {
    "lead-intake": lead_intake.build,
    "supplier-invoice": supplier_invoice.build,
    "support-triage": support_triage.build,
    "kpi-digest": kpi_digest.build,
    "purchase-approval": purchase_approval.build,
    "content-repurpose": content_repurpose.build,
}


def all_workflows() -> dict[str, dict[str, Any]]:
    """The six business workflows (wired to the shared error workflow) plus the error workflow itself."""
    error = error_handler.build().build()
    out = {slug: fn().build(error_workflow_id=error["id"]) for slug, fn in BUILDERS.items()}
    out["error-handler"] = error
    return out


def render(wf: dict[str, Any]) -> str:
    return json.dumps(wf, indent=2, ensure_ascii=False) + "\n"


def write_all(folder: Path = WORKFLOWS) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for slug, wf in all_workflows().items():
        path = folder / f"{slug}.json"
        path.write_text(render(wf), encoding="utf-8")
        paths.append(path)
    return paths
