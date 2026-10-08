"""Runs the evaluation, then writes results/summary.json, results/items.csv and results/RESULTS.md."""

from __future__ import annotations

import csv
import json
from datetime import date
from typing import Any

from opsflow.paths import DATA, RESULTS, WORKFLOW_SLUGS

TITLES = {
    "lead-intake": "Lead intake and enrichment",
    "supplier-invoice": "Supplier invoice to draft bill",
    "support-triage": "Customer support triage",
    "kpi-digest": "Daily KPI digest",
    "purchase-approval": "Purchase approval routing",
    "content-repurpose": "Blog post to social drafts",
}
UNITS = {"content-repurpose": "blog posts (3 drafts each)", "kpi-digest": "report days"}
# Assumed list price for gemini-flash-lite, USD per million tokens (input, output).
PRICE_PER_M = (0.10, 0.40)


def evaluate(modes: tuple[str, ...], split: str, gateway: str, only: tuple[str, ...] | None, ai_key: str) -> int:
    from opsflow.eval.runner import run_all
    from opsflow.eval.scoring import score

    if "ai" in modes and gateway == "live" and not ai_key:
        print("No AI_API_KEY set: the 'ai' mode will fall back to rules unless the replay cache has the answers.")
    runs = run_all(modes=modes, slugs=only, split=split, gateway_mode=gateway, ai_key=ai_key)
    results = [score(r) for r in runs]
    RESULTS.mkdir(parents=True, exist_ok=True)
    previous = load_summary() if only else {"runs": []}
    keep = [
        r
        for r in previous.get("runs", [])
        if (r["workflow"], r["mode"]) not in {(x["workflow"], x["mode"]) for x in results}
    ]
    summary = {
        "date": date.today().isoformat(),
        "split": split,
        "gateway": gateway,
        "model": "gemini-flash-lite-latest",
        "runs": keep + results,
    }
    (RESULTS / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    rebuild_markdown()
    failed = [r for r in results if r["status"] not in ("success", "waiting")]
    return 1 if failed else 0


def load_summary() -> dict[str, Any]:
    path = RESULTS / "summary.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"runs": []}


def time_model() -> list[dict[str, Any]]:
    with (DATA / "time_model.csv").open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def pct(a: int, b: int) -> str:
    return f"{a}/{b} ({100 * a / b:.0f}%)" if b else "n/a"


def hours_saved(run: dict[str, Any], assumption: dict[str, Any]) -> dict[str, float]:
    s = run["summary"]["all"]
    n = s["items"]
    straight = s["straight_through"] / n
    error = 1 - s["correct"] / n
    manual = float(assumption["manual_minutes"])
    after = (
        straight * float(assumption["review_minutes"])
        + (1 - straight) * float(assumption["flagged_minutes"])
        + error * float(assumption["rework_minutes"])
    )
    volume = float(assumption["monthly_volume"])
    return {
        "straight": straight,
        "error": error,
        "manual": manual,
        "after": after,
        "volume": volume,
        "hours": volume * (manual - after) / 60,
    }


def rebuild_markdown() -> None:
    summary = load_summary()
    runs = {(r["workflow"], r["mode"]): r for r in summary["runs"]}
    write_items_csv(summary["runs"])
    lines = [
        "# Evaluation results",
        "",
        f"Run on {summary['date']} with `python -m opsflow eval` (model `{summary['model']}`, gateway "
        f"`{summary['gateway']}`). Every workflow ran for real inside n8n from its **Try with sample data** "
        "trigger, against the mock systems, on every labelled item. Two modes:",
        "",
        "- **rules**: `AI_MODE=off`. The keyword/regex/template baseline that each workflow falls back to.",
        "- **ai**: the shipped workflow: the model suggests, the guard rules decide.",
        "",
        "Items in the **heldout** split were written with the rest but never looked at while prompts and rules "
        "were tuned. An item counts as handled correctly only when every check on it is right.",
        "",
        "## Summary",
        "",
        "| Workflow | Items | Rules only | AI + rules | AI, dev | AI, held out | Guard hits (AI) | Straight through (AI) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for slug in WORKFLOW_SLUGS:
        ai, rules = runs.get((slug, "ai")), runs.get((slug, "rules"))
        if not ai and not rules:
            continue
        ref = ai or rules
        assert ref is not None
        a = ref["summary"]["all"]

        def cell(run: dict[str, Any] | None, split: str = "all") -> str:
            if not run or split not in run["summary"]:
                return "-"
            s = run["summary"][split]
            return pct(s["correct"], s["items"])

        lines.append(
            f"| {TITLES[slug]} | {a['items']} {UNITS.get(slug, '')} | {cell(rules)} | {cell(ai)} | {cell(ai, 'dev')} | "
            f"{cell(ai, 'heldout')} | {ai['summary']['all']['guard_hit_items'] if ai else '-'} | "
            f"{pct(ai['summary']['all']['straight_through'], ai['summary']['all']['items']) if ai else '-'} |"
        )

    lines += ["", "## Checks per workflow", ""]
    for slug in WORKFLOW_SLUGS:
        ai, rules = runs.get((slug, "ai")), runs.get((slug, "rules"))
        if not ai and not rules:
            continue
        lines += [
            f"### {TITLES[slug]}",
            "",
            "| Check | Rules only | AI + rules | AI, held out |",
            "|---|---|---|---|",
        ]
        ref = ai or rules
        assert ref is not None
        for name in ref["summary"]["all"]["checks"]:

            def c(run: dict[str, Any] | None, split: str = "all", name: str = name) -> str:
                if not run or split not in run["summary"] or name not in run["summary"][split]["checks"]:
                    return "-"
                v = run["summary"][split]["checks"][name]
                return pct(v["right"], v["of"])

            lines.append(f"| {name.replace('_', ' ')} | {c(rules)} | {c(ai)} | {c(ai, 'heldout')} |")
        lines.append("")
        written = (ai or rules or {}).get("written", {})
        if written:
            lines.append(
                "What the AI run wrote to the mock systems: "
                + "; ".join(f"{k}: {v}" for k, v in written.items())
                + "."
            )
            lines.append("")
        if ai:
            misses = [r for r in ai["rows"] if not r["correct"]]
            if misses:
                lines += [
                    "Items not handled correctly (AI + rules):",
                    "",
                    "| Item | Split | Failed checks | Expected | Got |",
                    "|---|---|---|---|---|",
                ]
                for r in misses:
                    failed = ", ".join(k for k, v in r["checks"].items() if v is False)
                    lines.append(
                        f"| {r['id']} | {r['split']} | {failed} | {r['expected']} | {r['got'].replace('|', '/')} |"
                    )
                lines.append("")
            else:
                lines += ["Every item was handled correctly.", ""]

    lines += [
        "## Model calls, latency and cost",
        "",
        "Calls go through the caching gateway in the mock services: `live` calls reached the model, `cached` "
        "ones were answered from `eval-cache/ai/` (the same request always gets the same stored answer). Model "
        "latency is measured on live calls (cached answers keep the latency recorded when they were made). "
        f"Cost assumes US${PRICE_PER_M[0]:.2f} per million input tokens and US${PRICE_PER_M[1]:.2f} per million "
        "output tokens.",
        "",
        "| Workflow | Model calls | Live | Cached | Failed | Tokens in / out | Model p50 / p95 | n8n run time | Cost per item |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    totals = {"calls": 0, "live": 0, "cached": 0, "failed": 0, "in": 0, "out": 0}
    for slug in WORKFLOW_SLUGS:
        ai = runs.get((slug, "ai"))
        if not ai:
            continue
        m = ai["model"]
        n = ai["summary"]["all"]["items"]
        cost = (m["prompt_tokens"] * PRICE_PER_M[0] + m["completion_tokens"] * PRICE_PER_M[1]) / 1e6
        p50 = f"{m['model_latency_ms_p50'] / 1000:.1f}s" if m["model_latency_ms_p50"] else "-"
        p95 = f"{m['model_latency_ms_p95'] / 1000:.1f}s" if m["model_latency_ms_p95"] else "-"
        lines.append(
            f"| {TITLES[slug]} | {m['calls']} | {m['live']} | {m['cached']} | {m['failed']} | "
            f"{m['prompt_tokens']:,} / {m['completion_tokens']:,} | {p50} / {p95} | {ai['execution_ms'] / 1000:.1f}s "
            f"for {n} | US${cost / n:.5f} |"
        )
        totals["calls"] += m["calls"]
        totals["live"] += m["live"]
        totals["cached"] += m["cached"]
        totals["failed"] += m["failed"]
        totals["in"] += m["prompt_tokens"]
        totals["out"] += m["completion_tokens"]
    lines += [
        "",
        f"Total for the AI run: {totals['calls']} model calls ({totals['live']} live, {totals['cached']} cached, "
        f"{totals['failed']} failed), {totals['in']:,} input and {totals['out']:,} output tokens.",
        "",
        "## Time saved",
        "",
        "Assumptions are in `data/time_model.csv`: minutes for doing each item by hand, minutes for a person to "
        "review an item that went straight through, minutes for a person to handle a flagged item (with the AI's "
        "work already in front of them), rework minutes for an item handled wrongly, and monthly volume. The "
        "straight-through and error rates are the measured ones from the AI run above.",
        "",
        "`minutes after = straight × review + (1 − straight) × flagged + error × rework`",
        "",
        "| Workflow | Manual min/item | Straight through | Error rate | Min/item after | Volume/month | Hours saved/month |",
        "|---|---|---|---|---|---|---|",
    ]
    total_hours = 0.0
    for assumption in time_model():
        ai = runs.get((assumption["workflow"], "ai"))
        if not ai:
            continue
        h = hours_saved(ai, assumption)
        total_hours += h["hours"]
        lines.append(
            f"| {TITLES[assumption['workflow']]} | {h['manual']:g} | {h['straight'] * 100:.0f}% | {h['error'] * 100:.0f}% | "
            f"{h['after']:.1f} | {h['volume']:g} | {h['hours']:.1f} |"
        )
    lines += [f"| **Total** | | | | | | **{total_hours:.0f}** |", ""]
    (RESULTS / "RESULTS.md").write_text("\n".join(lines), encoding="utf-8")


def write_items_csv(runs: list[dict[str, Any]]) -> None:
    with (RESULTS / "items.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "mode",
                "workflow",
                "item",
                "split",
                "correct",
                "failed_checks",
                "expected",
                "got",
                "guard_hits",
                "decided_by",
            ]
        )
        for run in runs:
            for r in run["rows"]:
                w.writerow(
                    [
                        run["mode"],
                        run["workflow"],
                        r["id"],
                        r["split"],
                        r["correct"],
                        ";".join(k for k, v in r["checks"].items() if v is False),
                        r["expected"],
                        r["got"],
                        ";".join(map(str, r["guard_hits"])),
                        r.get("decided_by", ""),
                    ]
                )
