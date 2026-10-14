from __future__ import annotations

import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest

from opsflow.mock.console import render_console
from opsflow.mock.gateway import Gateway
from opsflow.mock.server import Api, build_api, make_handler
from opsflow.mock.store import Store, norm_phone


@pytest.fixture()
def api(tmp_path: Path) -> Api:
    return build_api("off", log_path=tmp_path / "calls.jsonl", cache_dir=tmp_path / "cache")


def call(api: Api, method: str, path: str, body: Any = None, **query: str) -> tuple[int, Any]:
    return api.handle(method, path, query, body or {}, {})


def test_samples_hide_labels(api: Api) -> None:
    status, items = call(api, "GET", "/samples/support-triage", split="heldout")
    assert status == 200
    assert len(items) == 8
    assert all("expected" not in i for i in items)
    assert all(i["sample_id"].startswith("S") for i in items)


def test_crm_lookup_matches_email_case_and_phone_format(api: Api) -> None:
    _, by_email = call(api, "GET", "/crm/contacts", email=" KATE.Whitfield@Example.com")
    _, by_phone = call(api, "GET", "/crm/contacts", phone="+64 22 555 0102")
    assert by_email["count"] == 1
    assert by_phone["matches"][0]["name"] == "Tomasi Fifita"
    assert norm_phone("+64 21 555 0101") == "0215550101"


def test_bills_are_always_drafts_and_reset_restores_seed(api: Api) -> None:
    status, bill = call(api, "POST", "/accounting/bills", {"invoice_number": "X1", "status": "AUTHORISED"})
    assert status == 201
    assert bill["status"] == "DRAFT"
    call(api, "POST", "/admin/reset")
    _, rows = call(api, "GET", "/accounting/bills", invoice_number="X1")
    assert rows["count"] == 0


def test_notes_resolve_contact_by_email(api: Api) -> None:
    status, note = call(api, "POST", "/crm/notes", {"email": "mere.tane@example.com", "note": "hi"})
    assert status == 201
    assert note["contact_id"] == "C0005"
    status, _ = call(api, "POST", "/crm/notes", {"email": "nobody@example.com", "note": "hi"})
    assert status == 404


def test_sales_query_is_read_only(api: Api) -> None:
    status, out = call(
        api,
        "POST",
        "/sales/query",
        {"sql": "SELECT COUNT(*) AS n FROM orders WHERE order_date = ?", "params": ["2026-09-10"]},
    )
    assert status == 200
    assert out["rows"][0]["n"] > 0
    for bad in ("DELETE FROM orders", "SELECT 1; DROP TABLE orders", "UPDATE orders SET qty = 0"):
        status, _ = call(api, "POST", "/sales/query", {"sql": bad})
        assert status == 400


def test_chat_needs_text(api: Api) -> None:
    assert call(api, "POST", "/chat/sales", {"text": "hello"})[0] == 200
    assert call(api, "POST", "/chat/sales", {"foo": 1})[0] == 400


def test_unknown_route(api: Api) -> None:
    assert call(api, "GET", "/nope")[0] == 404


def test_console_renders_every_tab() -> None:
    state = Store().snapshot()
    for tab in ("overview", "leads", "invoices", "support", "approvals", "content", "chat", "errors"):
        html = render_console(state, tab)
        assert "Acme Outdoor Gear" in html
        assert "<script src" not in html


# ------------------------------------------------------------------------------------------------- gateway


class FakeProvider(BaseHTTPRequestHandler):
    calls: ClassVar[list[dict[str, Any]]] = []
    fail_first = 0

    def log_message(self, *args: Any) -> None:
        pass

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeProvider.calls.append({"auth": self.headers.get("Authorization"), "body": body})
        if FakeProvider.fail_first > 0:
            FakeProvider.fail_first -= 1
            self.send_response(429)
            self.end_headers()
            self.wfile.write(b'{"error": {"message": "slow down"}}')
            return
        out = {
            "choices": [{"message": {"content": '{"ok": true}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 3},
        }
        raw = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


@pytest.fixture()
def provider() -> Any:
    FakeProvider.calls = []
    FakeProvider.fail_first = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeProvider)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


REQUEST = {"model": "m", "messages": [{"role": "user", "content": "hi"}], "temperature": 0}


def test_gateway_caches_and_forwards_the_key(tmp_path: Path, provider: str) -> None:
    gw = Gateway(cache_dir=tmp_path / "c", log_path=tmp_path / "log.jsonl", upstream=provider, min_interval=0)
    first = gw.complete(REQUEST, "Bearer test-key", tag="t")
    second = gw.complete(REQUEST, "Bearer test-key", tag="t")
    assert first.status == second.status == 200
    assert not first.cached and second.cached
    assert len(FakeProvider.calls) == 1
    assert FakeProvider.calls[0]["auth"] == "Bearer test-key"
    log = (tmp_path / "log.jsonl").read_text()
    assert "test-key" not in log
    assert "test-key" not in "".join(p.read_text() for p in (tmp_path / "c").rglob("*.json"))


def test_gateway_retries_rate_limits(tmp_path: Path, provider: str) -> None:
    FakeProvider.fail_first = 2
    gw = Gateway(cache_dir=tmp_path / "c", log_path=tmp_path / "l", upstream=provider, min_interval=0, backoff=0.01)
    assert gw.complete(REQUEST, "Bearer k").status == 200
    assert len(FakeProvider.calls) == 3


def test_gateway_replay_and_no_key(tmp_path: Path, provider: str) -> None:
    replay = Gateway(cache_dir=tmp_path / "c", log_path=tmp_path / "l", upstream=provider, mode="replay")
    assert replay.complete(REQUEST, "Bearer k").status == 503
    live = Gateway(cache_dir=tmp_path / "c", log_path=tmp_path / "l", upstream=provider)
    assert live.complete(REQUEST, "Bearer ").status == 401
    assert live.complete(REQUEST, "Bearer undefined").status == 401
    assert FakeProvider.calls == []


def test_http_server_end_to_end(tmp_path: Path) -> None:
    api = build_api("off", log_path=tmp_path / "l", cache_dir=tmp_path / "c")
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(api))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(f"{base}/health") as resp:
            assert json.loads(resp.read())["ok"] is True
        with urllib.request.urlopen(f"{base}/files/invoices/I01-sat-10477.pdf") as resp:
            assert resp.read(4) == b"%PDF"
        with urllib.request.urlopen(f"{base}/") as resp:
            assert b"Ops console" in resp.read()
    finally:
        server.shutdown()
