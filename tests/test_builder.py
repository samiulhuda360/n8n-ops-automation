from __future__ import annotations

import copy
import json

from opsflow.build import BUILDERS, all_workflows, render
from opsflow.n8n import Flow, workflow_id
from opsflow.validate import check_workflow, validate


def test_every_workflow_builds_and_is_deterministic() -> None:
    first, second = all_workflows(), all_workflows()
    assert set(first) == {*BUILDERS, "error-handler"}
    for slug in first:
        assert render(first[slug]) == render(second[slug])


def test_ids_are_n8n_shaped() -> None:
    for wf in all_workflows().values():
        assert len(wf["id"]) == 16
        assert wf["id"].isalnum()
    assert workflow_id("a") != workflow_id("b")


def test_committed_files_match_the_builder() -> None:
    report = validate()
    assert all(not problems for problems in report.values()), report


def test_manual_trigger_comes_first_and_errors_are_wired() -> None:
    wfs = all_workflows()
    error_id = wfs["error-handler"]["id"]
    for slug in BUILDERS:
        wf = wfs[slug]
        assert wf["nodes"][0]["name"] == "Try with sample data"
        assert wf["settings"]["errorWorkflow"] == error_id


def test_code_nodes_inline_the_shared_libraries() -> None:
    wf = all_workflows()["support-triage"]
    code = next(n for n in wf["nodes"] if n["name"] == "Apply support rules")["parameters"]["jsCode"]
    assert "function parseAiJson" in code
    assert "function decideTicket" in code
    assert "// ---- node logic" in code


def test_validator_catches_a_stored_key_and_a_broken_link() -> None:
    wfs = all_workflows()
    error_id = wfs["error-handler"]["id"]
    wf = copy.deepcopy(wfs["lead-intake"])
    wf["nodes"][1]["parameters"]["note"] = "key AIzaSyA1234567890abcdefghijklmnopqrst"
    wf["connections"]["Normalise lead"]["main"][0].append({"node": "Nowhere", "type": "main", "index": 0})
    problems = check_workflow("lead-intake", wf, error_id)
    assert any("secret" in p for p in problems)
    assert any("unknown node" in p for p in problems)


def test_validator_catches_a_missing_guard_and_an_unsafe_write() -> None:
    wfs = all_workflows()
    wf = copy.deepcopy(wfs["support-triage"])
    for n in wf["nodes"]:
        if n["type"] == "n8n-nodes-base.code":
            n["parameters"]["jsCode"] = n["parameters"]["jsCode"].replace("SAFETY_RE", "SAFE")
        if n["name"] == "Create helpdesk ticket":
            n["parameters"]["url"] = "={{ 'https://mail.example.com/send' }}"
    problems = check_workflow("support-triage", wf, wfs["error-handler"]["id"])
    assert any("SAFETY_RE" in p for p in problems)
    assert any("outside the allowed list" in p for p in problems)


def test_flow_rejects_duplicate_names() -> None:
    f = Flow("x", "x", "x")
    f.manual("A", (0, 0))
    try:
        f.manual("A", (0, 0))
    except ValueError:
        return
    raise AssertionError("duplicate name accepted")


def test_ai_call_reads_the_key_from_env_only() -> None:
    for wf in all_workflows().values():
        text = json.dumps(wf)
        if "chat/completions" in text:
            assert "$env.AI_API_KEY" in text
