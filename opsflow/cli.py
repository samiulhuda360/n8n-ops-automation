"""Command line entry point.

python -m opsflow build                 # regenerate workflows/*.json from opsflow/flows
python -m opsflow validate              # check the workflow files (CI runs this)
python -m opsflow mock                  # run the mock business systems on :8790
python -m opsflow eval [--modes rules,ai] [--split all|dev|heldout] [--gateway live|replay]
python -m opsflow report                # rebuild results/RESULTS.md from results/summary.json
python -m opsflow demo                  # mock systems + n8n editor with the workflows imported
"""

from __future__ import annotations

import argparse
import os
import sys


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        prog="opsflow", description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build", help="generate workflows/*.json")
    sub.add_parser("validate", help="check the workflow files")
    mock = sub.add_parser("mock", help="run the mock business systems")
    mock.add_argument("--port", type=int, default=8790)
    mock.add_argument("--ai-mode", choices=("live", "replay", "off"), default="live")
    ev = sub.add_parser("eval", help="run every workflow on the labelled samples and score it")
    ev.add_argument("--modes", default="rules,ai")
    ev.add_argument("--split", default="all", choices=("all", "dev", "heldout"))
    ev.add_argument("--gateway", default="live", choices=("live", "replay", "off"))
    ev.add_argument("--only", default="", help="comma-separated workflow slugs")
    sub.add_parser("report", help="rebuild results/RESULTS.md from results/summary.json")
    demo = sub.add_parser("demo", help="mock systems plus the n8n editor, workflows imported")
    demo.add_argument("--port", type=int, default=5678)
    demo.add_argument("--gateway", default="replay", choices=("live", "replay", "off"))
    args = parser.parse_args(argv)

    if args.command == "build":
        from opsflow.build import write_all

        for path in write_all():
            print("wrote", path.relative_to(path.parent.parent))
        return 0
    if args.command == "validate":
        from opsflow.validate import main as validate_main

        return validate_main()
    if args.command == "mock":
        from opsflow.mock.server import serve

        server = serve(args.port, args.ai_mode)
        print(f"mock systems on http://127.0.0.1:{args.port} (console at /, model gateway {args.ai_mode})")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            server.shutdown()
        return 0
    if args.command == "eval":
        from opsflow.eval.report import evaluate

        modes = tuple(m for m in args.modes.split(",") if m)
        only = tuple(s for s in args.only.split(",") if s) or None
        key = os.environ.get("AI_API_KEY", "")
        return evaluate(modes=modes, split=args.split, gateway=args.gateway, only=only, ai_key=key)
    if args.command == "report":
        from opsflow.eval.report import rebuild_markdown

        rebuild_markdown()
        return 0
    if args.command == "demo":
        from opsflow.demo import run_demo

        return run_demo(port=args.port, gateway=args.gateway)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
