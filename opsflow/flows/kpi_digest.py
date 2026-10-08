"""Workflow 4: daily sales query -> KPIs -> AI five-line summary -> every number checked -> chat message."""

from __future__ import annotations

from opsflow.n8n import Flow, js_const

PROMPT = """You write the daily sales update for the managers of Acme Outdoor Gear, a New Zealand outdoor gear retailer.

You get one JSON object of facts computed from the sales database. Write exactly five short lines (each under 140 characters) for a chat message:
1. Revenue and number of orders, with the change against the same day last week.
2. Average order value and units sold.
3. The channel split: online, store and wholesale revenue.
4. The top product and the refunds.
5. The alerts that need a look, in plain words, or "No alerts today." if the alerts list is empty.

Use only numbers that appear in the facts. You may write money as whole dollars (for example $9,664) and percentages with one decimal place. Do not calculate new numbers, totals or differences. No emoji, no markdown.

Reply with JSON only: {"lines": ["...", "...", "...", "...", "..."]}"""

YESTERDAY = """
// The schedule runs early in the morning and reports on yesterday (New Zealand time).
const nz = new Intl.DateTimeFormat('en-CA', { timeZone: 'Pacific/Auckland' }).format(new Date());
const d = new Date(`${nz}T00:00:00Z`);
d.setUTCDate(d.getUTCDate() - 1);
return [{ json: { report_date: d.toISOString().slice(0, 10) } }];
"""

NORMALISE = """
const e = pickInput($json);
const reportDate = String(e.report_date || '').slice(0, 10);
if (!/^\\d{4}-\\d{2}-\\d{2}$/.test(reportDate)) throw new Error(`Not a date: ${e.report_date}`);
return { json: { sample_id: e.sample_id || null, report_date: reportDate, prev_date: shiftDate(reportDate, -7), sql: KPI_SQL } };
"""

COMPUTE = """
const { sample_id, report_date } = $('Normalise date').item.json;
return { json: { sample_id, kpis: kpisFromRows($json.rows || [], report_date) } };
"""

PREPARE = (
    js_const("SYSTEM", PROMPT)
    + """
const { sample_id, kpis } = $json;
const facts = { ...kpis };
return { json: { sample_id, kpis, ai_request: aiRequest(SYSTEM, JSON.stringify(facts, null, 2), { model: $env.AI_MODEL || 'gemini-flash-lite-latest', maxTokens: 500 }) } };
"""
)

CHECK = """
// The model writes; this node checks. Any number that isn't in the query result sends us to the template.
const { sample_id, kpis } = $('Prepare AI request').item.json;
const ai = parseAiJson($json);
let lines = ai && Array.isArray(ai.lines) ? ai.lines.map((l) => String(l).replace(/^\\s*[-*•\\d.]+\\s*/, '').trim()).filter(Boolean) : null;
let grounding = lines ? groundingCheck(lines, kpis) : { ok: false, problems: ['no_model_answer'], ungrounded: [] };
let source = 'AI, all numbers checked';
if (!lines) {
  lines = templateSummary(kpis);
  source = 'template (AI off or no answer)';
} else if (!grounding.ok) {
  lines = templateSummary(kpis);
  source = `template (AI text failed the check: ${grounding.problems.join(', ')})`;
}
return { json: { sample_id, report_date: kpis.report_date, kpis, lines, summary_source: source, ai_grounding: grounding, message: chatMessage(kpis, lines, source) } };
"""


def build() -> Flow:
    f = Flow(
        "Daily KPI digest",
        "kpi-digest",
        "Every morning: queries yesterday's sales, computes the KPIs, has AI write a five-line summary, checks "
        "every number in it against the query result, and posts the digest to the team chat.",
    )
    f.sticky(
        "About this workflow",
        (-40, -400),
        "## Daily KPI digest\nSQL query → KPIs in code → AI writes 5 lines → number check → chat.\n\n"
        "**Guards:** the KPIs are computed in code, never by the model · every number in the AI text must match "
        "a computed fact (rounding allowed) and there must be exactly five lines · otherwise the template "
        "summary is posted.\n\n**AI off:** template summary.",
        width=520,
        height=230,
    )
    sched = f.schedule("Every day at 7am", (0, 0), 7)
    yday = f.code("Report on yesterday", (220, 0), YESTERDAY)
    load = f.sample_source((0, 200))
    norm = f.code("Normalise date", (440, 100), NORMALISE, libs=("common", "kpi"), each=True)
    query = f.mock(
        "Query sales", (660, 100), "POST", "'/sales/query'",
        body="={{ JSON.stringify({ sql: $json.sql, params: [$json.report_date, $json.prev_date] }) }}",
        note="Read-only SQL, grouped by day, channel, status and product",
    )
    compute = f.code("Compute KPIs", (880, 100), COMPUTE, libs=("common", "kpi"), each=True)
    prep = f.code("Prepare AI request", (1100, 100), PREPARE, libs=("common",), each=True)
    check = f.code("Check every number", (1760, 100), CHECK, libs=("common", "kpi"), each=True,
                   note="Ungrounded numbers -> template")
    f.ai_step(prep, "Write summary (AI)", check, (1320, 100), "Five lines from the facts")
    post = f.mock(
        "Post to #daily-kpis", (1980, 100), "POST", "'/chat/daily-kpis'",
        body="={{ JSON.stringify({ sample_id: $json.sample_id, report_date: $json.report_date, text: $json.message.text, blocks: $json.message.blocks, summary_source: $json.summary_source }) }}",
        note="Slack-format message to the chat webhook",
    )
    f.link(sched, yday)
    f.link(yday, norm)
    f.link(load, norm)
    f.chain(norm, query, compute, prep)
    f.link(check, post)
    return f
