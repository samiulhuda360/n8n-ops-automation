"""A small OpenAI-compatible model gateway with a disk cache, spacing between calls and retries.

The workflows call the model with an ordinary OpenAI-style chat-completions request. In production that request
goes straight to the provider. For evaluation and demos, AI_BASE_URL points at this gateway instead, which:

- answers repeated requests from a disk cache (the same prompt always gets the same answer, at no cost);
- spaces live calls at least `min_interval` seconds apart, because the free quota is shared;
- retries 429 and 5xx responses with a growing back-off;
- logs every call (cached or live, latency, tokens) to a JSONL file for the results tables.

The caller's Authorization header is forwarded to the provider and never stored or logged.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_UPSTREAM = "https://generativelanguage.googleapis.com/v1beta/openai"
RETRY_STATUS = {429, 500, 502, 503, 504}


@dataclass
class GatewayResult:
    status: int
    body: dict[str, Any]
    cached: bool = False


@dataclass
class Gateway:
    cache_dir: Path
    log_path: Path
    mode: str = "live"  # live: cache, then provider | replay: cache only | off: always refuse
    upstream: str = DEFAULT_UPSTREAM
    min_interval: float = 2.5
    max_attempts: int = 4
    backoff: float = 4.0
    timeout: float = 60.0
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _last_call: float = 0.0

    @staticmethod
    def cache_key(request: dict[str, Any]) -> str:
        keep = {k: request.get(k) for k in ("model", "messages", "temperature", "response_format", "max_tokens")}
        return hashlib.sha256(json.dumps(keep, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / key[:2] / f"{key}.json"

    def _log(self, entry: dict[str, Any]) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

    def complete(self, request: dict[str, Any], authorization: str | None, tag: str = "") -> GatewayResult:
        key = self.cache_key(request)
        path = self._cache_path(key)
        started = time.perf_counter()
        base = {"ts": time.time(), "workflow": tag, "model": request.get("model"), "key": key[:12]}

        if self.mode == "off":
            self._log({**base, "cached": False, "status": 503, "latency_ms": 0, "note": "gateway off"})
            return GatewayResult(503, {"error": {"message": "model gateway is switched off"}})

        if path.exists():
            body = json.loads(path.read_text(encoding="utf-8"))
            usage = body.get("usage") or {}
            self._log(
                {
                    **base,
                    "cached": True,
                    "status": 200,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                    "live_latency_ms": body.get("_gateway", {}).get("latency_ms"),
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                }
            )
            return GatewayResult(200, body, cached=True)

        if self.mode == "replay":
            self._log({**base, "cached": False, "status": 503, "latency_ms": 0, "note": "cache miss in replay"})
            return GatewayResult(503, {"error": {"message": "not in the replay cache"}})

        token = (authorization or "").removeprefix("Bearer ").strip()
        if not token or token in {"undefined", "null"}:
            self._log({**base, "cached": False, "status": 401, "latency_ms": 0, "note": "no key"})
            return GatewayResult(401, {"error": {"message": "no API key was sent"}})

        status, body, live_ms = self._call_upstream(request, token)
        if status == 200:
            body["_gateway"] = {"latency_ms": live_ms}
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")
        usage = body.get("usage") or {}
        self._log(
            {
                **base,
                "cached": False,
                "status": status,
                "latency_ms": live_ms,
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
            }
        )
        return GatewayResult(status, body)

    def _call_upstream(self, request: dict[str, Any], token: str) -> tuple[int, dict[str, Any], float]:
        payload = json.dumps(request).encode("utf-8")
        status, body, latency = 500, {"error": {"message": "not called"}}, 0.0
        for attempt in range(1, self.max_attempts + 1):
            with self._lock:  # one live call at a time, spaced out
                wait = self.min_interval - (time.monotonic() - self._last_call)
                if wait > 0:
                    time.sleep(wait)
                self._last_call = time.monotonic()
                started = time.perf_counter()
                req = urllib.request.Request(
                    self.upstream.rstrip("/") + "/chat/completions",
                    data=payload,
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                        status, body = resp.status, json.loads(resp.read().decode("utf-8"))
                except urllib.error.HTTPError as err:
                    status = err.code
                    try:
                        body = json.loads(err.read().decode("utf-8"))
                    except (ValueError, OSError):
                        body = {"error": {"message": f"HTTP {err.code}"}}
                except (urllib.error.URLError, TimeoutError, OSError) as err:
                    status, body = 504, {"error": {"message": f"upstream unreachable: {type(err).__name__}"}}
                latency = round((time.perf_counter() - started) * 1000, 1)
            if status not in RETRY_STATUS or attempt == self.max_attempts:
                break
            time.sleep(self.backoff * attempt)
        if isinstance(body, list):  # some providers wrap errors in a list
            body = body[0] if body else {}
        return status, body, latency
