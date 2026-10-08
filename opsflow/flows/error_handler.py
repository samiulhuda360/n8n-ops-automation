"""The shared error workflow: any failed production execution is logged and posted to #ops-alerts."""

from __future__ import annotations

from opsflow.n8n import ERROR_WORKFLOW_NAME, Flow

DESCRIBE = """
// n8n passes { execution, workflow } to an error workflow.
return $input.all().map((item) => {
  const e = item.json.execution || {};
  const wf = item.json.workflow || {};
  const message = (e.error && e.error.message) || 'Unknown error';
  return { json: {
    workflow: wf.name || 'unknown workflow',
    workflow_id: wf.id || null,
    execution_id: e.id || null,
    execution_url: e.url || null,
    node: e.lastNodeExecuted || null,
    mode: e.mode || null,
    message: String(message).slice(0, 500),
    text: `Workflow "${wf.name || 'unknown'}" failed at "${e.lastNodeExecuted || '?'}": ${String(message).slice(0, 300)}${e.url ? `\\nExecution: ${e.url}` : ''}`,
  } };
});
"""

SAMPLE = """
// The shape n8n sends to an error workflow, for trying this one by hand.
return [{ json: {
  execution: { id: 'sample-231', url: 'http://localhost:5678/workflow/sample/executions/231', lastNodeExecuted: 'Create draft bill', mode: 'webhook',
    error: { message: 'The service refused the connection (ECONNREFUSED)' } },
  workflow: { id: 'sample', name: 'Supplier invoice to draft bill' },
} }];
"""


def build() -> Flow:
    f = Flow(
        ERROR_WORKFLOW_NAME,
        "error-handler",
        "Shared error workflow for all six workflows: logs the failure and alerts #ops-alerts with a link to "
        "the failed execution.",
    )
    trig = f.add("When a workflow fails", "n8n-nodes-base.errorTrigger", 1, (0, 0), {})
    manual = f.manual("Try with a sample error", (0, 200))
    sample = f.code("Sample failure", (220, 200), SAMPLE)
    describe = f.code("Describe the failure", (440, 100), DESCRIBE)
    log = f.mock(
        "Log the error",
        (660, 100),
        "POST",
        "'/ops/errors'",
        body="={{ JSON.stringify({ workflow: $json.workflow, node: $json.node, message: $json.message, execution_id: $json.execution_id, execution_url: $json.execution_url }) }}",
    )
    alert = f.mock(
        "Alert #ops-alerts",
        (880, 100),
        "POST",
        "'/chat/ops-alerts'",
        body="={{ JSON.stringify({ text: $('Describe the failure').item.json.text }) }}",
    )
    f.link(trig, describe)
    f.link(manual, sample)
    f.link(sample, describe)
    f.chain(describe, log, alert)
    return f
