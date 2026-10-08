# How the evaluation works

`python -m opsflow eval` measures the workflows as they actually run in n8n.

## Data

| Workflow | Items | Held out | Labels |
|---|---|---|---|
| Lead intake | 24 web-form leads | 8 | category, priority, duplicate, route |
| Supplier invoices | 24 PDF invoices in three layouts | 8 | every header field, route, exception reasons |
| Support triage | 24 customer emails | 8 | category (one or more acceptable), priority, needs a person |
| KPI digest | 21 report days over two months of orders | 7 | KPIs and alerts from an independent Python calculation |
| Purchase approvals | 24 purchase requests | 8 | category, approval route required by the policy |
| Content | 15 blog posts | 5 | terms every post must carry, whether the post makes claims to check |

All of it is invented: the people, companies and orders. `scripts/make_data.py` generates the sales orders,
invoices (as real PDFs, through fpdf2), purchase requests and seed data with a fixed random seed. The leads,
support emails and blog posts are hand-written JSON.

The **held-out** items were written together with the rest, then set aside: prompts and rules were only ever
tuned against the dev items. The keyword lists of the rule-based baseline were written with the dev items in
view, which helps the baseline more than the AI path.

## Procedure

1. Start the mock services in-process and import all seven workflows into a fresh, throwaway n8n data folder.
2. For each mode (`rules` with `AI_MODE=off`, then `ai`) and each workflow: reset the mock systems to their seed
   state, run `n8n execute --id=<workflow> --rawOutput` (which starts at the **Try with sample data** trigger),
   then read the decision node's output from the execution data and the mock systems' state.
3. Score every item. An item counts as correct only when every applicable check passes.
4. Read the model gateway's call log for live and cached calls, tokens and latency.
5. Write `results/summary.json`, `results/items.csv` (one row per item and mode) and `results/RESULTS.md`.

The purchase-approval run ends with status `waiting`: the first request that needs a manager pauses at its
approval form, as it would in production. Its routing decisions are all made before that point.

## Model gateway and cache

Model calls go to `AI_BASE_URL`. For the evaluation that is the gateway inside the mock services, which caches
answers on disk in `eval-cache/ai/` keyed by a hash of the request, spaces live calls at least 2.5 seconds apart,
retries rate limits and server errors with a growing back-off, and logs each call. The API key travels only in
the request header from n8n's environment; it is never written to the cache or the log.

Because the cache is committed, `python -m opsflow eval --gateway replay` reproduces the AI results without a
key. CI runs the rule-based path in n8n with the gateway switched off, so it never calls a model.

## Time-saved model

`data/time_model.csv` states, for each workflow, the minutes to do one item by hand, the minutes a person spends
reviewing an item that went straight through, the minutes for a flagged item (with the AI's work in front of
them), the rework minutes for an item handled wrongly, and the monthly volume. These are assumptions for a
small retailer, not measurements.

```
minutes after = straight-through share × review + (1 − straight-through share) × flagged + error rate × rework
hours saved per month = volume × (manual minutes − minutes after) / 60
```

The straight-through share and error rate come from the AI run.
