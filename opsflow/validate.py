"""Static checks on the workflow files. CI runs these; nothing here calls n8n or a model.

- the committed JSON matches what the builder generates;
- every connection points at a real node and every node is reachable from a trigger;
- each business workflow has a production trigger (webhook or schedule), a manual sample trigger, the shared
  error workflow, an AI on/off gate and an AI call that falls back instead of failing;
- no credentials, API keys or tokens are stored, and the model key is only read from $env;
- the guard rules each workflow depends on are present in its Code nodes;
- nothing sends, posts or pays on its own: outbound calls only go to drafts, queues, logs and chat.
"""

from __future__ import annotations

import json
import re
from collections import deque
from pathlib import Path
from typing import Any

from opsflow.build import all_workflows, render
from opsflow.paths import WORKFLOWS

TRIGGERS = {
    "n8n-nodes-base.webhook",
    "n8n-nodes-base.scheduleTrigger",
    "n8n-nodes-base.manualTrigger",
    "n8n-nodes-base.errorTrigger",
}
SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),
    re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"Bearer [A-Za-z0-9._\-]{20,}"),
    re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b"),  # Telegram bot token
]
GUARDS = {
    "lead-intake": ["decideLead(", "spamSignals(", "looksLikeInjection(", "DRAFT_PROMISE_RE"],
    "supplier-invoice": ["checkInvoice(", "gst_mismatch", "total_mismatch", "duplicate_invoice", "not_in_pdf"],
    "support-triage": ["decideTicket(", "SAFETY_RE", "LEGAL_RE", "draft_makes_promise"],
    "kpi-digest": ["kpisFromRows(", "groundingCheck(", "templateSummary("],
    "purchase-approval": ["decideRoute(", "R7 requester cannot approve", "G1 answered by"],
    "content-repurpose": ["checkPost(", "claimsIn(", "numbers_not_in_blog"],
}
# Outbound endpoints a workflow may write to: drafts, queues, logs, chat. Nothing that sends or pays.
ALLOWED_WRITES = re.compile(
    r"/(crm/(contacts|notes|drafts)|leads/log|helpdesk/tickets|accounting/(bills|exceptions)|chat/[a-z-]+|"
    r"sales/query|audit|approvals(/.+)?|content/review-queue|ops/errors|ai/v1/chat/completions)'?"
)


def check_workflow(slug: str, wf: dict[str, Any], error_id: str) -> list[str]:
    problems: list[str] = []
    nodes = {n["name"]: n for n in wf["nodes"]}
    if len(nodes) != len(wf["nodes"]):
        problems.append("duplicate node names")
    targets: dict[str, list[str]] = {}
    for src, outs in wf["connections"].items():
        if src not in nodes:
            problems.append(f"connection from unknown node {src!r}")
        for branch in outs.get("main", []):
            for edge in branch:
                if edge["node"] not in nodes:
                    problems.append(f"connection to unknown node {edge['node']!r}")
                targets.setdefault(src, []).append(edge["node"])

    real = {n: v for n, v in nodes.items() if v["type"] != "n8n-nodes-base.stickyNote"}
    starts = [n for n, v in real.items() if v["type"] in TRIGGERS]
    seen = set(starts)
    queue = deque(starts)
    while queue:
        for nxt in targets.get(queue.popleft(), []):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    for name in real:
        if name not in seen:
            problems.append(f"node {name!r} is not reachable from a trigger")

    for n in wf["nodes"]:
        if "credentials" in n:
            problems.append(f"node {n['name']!r} stores credentials")
    text = json.dumps(wf)
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            problems.append(f"possible secret matching {pattern.pattern}")
    for n in real.values():
        for header in n["parameters"].get("headerParameters", {}).get("parameters", []):
            if header["name"].lower() == "authorization" and "$env." not in header["value"]:
                problems.append(f"{n['name']!r}: Authorization must come from $env")

    if slug == "error-handler":
        if not any(v["type"] == "n8n-nodes-base.errorTrigger" for v in real.values()):
            problems.append("error workflow has no Error Trigger")
        return problems

    types = [v["type"] for v in real.values()]
    if not ({"n8n-nodes-base.webhook", "n8n-nodes-base.scheduleTrigger"} & set(types)):
        problems.append("no webhook or schedule trigger")
    if "Try with sample data" not in real or real["Try with sample data"]["type"] != "n8n-nodes-base.manualTrigger":
        problems.append("no 'Try with sample data' manual trigger")
    if wf["nodes"][0]["type"] != "n8n-nodes-base.manualTrigger":
        problems.append("the manual trigger must be the first node (n8n execute starts there)")
    if wf["settings"].get("errorWorkflow") != error_id:
        problems.append("not wired to the shared error workflow")
    if "AI switched on?" not in real:
        problems.append("no AI on/off gate")
    ai_nodes = [v for v in real.values() if "/chat/completions" in str(v["parameters"].get("url", ""))]
    if len(ai_nodes) != 1:
        problems.append(f"expected one AI call, found {len(ai_nodes)}")
    for v in ai_nodes:
        if v.get("onError") != "continueRegularOutput" or not v.get("retryOnFail"):
            problems.append(f"{v['name']!r} must retry and fall back to the rules instead of failing")

    code = "\n".join(v["parameters"].get("jsCode", "") for v in real.values())
    for marker in GUARDS[slug]:
        if marker not in code:
            problems.append(f"guard missing: {marker}")

    for v in real.values():
        if v["type"] != "n8n-nodes-base.httpRequest" or v["parameters"].get("method", "GET") == "GET":
            continue
        url = str(v["parameters"].get("url", ""))
        if "/chat/completions" in url:
            continue
        if not ALLOWED_WRITES.search(url):
            problems.append(f"{v['name']!r} writes to an endpoint outside the allowed list: {url}")
    if slug == "purchase-approval" and not any(v["type"] == "n8n-nodes-base.wait" for v in real.values()):
        problems.append("approvals need a Wait node for the approver's decision")
    return problems


def validate(folder: Path = WORKFLOWS) -> dict[str, list[str]]:
    expected = all_workflows()
    error_id = expected["error-handler"]["id"]
    report: dict[str, list[str]] = {}
    for slug, wf in expected.items():
        path = folder / f"{slug}.json"
        problems = []
        if not path.exists():
            problems.append("file missing: run python -m opsflow build")
        else:
            committed = path.read_text(encoding="utf-8").replace("\r\n", "\n")
            if committed != render(wf):
                problems.append("out of date: run python -m opsflow build")
            problems += check_workflow(slug, json.loads(committed), error_id)
        report[slug] = problems
    extra = {p.stem for p in folder.glob("*.json")} - set(expected)
    for slug in sorted(extra):
        report[slug] = ["unexpected workflow file"]
    return report


def main() -> int:
    report = validate()
    bad = 0
    for slug, problems in report.items():
        status = "ok" if not problems else f"{len(problems)} problem(s)"
        print(f"{slug:20} {status}")
        for p in problems:
            print(f"    - {p}")
        bad += len(problems)
    return 1 if bad else 0
