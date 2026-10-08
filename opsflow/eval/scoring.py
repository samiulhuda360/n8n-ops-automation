"""Scores one workflow run against the labels in data/samples.

Every item gets a row of named checks (True, False, or None when a check doesn't apply). An item is handled
correctly when every applicable check is True. Each workflow also reports its guard hits and the share of items
that went straight through without a person (used by the time-saved model).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from opsflow.eval.runner import WorkflowRun
from opsflow.n8n_cli import node_items, node_time_ms
from opsflow.paths import SAMPLES

Row = dict[str, Any]


def labels(slug: str) -> dict[str, dict[str, Any]]:
    data = json.loads((SAMPLES / f"{slug}.json").read_text(encoding="utf-8"))
    return {i["id"]: i for i in data["items"]}


def supplier_key(name: Any) -> str:
    text = re.sub(r"\blimited\b", "ltd", str(name or "").lower())
    return re.sub(r"[^a-z0-9]", "", text)


def close(a: Any, b: Any, tol: float) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= tol


def row(
    sample_id: str, label: dict[str, Any], checks: dict[str, bool | None], expected: str, got: str, **extra: Any
) -> Row:
    applicable = [v for v in checks.values() if v is not None]
    return {
        "id": sample_id,
        "split": label["split"],
        "checks": checks,
        "correct": all(applicable),
        "expected": expected,
        "got": got,
        **extra,
    }


# ------------------------------------------------------------------------------------------------- workflows


def score_leads(run: WorkflowRun, lab: dict[str, dict[str, Any]]) -> tuple[list[Row], dict[str, Any]]:
    rows = []
    for got in node_items(run.execution, "Apply lead rules"):
        label = lab[got["sample_id"]]
        exp = label["expected"]
        checks = {
            "category": got["category"] == exp["category"],
            "priority": (got["priority"] == exp["priority"]) if exp["priority"] else None,
            "duplicate": got["duplicate"] == exp["duplicate"],
            "route": got["route"] == exp["route"],
        }
        rows.append(
            row(
                got["sample_id"],
                label,
                checks,
                f"{exp['category']} / {exp['priority']} / dup={exp['duplicate']}",
                f"{got['category']} / {got['priority']} / dup={got['duplicate']}",
                guard_hits=got["flags"],
                straight_through=not got["needs_review"],
                decided_by=got["decided_by"],
            )
        )
    s = run.state
    written = {
        "new CRM rows": len([r for r in s["crm_contacts"] if not r.get("seed")]),
        "notes on existing contacts": len(s["crm_notes"]),
        "follow-up drafts awaiting approval": len(s["crm_drafts"]),
        "forwarded to support": len(s["tickets"]),
        "discarded as spam (logged)": len(s["lead_log"]),
    }
    return rows, written


INVOICE_FIELDS = (
    "supplier_name",
    "gst_number",
    "invoice_number",
    "invoice_date",
    "due_date",
    "po_number",
    "currency",
    "subtotal",
    "gst",
    "total",
)
CORE_REASONS = {
    "gst_mismatch",
    "total_mismatch",
    "lines_mismatch",
    "unknown_supplier",
    "duplicate_invoice",
    "po_mismatch",
}


def score_invoices(run: WorkflowRun, lab: dict[str, dict[str, Any]]) -> tuple[list[Row], dict[str, Any]]:
    rows = []
    for got in node_items(run.execution, "Validate invoice"):
        label = lab[got["sample_id"]]
        exp = label["expected"]
        fields = {}
        for f in INVOICE_FIELDS:
            if f == "supplier_name":
                fields[f] = supplier_key(got.get(f)) == supplier_key(exp.get(f))
            elif f in ("subtotal", "gst", "total"):
                fields[f] = close(got.get(f), exp.get(f), 0.005)
            else:
                fields[f] = (got.get(f) or None) == (exp.get(f) or None)
        got_core = {r for r in got["reasons"] if r in CORE_REASONS}
        checks: dict[str, bool | None] = {f"field:{k}": v for k, v in fields.items()}
        checks["route"] = got["route"] == exp["route"]
        checks["reasons"] = got_core == set(exp["reasons"])
        rows.append(
            row(
                got["sample_id"],
                label,
                checks,
                f"{exp['route']} {sorted(exp['reasons'])}",
                f"{got['route']} {sorted(got['reasons'])}",
                guard_hits=got["reasons"],
                straight_through=got["route"] == "draft_bill",
                decided_by=got["extracted_by"],
                wrong_bill=got["route"] == "draft_bill" and exp["route"] != "draft_bill",
                layout=exp["layout"],
            )
        )
    s = run.state
    written = {
        "draft bills": len([b for b in s["bills"] if not b.get("seed")]),
        "exception queue": len(s["invoice_exceptions"]),
        "bills created that should have been exceptions": sum(r["wrong_bill"] for r in rows),
    }
    return rows, written


def score_support(run: WorkflowRun, lab: dict[str, dict[str, Any]]) -> tuple[list[Row], dict[str, Any]]:
    rows = []
    for got in node_items(run.execution, "Apply support rules"):
        label = lab[got["sample_id"]]
        exp = label["expected"]
        checks = {
            "category": got["category"] in exp["category"],
            "priority": got["priority"] == exp["priority"],
            "needs_person": got["needs_person"] == exp["needs_person"],
        }
        rows.append(
            row(
                got["sample_id"],
                label,
                checks,
                f"{'/'.join(exp['category'])} / {exp['priority']} / person={exp['needs_person']}",
                f"{got['category']} / {got['priority']} / person={got['needs_person']}",
                guard_hits=got["guard_hits"],
                straight_through=not got["needs_person"],
                decided_by=got["decided_by"],
                missed_person=exp["needs_person"] and not got["needs_person"],
                urgent_expected=exp["priority"] == "urgent",
                urgent_caught=exp["priority"] == "urgent" and got["priority"] == "urgent" and got["needs_person"],
            )
        )
    s = run.state
    written = {
        "helpdesk tickets": len(s["tickets"]),
        "urgent alerts posted": len([m for m in s["chat_messages"] if m["channel"] == "support-escalations"]),
        "emails sent to customers": 0,
    }
    return rows, written


KPI_TOLERANCE = {
    "revenue": 0.011,
    "aov": 0.011,
    "refund_rate_pct": 0.051,
    "wholesale_share_pct": 0.051,
    "revenue_week_before": 0.011,
    "change_vs_week_before_pct": 0.051,
    "top_product_revenue": 0.011,
    "orders": 0,
    "units": 0,
    "refunds": 0,
}


def half_up(v: float, places: int = 0) -> float:
    """Rounds half away from zero, the way people (and JavaScript's Math.round for positives) round money."""
    from decimal import ROUND_HALF_UP, Decimal

    return float(Decimal(str(v)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def allowed_numbers(k: dict[str, Any], report_date: str) -> set[float]:
    """An independent version of the workflow's number check, built from the expected KPIs."""
    from datetime import date, timedelta

    base = [
        k[f]
        for f in (
            "revenue",
            "orders",
            "aov",
            "units",
            "refunds",
            "refund_rate_pct",
            "wholesale_share_pct",
            "revenue_week_before",
            "top_product_revenue",
        )
    ]
    base += list(k["revenue_by_channel"].values()) + list(k["orders_by_channel"].values())
    if k["change_vs_week_before_pct"] is not None:
        base += [k["change_vs_week_before_pct"], abs(k["change_vs_week_before_pct"])]
    out: set[float] = set()
    for v in base:
        out |= {half_up(v, 2), half_up(v, 1), half_up(v)}
        if abs(v) >= 1000:
            out |= {half_up(v / 1000, 1), half_up(v / 1000)}
    d = date.fromisoformat(report_date)
    p = d - timedelta(days=7)
    out |= {float(x) for x in (d.year, d.month, d.day, p.year, p.month, p.day, 7, 20, 5)}
    out |= {abs(n) for n in numbers_in(k.get("top_product") or "")}
    return out


def numbers_in(text: str) -> list[float]:
    out = []
    for m in re.finditer(r"-?\d[\d,]*(?:\.\d+)?", text):
        raw = re.sub(r",(?=\d{3}\b)", "", m.group(0))
        if "," in raw:
            continue
        out.append(float(raw))
    return out


def score_kpi(run: WorkflowRun, lab: dict[str, dict[str, Any]]) -> tuple[list[Row], dict[str, Any]]:
    rows = []
    for got in node_items(run.execution, "Check every number"):
        label = lab[got["sample_id"]]
        exp = label["expected"]
        k = got["kpis"]
        numeric_ok = all(close(k[f], exp[f], tol) for f, tol in KPI_TOLERANCE.items())
        channels_ok = all(
            close(k["revenue_by_channel"][c], exp["revenue_by_channel"][c], 0.011) for c in exp["revenue_by_channel"]
        )
        allowed = allowed_numbers(exp, label["input"]["report_date"])
        posted = [n for line in got["lines"] for n in numbers_in(line)]
        ungrounded = [
            n for n in posted if not any(abs(abs(a) - abs(n)) < (0.0102 if n == int(n) else 0.051) for a in allowed)
        ]
        checks = {
            "kpis": numeric_ok and channels_ok and k["top_product"] == exp["top_product"],
            "alerts": k["alerts"] == exp["alerts"],
            "posted_numbers_grounded": not ungrounded,
            "five_lines": len(got["lines"]) == 5,
        }
        rows.append(
            row(
                got["sample_id"],
                label,
                checks,
                f"alerts={exp['alerts']}",
                f"alerts={k['alerts']} / {got['summary_source']}",
                guard_hits=[]
                if got["summary_source"].startswith("AI") or "AI off" in got["summary_source"]
                else ["ai_text_rejected"],
                straight_through=True,
                decided_by=got["summary_source"],
                ai_text_accepted=got["summary_source"].startswith("AI"),
                ungrounded_in_ai_text=got.get("ai_grounding", {}).get("ungrounded", []),
                lines=got["lines"],
            )
        )
    written = {"digests posted": len([m for m in run.state["chat_messages"] if m["channel"] == "daily-kpis"])}
    return rows, written


def score_purchase(run: WorkflowRun, lab: dict[str, dict[str, Any]]) -> tuple[list[Row], dict[str, Any]]:
    rows = []
    for got in node_items(run.execution, "Apply spending policy"):
        label = lab[got["sample_id"]]
        exp = label["expected"]
        checks = {"category": got["category"] in exp["category"], "route": got["route"] == exp["route"]}
        rows.append(
            row(
                got["sample_id"],
                label,
                checks,
                f"{exp['route']} / {'|'.join(exp['category'])}",
                f"{got['route']} / {got['category']}",
                guard_hits=[r for r in got["rules"] if not r.startswith("R0")],
                straight_through=got["route"] in ("auto_approve", "return_to_requester"),
                decided_by=got["categorised_by"],
                restricted_expected=exp["route"] == "finance_review",
                restricted_caught=exp["route"] == "finance_review" and got["route"] == "finance_review",
                wrongly_auto_approved=got["route"] == "auto_approve" and exp["route"] != "auto_approve",
            )
        )
    s = run.state
    written = {
        "audit entries": len(s["audit_log"]),
        "approval requests opened (the run pauses at the first approver form)": len(s["approvals"]),
        "requesters notified": len([m for m in s["chat_messages"] if m["channel"] == "purchasing"]),
    }
    return rows, written


def score_content(run: WorkflowRun, lab: dict[str, dict[str, Any]]) -> tuple[list[Row], dict[str, Any]]:
    by_blog: dict[str, list[dict[str, Any]]] = {}
    for got in node_items(run.execution, "Check posts"):
        by_blog.setdefault(got["sample_id"], []).append(got)
    rows = []
    for sid, posts in by_blog.items():
        label = lab[sid]
        exp = label["expected"]
        flagged = bool(posts[0]["source_claims"])
        mentions = all(all(term.lower() in p["text"].lower() for term in exp["must_mention"]) for p in posts)
        passed = [all(p["checks"].values()) for p in posts]
        leaked_ready = [
            p["channel"]
            for p, ok in zip(posts, passed, strict=True)
            if ok and any(ph.lower() in p["text"].lower() for ph in exp["risky_phrases"])
        ]
        checks = {
            "claims_flag": flagged == exp["risky_source"],
            "key_facts_in_every_post": mentions,
            "all_posts_pass_checks": all(passed),
            "no_risky_claim_in_ready_posts": not leaked_ready,
        }
        rows.append(
            row(
                sid,
                label,
                checks,
                f"claims={exp['risky_source']} mention={exp['must_mention']}",
                f"claims={posts[0]['source_claims']} passed={sum(passed)}/3",
                guard_hits=sorted({f.split(":")[0] for p in posts for f in p["flags"]}),
                straight_through=all(passed),
                decided_by=posts[0]["written_by"],
                posts_passed=sum(passed),
                posts=len(posts),
                post_flags={p["channel"]: p["flags"] for p in posts},
            )
        )
    s = run.state
    written = {
        "posts in the review queue": len(s["review_queue"]),
        "posts published": 0,
    }
    return rows, written


SCORERS: dict[str, Callable[[WorkflowRun, dict[str, dict[str, Any]]], tuple[list[Row], dict[str, Any]]]] = {
    "lead-intake": score_leads,
    "supplier-invoice": score_invoices,
    "support-triage": score_support,
    "kpi-digest": score_kpi,
    "purchase-approval": score_purchase,
    "content-repurpose": score_content,
}

AI_NODES = {
    "lead-intake": "Qualify lead (AI)",
    "supplier-invoice": "Extract fields (AI)",
    "support-triage": "Classify and draft (AI)",
    "kpi-digest": "Write summary (AI)",
    "purchase-approval": "Read the description (AI)",
    "content-repurpose": "Write social posts (AI)",
}


def summarise(rows: list[Row]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for split in ("dev", "heldout", "all"):
        subset = [r for r in rows if split == "all" or r["split"] == split]
        if not subset:
            continue
        names = sorted({k for r in subset for k in r["checks"]})
        checks = {}
        for name in names:
            vals = [r["checks"][name] for r in subset if r["checks"].get(name) is not None]
            checks[name] = {"right": sum(vals), "of": len(vals)}
        out[split] = {
            "items": len(subset),
            "correct": sum(r["correct"] for r in subset),
            "checks": checks,
            "guard_hit_items": sum(bool(r["guard_hits"]) for r in subset),
            "straight_through": sum(r["straight_through"] for r in subset),
        }
    return out


def model_calls(run: WorkflowRun) -> dict[str, Any]:
    calls = run.ai_calls
    ok = [c for c in calls if c.get("status") == 200]
    live = [c for c in ok if not c.get("cached")]
    latencies = sorted(
        float(c["latency_ms"]) if not c.get("cached") else float(c.get("live_latency_ms") or 0) for c in ok
    )
    latencies = [x for x in latencies if x > 0]

    def pct(p: float) -> float | None:
        if not latencies:
            return None
        return latencies[min(len(latencies) - 1, round(p * (len(latencies) - 1)))]

    return {
        "calls": len(calls),
        "ok": len(ok),
        "live": len(live),
        "cached": len(ok) - len(live),
        "failed": len(calls) - len(ok),
        "prompt_tokens": sum(int(c.get("prompt_tokens") or 0) for c in ok),
        "completion_tokens": sum(int(c.get("completion_tokens") or 0) for c in ok),
        "model_latency_ms_p50": pct(0.5),
        "model_latency_ms_p95": pct(0.95),
    }


def execution_ms(run: WorkflowRun) -> float:
    from datetime import datetime

    def ts(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    return (ts(run.execution["stoppedAt"]) - ts(run.execution["startedAt"])).total_seconds() * 1000


def score(run: WorkflowRun) -> dict[str, Any]:
    lab = labels(run.slug)
    rows, written = SCORERS[run.slug](run, lab)
    return {
        "workflow": run.slug,
        "mode": run.mode,
        "status": run.status,
        "error": run.error,
        "summary": summarise(rows),
        "written": written,
        "model": model_calls(run),
        "execution_ms": execution_ms(run),
        "ai_node_ms": node_time_ms(run.execution, AI_NODES[run.slug]),
        "cli_wall_s": round(run.wall_seconds, 1),
        "rows": rows,
    }
