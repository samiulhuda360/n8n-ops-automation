"""A read-only HTML console over the mock systems: what each workflow wrote, as tables."""

from __future__ import annotations

import html
import json
from typing import Any

Record = dict[str, Any]

# tab -> (title, [(collection, heading, [columns])])
TABS: dict[str, tuple[str, list[tuple[str, str, list[str]]]]] = {
    "leads": (
        "Leads",
        [
            ("crm_contacts", "CRM sheet", ["id", "name", "company", "email", "category", "priority", "source", "owner"]),
            ("crm_drafts", "Follow-up drafts awaiting approval", ["id", "contact_id", "to", "subject", "status", "flags"]),
            ("crm_notes", "Notes added to existing contacts", ["id", "contact_id", "note"]),
            ("lead_log", "Discarded or forwarded", ["id", "sample_id", "email", "route", "reason"]),
        ],
    ),
    "invoices": (
        "Supplier invoices",
        [
            (
                "bills",
                "Draft bills",
                ["id", "supplier_name", "invoice_number", "invoice_date", "due_date", "currency", "subtotal", "gst",
                 "total", "status"],
            ),
            ("invoice_exceptions", "Exception queue", ["id", "supplier_name", "invoice_number", "total", "reasons",
                                                       "status"]),
        ],
    ),
    "support": (
        "Support",
        [("tickets", "Helpdesk tickets", ["id", "subject", "category", "priority", "queue", "status", "guard_hits"])],
    ),
    "approvals": (
        "Purchasing",
        [
            ("approvals", "Approval requests", ["id", "request_id", "requester", "amount_nzd", "route", "approver",
                                                "status"]),
            ("audit_log", "Audit log", ["id", "request_id", "event", "route", "rules", "actor", "created_at"]),
        ],
    ),
    "content": (
        "Content",
        [("review_queue", "Review queue (nothing is posted automatically)", ["id", "post_id", "channel", "text",
                                                                              "checks", "status"])],
    ),
    "chat": (
        "Chat",
        [("chat_messages", "Messages sent to the chat webhook", ["id", "channel", "text", "created_at"])],
    ),
    "errors": ("Errors", [("ops_errors", "Workflow errors", ["id", "workflow", "node", "message", "created_at"])]),
}

SEEDED = {"crm_contacts", "bills", "purchase_history", "suppliers", "purchase_orders"}

CSS = """
:root { --bg:#f5f3ee; --panel:#ffffff; --ink:#1d2a26; --muted:#5d6b66; --line:#dfe3dd; --accent:#2f6f68;
        --accent-soft:#e6f2ef; --warn:#a4561f; --warn-soft:#fbeee2; }
* { box-sizing:border-box }
body { margin:0; background:var(--bg); color:var(--ink); font:14px/1.45 "Segoe UI", system-ui, sans-serif; }
header { background:#1f3b36; color:#eef5f2; padding:14px 24px; display:flex; align-items:baseline; gap:16px; }
header h1 { font-size:18px; margin:0; font-weight:600 }
header span { opacity:.75; font-size:13px }
nav { display:flex; gap:4px; padding:10px 24px 0; flex-wrap:wrap; border-bottom:1px solid var(--line); background:#fbfaf7 }
nav a { padding:8px 14px; text-decoration:none; color:var(--muted); border-radius:6px 6px 0 0; }
nav a.on { background:var(--panel); color:var(--accent); font-weight:600; border:1px solid var(--line);
           border-bottom-color:var(--panel); margin-bottom:-1px }
main { padding:18px 24px 40px; }
section { background:var(--panel); border:1px solid var(--line); border-radius:8px; margin-bottom:18px; overflow:auto }
section h2 { font-size:15px; margin:0; padding:12px 16px; border-bottom:1px solid var(--line); display:flex;
             justify-content:space-between }
section h2 small { color:var(--muted); font-weight:400 }
table { border-collapse:collapse; width:100%; font-size:13px }
th, td { text-align:left; padding:7px 12px; border-bottom:1px solid #eef0ec; vertical-align:top; max-width:420px }
th { background:#f7f8f5; color:var(--muted); font-weight:600; position:sticky; top:0 }
td.long { white-space:pre-wrap }
.tag { display:inline-block; padding:1px 8px; border-radius:10px; background:var(--accent-soft); color:var(--accent);
       font-size:12px; margin:1px 2px 1px 0 }
.tag.warn { background:var(--warn-soft); color:var(--warn) }
.cards { display:grid; grid-template-columns:repeat(auto-fill, minmax(190px,1fr)); gap:12px; margin-bottom:18px }
.card { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:12px 14px }
.card b { font-size:24px; color:var(--accent); display:block }
.card span { color:var(--muted); font-size:12.5px }
.empty { color:var(--muted); padding:14px 16px }
"""

