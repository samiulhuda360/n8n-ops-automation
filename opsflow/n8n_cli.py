"""Drives the n8n command line: import the workflows into a throwaway data folder and run them.

n8n is found through the N8N_BIN environment variable (a path to `n8n`, `n8n.cmd` or the package's `bin/n8n`
script), or on PATH.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def find_n8n() -> list[str]:
    configured = os.environ.get("N8N_BIN")
    if configured:
        path = Path(configured)
        if path.is_file() and path.suffix.lower() not in (".cmd", ".exe", ".bat") and path.name != "n8n.cmd":
            return ["node", str(path)]
        return [str(path)]
    found = shutil.which("n8n")
    if not found:
        raise RuntimeError("n8n not found: install it (npm install -g n8n) or set N8N_BIN")
    return [found]


def run_data(stdout: str) -> dict[str, Any]:
    """`n8n execute --rawOutput` prints some log lines, then the execution as JSON."""
    start = stdout.find('{\n  "data"')
    if start < 0:
        start = stdout.find("{")
    if start < 0:
        raise RuntimeError(f"no execution JSON in the n8n output:\n{stdout[-3000:]}")
    return json.loads(stdout[start:])


def node_items(execution: dict[str, Any], node: str, output: int = 0) -> list[dict[str, Any]]:
    """All items a node produced on one output, across every run of that node."""
    runs = execution["data"]["resultData"]["runData"].get(node, [])
    items: list[dict[str, Any]] = []
    for run in runs:
        main = (run.get("data") or {}).get("main") or []
        if len(main) > output and main[output]:
            items += [i["json"] for i in main[output]]
    return items


def node_time_ms(execution: dict[str, Any], node: str) -> float:
    runs = execution["data"]["resultData"]["runData"].get(node, [])
    return float(sum(r.get("executionTime", 0) for r in runs))


@dataclass
class N8n:
    user_folder: Path
    env: dict[str, str] = field(default_factory=dict)
    command: list[str] = field(default_factory=find_n8n)

    def _env(self) -> dict[str, str]:
        return {
            **os.environ,
            "N8N_USER_FOLDER": str(self.user_folder),
            "N8N_DIAGNOSTICS_ENABLED": "false",
            "N8N_VERSION_NOTIFICATIONS_ENABLED": "false",
            "N8N_BLOCK_ENV_ACCESS_IN_NODE": "false",
            **self.env,
        }

    def run(self, args: list[str], timeout: int = 900) -> str:
        proc = subprocess.run(
            [*self.command, *args],
            env=self._env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"n8n {' '.join(args)} failed:\n{proc.stdout[-3000:]}\n{proc.stderr[-3000:]}")
        return proc.stdout

    def import_folder(self, folder: Path) -> None:
        self.run(["import:workflow", "--separate", f"--input={folder}"])

    def execute(self, workflow_id: str) -> dict[str, Any]:
        return run_data(self.run(["execute", f"--id={workflow_id}", "--rawOutput"]))
