"""One command for the full local demo: the mock systems plus the n8n editor with every workflow imported.

    python -m opsflow demo [--port 5678] [--gateway replay|live|off]

The model gateway defaults to replay, so the demo runs offline from the stored answers in eval-cache/ai.
With --gateway live and AI_API_KEY set, new inputs are sent to the model.
"""

from __future__ import annotations

import os
import subprocess
import threading

from opsflow.build import write_all
from opsflow.mock.server import serve
from opsflow.n8n_cli import N8n
from opsflow.paths import RUNTIME, WORKFLOWS


def run_demo(port: int = 5678, gateway: str = "replay", mock_port: int = 8790) -> int:
    write_all()
    server = serve(mock_port, gateway)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{mock_port}"
    n8n = N8n(
        user_folder=RUNTIME / "n8n-demo",
        env={
            "MOCK_BASE_URL": base,
            "AI_BASE_URL": f"{base}/ai/v1",
            "AI_API_KEY": os.environ.get("AI_API_KEY", ""),
            "N8N_PORT": str(port),
            "WEBHOOK_URL": f"http://localhost:{port}/",
            "N8N_SECURE_COOKIE": "false",
        },
    )
    print("importing the workflows ...")
    n8n.import_folder(WORKFLOWS)
    print(f"mock systems and ops console: {base}/")
    print(f"n8n editor:                   http://localhost:{port}/  (create the owner account on first run)")
    proc = subprocess.Popen([*n8n.command, "start"], env=n8n._env())
    try:
        return proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait(timeout=30)
        return 0
    finally:
        server.shutdown()
