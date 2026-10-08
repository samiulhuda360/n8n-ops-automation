"""Small helpers that produce n8n workflow JSON from readable Python.

Every Code node is assembled from the shared JavaScript files in opsflow/js plus a few lines of glue, so the
logic can be unit tested outside n8n and reviewed like normal code. Ids are derived from names, so rebuilding
gives the same JSON and a clean git diff.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from opsflow.paths import JS

Node = dict[str, Any]
NS = uuid.UUID("3b8f2c6e-9a41-4f0c-8d57-0e6a2b9c4d11")
MOCK = "($env.MOCK_BASE_URL || 'http://127.0.0.1:8790')"
AI_URL = "={{ ($env.AI_BASE_URL || 'https://generativelanguage.googleapis.com/v1beta/openai') + '/chat/completions' }}"
ERROR_WORKFLOW_NAME = "Ops error handler"


def uid(name: str) -> str:
    return str(uuid.uuid5(NS, name))


def workflow_id(name: str) -> str:
    """n8n workflow ids are 16 alphanumeric characters."""
    return uid("workflow:" + name).replace("-", "")[:16]


def js_lib(*names: str) -> str:
    return "\n\n".join((JS / f"{n}.js").read_text(encoding="utf-8").strip() for n in names)


class Flow:
    """Collects the nodes and connections of one workflow."""

    def __init__(self, name: str, slug: str, description: str) -> None:
        self.name = name
        self.slug = slug
        self.description = description
        self.nodes: list[Node] = []
        self.connections: dict[str, dict[str, list[list[dict[str, Any]]]]] = {}

    # --------------------------------------------------------------------------------------------- plumbing
    def add(self, name: str, type_: str, version: float, position: tuple[int, int], parameters: dict[str, Any],
            **extra: Any) -> str:
        if any(n["name"] == name for n in self.nodes):
            raise ValueError(f"duplicate node name: {name}")
        self.nodes.append(
            {
                "parameters": parameters,
                "id": uid(f"{self.slug}:{name}"),
                "name": name,
                "type": type_,
                "typeVersion": version,
                "position": list(position),
                **extra,
            }
        )
        return name

    def link(self, src: str, dst: str, output: int = 0) -> None:
        main = self.connections.setdefault(src, {"main": []})["main"]
        while len(main) <= output:
            main.append([])
        main[output].append({"node": dst, "type": "main", "index": 0})

    def chain(self, *names: str) -> None:
        for a, b in zip(names, names[1:], strict=False):
            self.link(a, b)

    # -------------------------------------------------------------------------------------------- node kinds
    def webhook(self, name: str, path: str, pos: tuple[int, int]) -> str:
        return self.add(
            name,
            "n8n-nodes-base.webhook",
            2,
            pos,
            {"httpMethod": "POST", "path": path, "responseMode": "onReceived", "options": {}},
            webhookId=uid(f"webhook:{path}"),
        )

    def schedule(self, name: str, pos: tuple[int, int], hour: int) -> str:
        return self.add(
            name,
            "n8n-nodes-base.scheduleTrigger",
            1.2,
            pos,
            {"rule": {"interval": [{"field": "days", "daysInterval": 1, "triggerAtHour": hour}]}},
        )

    def manual(self, name: str, pos: tuple[int, int]) -> str:
        return self.add(name, "n8n-nodes-base.manualTrigger", 1, pos, {})

    def code(self, name: str, pos: tuple[int, int], body: str, *, libs: tuple[str, ...] = (), each: bool = False,
             note: str = "") -> str:
        source = (js_lib(*libs) + "\n\n// ---- node logic\n" if libs else "") + body.strip() + "\n"
        params = {"mode": "runOnceForEachItem" if each else "runOnceForAllItems", "language": "javaScript",
                  "jsCode": source}
        extra: dict[str, Any] = {"notes": note, "notesInFlow": True} if note else {}
        return self.add(name, "n8n-nodes-base.code", 2, pos, params, **extra)

    def http(self, name: str, pos: tuple[int, int], method: str, url: str, *, body: str | None = None,
             query: dict[str, str] | None = None, note: str = "", continue_on_fail: bool = False,
             file_response: bool = False) -> str:
        params: dict[str, Any] = {"method": method, "url": url, "options": {"timeout": 30000}}
        if query:
            params["sendQuery"] = True
            params["queryParameters"] = {"parameters": [{"name": k, "value": v} for k, v in query.items()]}
        if body is not None:
            params.update({"sendBody": True, "contentType": "json", "specifyBody": "json", "jsonBody": body})
        if file_response:
            params["options"]["response"] = {"response": {"responseFormat": "file", "outputPropertyName": "data"}}
        extra: dict[str, Any] = {"notes": note, "notesInFlow": True} if note else {}
        if continue_on_fail:
            extra["onError"] = "continueRegularOutput"
        return self.add(name, "n8n-nodes-base.httpRequest", 4.2, pos, params, **extra)

    def mock(self, name: str, pos: tuple[int, int], method: str, path_expr: str, **kw: Any) -> str:
        """An HTTP call to the mock business systems. path_expr is a JS expression for the path."""
        return self.http(name, pos, method, f"={{{{ {MOCK} + {path_expr} }}}}", **kw)

    def ai_call(self, name: str, pos: tuple[int, int], note: str) -> str:
        return self.add(
            name,
            "n8n-nodes-base.httpRequest",
            4.2,
            pos,
            {
                "method": "POST",
                "url": AI_URL,
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Authorization", "value": "={{ 'Bearer ' + ($env.AI_API_KEY || '') }}"},
                        {"name": "X-Ops-Workflow", "value": self.slug},
                    ]
                },
                "sendBody": True,
                "contentType": "json",
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify($json.ai_request) }}",
                "options": {"timeout": 120000, "batching": {"batch": {"batchSize": 1, "batchInterval": 200}}},
            },
            retryOnFail=True,
            maxTries=3,
            waitBetweenTries=5000,
            onError="continueRegularOutput",
            notes=note,
            notesInFlow=True,
        )

    def if_(self, name: str, pos: tuple[int, int], expression: str, note: str = "") -> str:
        extra: dict[str, Any] = {"notes": note, "notesInFlow": True} if note else {}
        return self.add(
            name,
            "n8n-nodes-base.if",
            2.2,
            pos,
            {
                "conditions": {
                    "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                    "conditions": [
                        {
                            "id": uid(f"{self.slug}:{name}:condition"),
                            "leftValue": f"={{{{ {expression} }}}}",
                            "rightValue": "",
                            "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                        }
                    ],
                    "combinator": "and",
                },
                "looseTypeValidation": True,
                "options": {},
            },
            **extra,
        )

    def sticky(self, name: str, pos: tuple[int, int], content: str, width: int = 380, height: int = 260) -> str:
        return self.add(
            name,
            "n8n-nodes-base.stickyNote",
            1,
            pos,
            {"content": content, "height": height, "width": width, "color": 7},
        )

    # ---------------------------------------------------------------------------------------- shared shapes
    def sample_source(self, pos: tuple[int, int]) -> str:
        """Manual trigger plus a call that loads the labelled sample items from the mock services."""
        trigger = self.manual("Try with sample data", pos)
        load = self.mock(
            "Load sample data",
            (pos[0] + 220, pos[1]),
            "GET",
            f"'/samples/{self.slug}'",
            query={"split": "={{ $env.SAMPLE_SPLIT || 'all' }}", "limit": "={{ $env.SAMPLE_LIMIT || '' }}"},
            note="Invented, labelled items served by the mock services",
        )
        self.link(trigger, load)
        return load

    def ai_step(self, prepare: str, call_name: str, apply: str, pos: tuple[int, int], note: str) -> None:
        """prepare -> 'AI switched on?' -> AI call -> apply; with AI off the items go straight to apply."""
        gate = self.if_(
            "AI switched on?",
            pos,
            "$env.AI_MODE !== 'off' && !!($env.AI_API_KEY || $env.AI_BASE_URL)",
            note="Off: the rule-based path handles everything",
        )
        call = self.ai_call(call_name, (pos[0] + 220, pos[1] - 100), note)
        self.link(prepare, gate)
        self.link(gate, call, 0)
        self.link(gate, apply, 1)
        self.link(call, apply)

    def build(self, error_workflow_id: str | None = None) -> dict[str, Any]:
        settings: dict[str, Any] = {"executionOrder": "v1", "saveManualExecutions": True}
        if error_workflow_id:
            settings["errorWorkflow"] = error_workflow_id
        # `n8n execute` starts from the first starting node in the list, so the manual trigger goes first.
        nodes = sorted(self.nodes, key=lambda n: n["type"] != "n8n-nodes-base.manualTrigger")
        return {
            "name": self.name,
            "nodes": nodes,
            "connections": self.connections,
            "settings": settings,
            "pinData": {},
            "meta": {"templateCredsSetupCompleted": True},
            "tags": [],
            "active": False,
            "id": workflow_id(self.name),
            "versionId": uid(f"{self.name}:version"),
            "description": self.description,
        }


def js_const(name: str, value: Any) -> str:
    """A JS constant holding a Python value (prompts, schemas), safely encoded."""
    return f"const {name} = {json.dumps(value, ensure_ascii=False, indent=2)};"
