"""Runs the real workflows in a throwaway n8n against the mock services and collects what happened.

For each workflow and mode the runner resets the mock systems, runs the workflow from its "Try with sample
data" trigger with `n8n execute`, and keeps the execution data, the mock systems' state afterwards and the model
gateway's call log.
"""

from __future__ import annotations

import json
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from opsflow.build import write_all
from opsflow.mock.server import serve
from opsflow.n8n_cli import N8n
from opsflow.paths import RUNTIME, WORKFLOWS

MODES = ("rules", "ai")


@dataclass
class WorkflowRun:
    slug: str
    mode: str
    execution: dict[str, Any]
    state: dict[str, list[dict[str, Any]]]
    wall_seconds: float
    ai_calls: list[dict[str, Any]] = field(default_factory=list)

    @property
    def status(self) -> str:
        return str(self.execution.get("status"))

    @property
    def error(self) -> str | None:
        err = self.execution["data"]["resultData"].get("error")
        return json.dumps(err)[:500] if err else None


def read_calls(log: Path, start_line: int) -> list[dict[str, Any]]:
    if not log.exists():
        return []
    lines = log.read_text(encoding="utf-8").splitlines()[start_line:]
    return [json.loads(line) for line in lines if line.strip()]


def run_all(
    modes: tuple[str, ...] = MODES,
    slugs: tuple[str, ...] | None = None,
    split: str = "all",
    gateway_mode: str = "live",
    port: int = 8790,
    ai_key: str | None = None,
    log=print,
) -> list[WorkflowRun]:
    write_all()
    workflows = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in WORKFLOWS.glob("*.json")}
    order = slugs or tuple(s for s in workflows if s != "error-handler")

    folder = RUNTIME / "n8n-eval"
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)
    call_log = RUNTIME / "ai-calls.jsonl"
    server = serve(port=port, ai_mode=gateway_mode, log_path=call_log)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    runs: list[WorkflowRun] = []
    try:
        n8n = N8n(
            user_folder=folder,
            env={
                "MOCK_BASE_URL": base,
                "AI_BASE_URL": f"{base}/ai/v1",
                "AI_API_KEY": ai_key or "",
                "SAMPLE_SPLIT": split,
                "WEBHOOK_URL": "http://localhost:5678/",
            },
        )
        log("importing workflows into a fresh n8n data folder ...")
        n8n.import_folder(WORKFLOWS)
        for mode in modes:
            n8n.env["AI_MODE"] = "off" if mode == "rules" else "on"
            for slug in order:
                reset(base)
                before = len(call_log.read_text(encoding="utf-8").splitlines()) if call_log.exists() else 0
                started = time.perf_counter()
                execution = n8n.execute(workflows[slug]["id"])
                wall = time.perf_counter() - started
                run = WorkflowRun(slug, mode, execution, state(base), wall, read_calls(call_log, before))
                log(
                    f"  {mode:5} {slug:18} {run.status:8} {wall:6.1f}s  model calls: {len(run.ai_calls)}"
                    + (f"  ERROR {run.error}" if run.error else "")
                )
                runs.append(run)
    finally:
        server.shutdown()
        server.server_close()
    return runs


def reset(base: str) -> None:
    import urllib.request

    urllib.request.urlopen(urllib.request.Request(f"{base}/admin/reset", method="POST"), timeout=10).read()


def state(base: str) -> dict[str, list[dict[str, Any]]]:
    import urllib.request

    with urllib.request.urlopen(f"{base}/admin/state", timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))
