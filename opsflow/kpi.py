"""Reference KPI calculation in plain Python.

The KPI digest workflow computes the same numbers with SQL and JavaScript inside n8n. This independent version
produces the expected values the evaluation compares against, so a mistake in either one shows up as a mismatch.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

CHANNELS = ("online", "store", "wholesale")
REVENUE_DROP_PCT = -20.0
REFUND_SPIKE_PCT = 5.0


def _paid_total(rows: Iterable[Mapping[str, Any]]) -> float:
    return sum(float(r["total_nzd"]) for r in rows if r["status"] == "paid")


def compute_kpis(day: list[Mapping[str, Any]], week_before: list[Mapping[str, Any]]) -> dict[str, Any]:
    paid = [r for r in day if r["status"] == "paid"]
    revenue = round(_paid_total(day), 2)
    orders = len(paid)
    refunds = sum(1 for r in day if r["status"] == "refunded")
    by_channel = {c: round(sum(float(r["total_nzd"]) for r in paid if r["channel"] == c), 2) for c in CHANNELS}
    orders_by_channel = {c: sum(1 for r in paid if r["channel"] == c) for c in CHANNELS}
    product_revenue: dict[str, float] = defaultdict(float)
    for r in paid:
        product_revenue[r["product"]] += float(r["total_nzd"])
    top = sorted(product_revenue.items(), key=lambda kv: (-round(kv[1], 2), kv[0]))[0] if product_revenue else None
    prev_revenue = round(_paid_total(week_before), 2)
    change = round(100 * (revenue - prev_revenue) / prev_revenue, 1) if prev_revenue else None
    refund_rate = round(100 * refunds / len(day), 1) if day else 0.0

    alerts = []
    if change is not None and change <= REVENUE_DROP_PCT:
        alerts.append("revenue_drop")
    if refund_rate > REFUND_SPIKE_PCT:
        alerts.append("refund_spike")
    alerts += [f"{c}_zero" for c in ("online", "store") if orders_by_channel[c] == 0]

    return {
        "revenue": revenue,
        "orders": orders,
        "aov": round(revenue / orders, 2) if orders else 0.0,
        "units": sum(int(r["qty"]) for r in paid),
        "refunds": refunds,
        "refund_rate_pct": refund_rate,
        "revenue_by_channel": by_channel,
        "orders_by_channel": orders_by_channel,
        "wholesale_share_pct": round(100 * by_channel["wholesale"] / revenue, 1) if revenue else 0.0,
        "revenue_week_before": prev_revenue,
        "change_vs_week_before_pct": change,
        "top_product": top[0] if top else None,
        "top_product_revenue": round(top[1], 2) if top else 0.0,
        "alerts": alerts,
    }