WARN_WORDS = ("exception", "urgent", "person", "escalat", "reject", "spam", "fail", "mismatch", "duplicate",
              "director", "finance", "needs edit", "unknown", "open", "pending")


def _cell(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, list):
        if not value:
            return ""
        return "".join(_tag(str(v)) for v in value)
    if isinstance(value, dict):
        return "".join(_tag(f"{k}: {'ok' if v is True else 'fail' if v is False else v}") for k, v in value.items())
    if isinstance(value, float):
        return f"{value:,.2f}"
    text = str(value)
    if len(text) > 400:
        text = text[:397] + "..."
    return html.escape(text)


def _tag(text: str) -> str:
    warn = any(w in text.lower() for w in WARN_WORDS)
    return f'<span class="tag{" warn" if warn else ""}">{html.escape(text)}</span>'


def _table(rows: list[Record], columns: list[str]) -> str:
    if not rows:
        return '<div class="empty">Nothing yet.</div>'
    head = "".join(f"<th>{html.escape(c.replace('_', ' '))}</th>" for c in columns)
    body = []
    for row in rows:
        cells = []
        for c in columns:
            v = row.get(c)
            cls = ' class="long"' if isinstance(v, str) and len(v) > 80 else ""
            if c in ("status", "route", "priority", "category", "queue") and isinstance(v, str) and v:
                cells.append(f"<td>{_tag(v)}</td>")
            else:
                cells.append(f"<td{cls}>{_cell(v)}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _new_rows(state: dict[str, list[Record]], collection: str) -> list[Record]:
    rows = state.get(collection, [])
    if collection in SEEDED:
        return [r for r in rows if not r.get("seed")]
    return rows


def render_console(state: dict[str, list[Record]], tab: str = "overview") -> str:
    nav = [("overview", "Overview")] + [(k, v[0]) for k, v in TABS.items()]
    links = "".join(f'<a href="/?tab={k}" class="{"on" if k == tab else ""}">{html.escape(t)}</a>' for k, t in nav)
    if tab in TABS:
        parts = []
        for collection, heading, cols in TABS[tab][1]:
            rows = _new_rows(state, collection)
            parts.append(
                f'<section><h2>{html.escape(heading)}<small>{len(rows)} rows</small></h2>{_table(rows, cols)}</section>'
            )
        content = "".join(parts)
    else:
        counts = [
            ("New CRM rows", len(_new_rows(state, "crm_contacts"))),
            ("Follow-up drafts", len(state.get("crm_drafts", []))),
            ("Draft bills", len(_new_rows(state, "bills"))),
            ("Invoice exceptions", len(state.get("invoice_exceptions", []))),
            ("Support tickets", len(state.get("tickets", []))),
            ("Approval requests", len(state.get("approvals", []))),
            ("Audit entries", len(state.get("audit_log", []))),
            ("Posts in review", len(state.get("review_queue", []))),
            ("Chat messages", len(state.get("chat_messages", []))),
            ("Workflow errors", len(state.get("ops_errors", []))),
        ]
        cards = "".join(f'<div class="card"><b>{n}</b><span>{html.escape(t)}</span></div>' for t, n in counts)
        latest = state.get("chat_messages", [])[-3:]
        msgs = "".join(
            f'<section><h2>#{html.escape(m.get("channel", ""))}<small>{html.escape(m.get("created_at", ""))}</small>'
            f'</h2><div class="empty" style="white-space:pre-wrap;color:var(--ink)">{html.escape(m.get("text", ""))}'
            "</div></section>"
            for m in reversed(latest)
        )
        content = f'<div class="cards">{cards}</div>{msgs}'
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Acme Ops console</title>
<style>{CSS}</style></head><body>
<header><h1>Acme Outdoor Gear · Ops console</h1><span>mock CRM, accounting, helpdesk, purchasing and chat</span></header>
<nav>{links}</nav><main>{content}</main>
<script type="application/json" id="state-counts">{json.dumps({k: len(v) for k, v in state.items()})}</script>
</body></html>"""
