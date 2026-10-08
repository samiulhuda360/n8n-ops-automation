from __future__ import annotations

import csv
import json
from collections import defaultdict

from opsflow.eval.report import hours_saved
from opsflow.eval.scoring import allowed_numbers, numbers_in, summarise, supplier_key
from opsflow.kpi import compute_kpis
from opsflow.paths import DATA, INVOICES, SAMPLES, SEED, WORKFLOW_SLUGS


def load(slug: str) -> list[dict]:
    return json.loads((SAMPLES / f"{slug}.json").read_text(encoding="utf-8"))["items"]


def test_every_workflow_has_labelled_dev_and_heldout_items() -> None:
    for slug in WORKFLOW_SLUGS:
        items = load(slug)
        assert 15 <= len(items) <= 30
        splits = {i["split"] for i in items}
        assert splits == {"dev", "heldout"}
        assert len({i["id"] for i in items}) == len(items)
        assert all("expected" in i and "input" in i for i in items)


def test_people_use_example_addresses() -> None:
    for slug in ("lead-intake", "support-triage", "purchase-approval"):
        for item in load(slug):
            for key in ("email", "from", "requester_email"):
                if item["input"].get(key):
                    assert item["input"][key].strip().lower().endswith("@example.com")


def test_invoice_pdfs_exist_for_every_sample() -> None:
    for item in load("supplier-invoice"):
        assert (INVOICES / item["input"]["attachment_name"]).exists()


def test_kpi_labels_match_the_reference_calculation() -> None:
    by_date: dict[str, list[dict]] = defaultdict(list)
    with (SEED / "sales_orders.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            by_date[r["order_date"]].append(r)
    item = load("kpi-digest")[0]
    from datetime import date, timedelta

    d = date.fromisoformat(item["input"]["report_date"])
    k = compute_kpis(by_date[d.isoformat()], by_date[(d - timedelta(days=7)).isoformat()])
    assert k == item["expected"]


def test_planted_events_raise_alerts() -> None:
    alerts = {i["input"]["report_date"]: i["expected"]["alerts"] for i in load("kpi-digest")}
    assert "revenue_drop" in alerts["2026-09-12"]
    assert "refund_spike" in alerts["2026-09-15"]
    assert "store_zero" in alerts["2026-09-29"]


def test_grounding_helpers() -> None:
    assert numbers_in("Revenue $9,663.90, up 10.3%") == [9663.9, 10.3]
    k = load("kpi-digest")[0]["expected"]
    allowed = allowed_numbers(k, "2026-09-10")
    assert round(k["revenue"], 2) in allowed
    assert float(round(k["revenue"])) in allowed
    assert supplier_key("Southern Alps Textiles Limited") == supplier_key("SOUTHERN ALPS TEXTILES LTD")


def test_summary_counts_splits() -> None:
    rows = [
        {
            "split": "dev",
            "checks": {"a": True, "b": None},
            "correct": True,
            "guard_hits": [],
            "straight_through": True,
        },
        {
            "split": "heldout",
            "checks": {"a": False, "b": True},
            "correct": False,
            "guard_hits": ["x"],
            "straight_through": False,
        },
    ]
    s = summarise(rows)
    assert s["all"]["correct"] == 1
    assert s["all"]["checks"]["a"] == {"right": 1, "of": 2}
    assert s["all"]["checks"]["b"] == {"right": 1, "of": 1}
    assert s["heldout"]["guard_hit_items"] == 1


def test_time_model_formula() -> None:
    run = {"summary": {"all": {"items": 10, "straight_through": 8, "correct": 9}}}
    assumption = {
        "manual_minutes": "10",
        "review_minutes": "1",
        "flagged_minutes": "5",
        "rework_minutes": "10",
        "monthly_volume": "60",
    }
    h = hours_saved(run, assumption)
    # after = 0.8*1 + 0.2*5 + 0.1*10 = 2.8 min; saved = 60 * 7.2 / 60
    assert abs(h["after"] - 2.8) < 1e-9
    assert abs(h["hours"] - 7.2) < 1e-9


def test_time_model_covers_every_workflow() -> None:
    with (DATA / "time_model.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert {r["workflow"] for r in rows} == set(WORKFLOW_SLUGS)
    for r in rows:
        assert float(r["manual_minutes"]) > float(r["review_minutes"])
