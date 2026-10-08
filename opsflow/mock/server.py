"""Mock business systems for Acme Outdoor Gear, so every workflow runs offline.

    python -m opsflow mock [--port 8790] [--ai-mode live|replay|off]

One small HTTP server stands in for the CRM sheet, the accounting system, the helpdesk, the chat webhook, the
purchasing system, the content review queue and the sales database. It also serves the labelled sample data, the
invoice PDFs, an OpenAI-compatible model gateway (/ai/v1) and a read-only console at /.
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from opsflow.mock.console import render_console
from opsflow.mock.gateway import DEFAULT_UPSTREAM, Gateway
from opsflow.mock.store import Store
from opsflow.paths import AI_CACHE, INVOICES, RUNTIME

Json = dict[str, Any]
Response = tuple[int, Any]
Handler = Callable[["Api", re.Match[str], Json, dict[str, str]], Response]


class Api:
    """Routes requests to the store. Kept apart from the HTTP plumbing so it can be unit tested directly."""

    def __init__(self, store: Store, gateway: Gateway) -> None:
        self.store = store
        self.gateway = gateway
        self.routes: list[tuple[str, re.Pattern[str], Handler]] = []
        for method, pattern, handler in ROUTES:
            self.routes.append((method, re.compile(f"^{pattern}$"), handler))

    def handle(self, method: str, path: str, query: dict[str, str], body: Json, headers: dict[str, str]) -> Response:
        for m, pattern, handler in self.routes:
            if m != method:
                continue
            match = pattern.match(path)
            if match:
                ctx = {**query, **{f"h:{k.lower()}": v for k, v in headers.items()}}
                try:
                    return handler(self, match, body, ctx)
                except KeyError as err:
                    return 404, {"error": f"not found: {err}"}
                except ValueError as err:
                    return 400, {"error": str(err)}
        return 404, {"error": f"no route for {method} {path}"}


# ---------------------------------------------------------------------------------------------------- handlers


def health(api: Api, m: re.Match[str], body: Json, q: dict[str, str]) -> Response:
    return 200, {"ok": True, "ai_mode": api.gateway.mode}


def reset(api: Api, m: re.Match[str], body: Json, q: dict[str, str]) -> Response:
    api.store.reset()
    return 200, {"ok": True}


def state(api: Api, m: re.Match[str], body: Json, q: dict[str, str]) -> Response:
    return 200, api.store.snapshot()


def samples(api: Api, m: re.Match[str], body: Json, q: dict[str, str]) -> Response:
    split = q.get("split") or "all"
    limit = int(q.get("limit") or 0)
    items = api.store.samples(m["wf"], split)
    return 200, items[:limit] if limit else items


def crm_lookup(api: Api, m: re.Match[str], body: Json, q: dict[str, str]) -> Response:
    hits = api.store.crm_lookup(q.get("email"), q.get("phone"))
    return 200, {"matches": hits, "count": len(hits)}


def adder(collection: str, force: Json | None = None) -> Handler:
    def handler(api: Api, m: re.Match[str], body: Json, q: dict[str, str]) -> Response:
        if not isinstance(body, dict) or not body:
            raise ValueError("send a JSON object")
        return 201, api.store.add(collection, {**body, **(force or {})})

    return handler


def lister(collection: str, *filters: str) -> Handler:
    def handler(api: Api, m: re.Match[str], body: Json, q: dict[str, str]) -> Response:
        match = {f: q[f] for f in filters if q.get(f)}
        rows = api.store.find(collection, **match)
        return 200, {"rows": rows, "count": len(rows)}

    return handler


def add_note(api: Api, m: re.Match[str], body: Json, q: dict[str, str]) -> Response:
    """A note on an existing contact; finds the contact by email or phone when no id is given."""
    if not body.get("note"):
        raise ValueError("a note needs text")
    contact_id = body.get("contact_id")
    if not contact_id:
        hits = api.store.crm_lookup(body.get("email"), body.get("phone"))
        if not hits:
            return 404, {"error": "no contact with that email or phone"}
        contact_id = hits[0]["id"]
    return 201, api.store.add("crm_notes", {**body, "contact_id": contact_id})


def purchase_order(api: Api, m: re.Match[str], body: Json, q: dict[str, str]) -> Response:
    rows = api.store.find("purchase_orders", po_number=m["po"])
    return (200, rows[0]) if rows else (404, {"error": "unknown purchase order"})


def sales_query(api: Api, m: re.Match[str], body: Json, q: dict[str, str]) -> Response:
    rows = api.store.sales_query(str(body.get("sql", "")), body.get("params") or [])
    return 200, {"rows": rows, "count": len(rows)}


def policy(api: Api, m: re.Match[str], body: Json, q: dict[str, str]) -> Response:
    return 200, api.store.policy


def history(api: Api, m: re.Match[str], body: Json, q: dict[str, str]) -> Response:
    rows = api.store.find("purchase_history")
    if q.get("requester"):
        rows = [r for r in rows if r.get("requester", "").lower() == q["requester"].lower()]
    if q.get("supplier"):
        rows = [r for r in rows if r.get("supplier", "").lower() == q["supplier"].lower()]
    if q.get("since"):
        rows = [r for r in rows if r.get("date", "") >= q["since"]]
    return 200, {"rows": rows, "count": len(rows)}


def approval_decision(api: Api, m: re.Match[str], body: Json, q: dict[str, str]) -> Response:
    row = api.store.update("approvals", m["id"], {"status": body.get("decision", "unknown"), **body})
    return (200, row) if row else (404, {"error": "unknown approval"})


def chat(api: Api, m: re.Match[str], body: Json, q: dict[str, str]) -> Response:
    if not isinstance(body, dict) or not (body.get("text") or body.get("blocks")):
        raise ValueError("a chat message needs text or blocks")
    return 200, {"ok": True, "message": api.store.add("chat_messages", {"channel": m["channel"], **body})}


def ai_completion(api: Api, m: re.Match[str], body: Json, q: dict[str, str]) -> Response:
    result = api.gateway.complete(body, q.get("h:authorization"), tag=q.get("h:x-ops-workflow", ""))
    return result.status, result.body


ROUTES: list[tuple[str, str, Handler]] = [
    ("GET", r"/health", health),
    ("POST", r"/admin/reset", reset),
    ("GET", r"/admin/state", state),
    ("GET", r"/samples/(?P<wf>[a-z-]+)", samples),
    ("GET", r"/crm/contacts", crm_lookup),
    ("POST", r"/crm/contacts", adder("crm_contacts")),
    ("POST", r"/crm/notes", add_note),
    ("POST", r"/crm/drafts", adder("crm_drafts", {"status": "awaiting approval"})),
    ("POST", r"/leads/log", adder("lead_log")),
    ("GET", r"/accounting/suppliers", lister("suppliers")),
    ("GET", r"/accounting/purchase-orders/(?P<po>[A-Za-z0-9-]+)", purchase_order),
    ("GET", r"/accounting/bills", lister("bills", "supplier_id", "invoice_number")),
    ("POST", r"/accounting/bills", adder("bills", {"status": "DRAFT"})),
    ("POST", r"/accounting/exceptions", adder("invoice_exceptions", {"status": "open"})),
    ("POST", r"/helpdesk/tickets", adder("tickets")),
    ("POST", r"/chat/(?P<channel>[a-z0-9-]+)", chat),
    ("POST", r"/sales/query", sales_query),
    ("GET", r"/purchasing/policy", policy),
    ("GET", r"/purchasing/history", history),
    ("POST", r"/approvals", adder("approvals", {"status": "pending"})),
    ("POST", r"/approvals/(?P<id>[A-Z0-9]+)/decision", approval_decision),
    ("POST", r"/audit", adder("audit_log")),
    ("POST", r"/content/review-queue", adder("review_queue", {"status": "needs review"})),
    ("POST", r"/ops/errors", adder("ops_errors")),
    ("POST", r"/ai/v1/chat/completions", ai_completion),
]


# -------------------------------------------------------------------------------------------------------- HTTP


def make_handler(api: Api) -> type[BaseHTTPRequestHandler]:
    class RequestHandler(BaseHTTPRequestHandler):
        server_version = "AcmeMock/1.0"

        def log_message(self, format: str, *args: Any) -> None:
            pass

        def _send(self, status: int, payload: Any, content_type: str = "application/json") -> None:
            raw = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _dispatch(self, method: str) -> None:
            url = urlparse(self.path)
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            if method == "GET" and url.path in ("/", "/console"):
                html = render_console(api.store.snapshot(), query.get("tab", "overview"))
                self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
                return
            if method == "GET" and url.path.startswith("/files/invoices/"):
                self._file(INVOICES, url.path.removeprefix("/files/invoices/"))
                return
            body: Json = {}
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                try:
                    body = json.loads(self.rfile.read(length).decode("utf-8"))
                except ValueError:
                    self._send(400, {"error": "body is not JSON"})
                    return
            status, payload = api.handle(method, url.path, query, body, dict(self.headers.items()))
            self._send(status, payload)

        def _file(self, folder: Path, name: str) -> None:
            path = (folder / name).resolve()
            if folder.resolve() not in path.parents or not path.is_file():
                self._send(404, {"error": "no such file"})
                return
            ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self._send(200, path.read_bytes(), ctype)

        def do_GET(self) -> None:
            self._dispatch("GET")

        def do_POST(self) -> None:
            self._dispatch("POST")

    return RequestHandler


def build_api(ai_mode: str = "live", log_path: Path | None = None, cache_dir: Path = AI_CACHE) -> Api:
    gateway = Gateway(
        cache_dir=cache_dir,
        log_path=log_path or RUNTIME / "ai-calls.jsonl",
        mode=ai_mode,
        upstream=os.environ.get("AI_UPSTREAM_URL", DEFAULT_UPSTREAM),
        min_interval=float(os.environ.get("AI_MIN_INTERVAL", "2.5")),
    )
    return Api(Store(), gateway)


def serve(port: int = 8790, ai_mode: str = "live", log_path: Path | None = None) -> ThreadingHTTPServer:
    api = build_api(ai_mode, log_path)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(api))
    server.daemon_threads = True
    return server
