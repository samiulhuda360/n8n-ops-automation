# Evaluation results

Run on 2026-10-08 with `python -m opsflow eval` (model `gemini-flash-lite-latest`, gateway `off`). Every workflow ran for real inside n8n from its **Try with sample data** trigger, against the mock systems, on every labelled item. Two modes:

- **rules**: `AI_MODE=off`. The keyword/regex/template baseline that each workflow falls back to.
- **ai**: the shipped workflow: the model suggests, the guard rules decide.

Items in the **heldout** split were written with the rest but never looked at while prompts and rules were tuned. An item counts as handled correctly only when every check on it is right.

## Summary

| Workflow | Items | Rules only | AI + rules | AI, dev | AI, held out | Guard hits (AI) | Straight through (AI) |
|---|---|---|---|---|---|---|---|
| Lead intake and enrichment | 24  | 20/24 (83%) | - | - | - | - | - |
| Supplier invoice to draft bill | 24  | 9/24 (38%) | - | - | - | - | - |
| Customer support triage | 24  | 23/24 (96%) | - | - | - | - | - |
| Daily KPI digest | 21 report days | 5/21 (24%) | - | - | - | - | - |
| Purchase approval routing | 24  | 16/24 (67%) | - | - | - | - | - |
| Blog post to social drafts | 15 blog posts (3 drafts each) | 5/15 (33%) | - | - | - | - | - |

## Checks per workflow

### Lead intake and enrichment

| Check | Rules only | AI + rules | AI, held out |
|---|---|---|---|
| category | 22/24 (92%) | - | - |
| duplicate | 24/24 (100%) | - | - |
| priority | 15/17 (88%) | - | - |
| route | 23/24 (96%) | - | - |

What the AI run wrote to the mock systems: new CRM rows: 13; notes on existing contacts: 4; follow-up drafts awaiting approval: 17; forwarded to support: 4; discarded as spam (logged): 3.

### Supplier invoice to draft bill

| Check | Rules only | AI + rules | AI, held out |
|---|---|---|---|
| field:currency | 24/24 (100%) | - | - |
| field:due date | 10/24 (42%) | - | - |
| field:gst | 10/24 (42%) | - | - |
| field:gst number | 16/24 (67%) | - | - |
| field:invoice date | 10/24 (42%) | - | - |
| field:invoice number | 18/24 (75%) | - | - |
| field:po number | 24/24 (100%) | - | - |
| field:subtotal | 10/24 (42%) | - | - |
| field:supplier name | 24/24 (100%) | - | - |
| field:total | 10/24 (42%) | - | - |
| reasons | 19/24 (79%) | - | - |
| route | 15/24 (62%) | - | - |

What the AI run wrote to the mock systems: draft bills: 5; exception queue: 19; bills created that should have been exceptions: 1.

### Customer support triage

| Check | Rules only | AI + rules | AI, held out |
|---|---|---|---|
| category | 23/24 (96%) | - | - |
| needs person | 23/24 (96%) | - | - |
| priority | 23/24 (96%) | - | - |

What the AI run wrote to the mock systems: helpdesk tickets: 24; urgent alerts posted: 4; emails sent to customers: 0.

### Daily KPI digest

| Check | Rules only | AI + rules | AI, held out |
|---|---|---|---|
| alerts | 21/21 (100%) | - | - |
| five lines | 21/21 (100%) | - | - |
| kpis | 21/21 (100%) | - | - |
| posted numbers grounded | 5/21 (24%) | - | - |

What the AI run wrote to the mock systems: digests posted: 21.

### Purchase approval routing

| Check | Rules only | AI + rules | AI, held out |
|---|---|---|---|
| category | 18/24 (75%) | - | - |
| route | 19/24 (79%) | - | - |

What the AI run wrote to the mock systems: audit entries: 24; approval requests opened (the run pauses at the first approver form): 1; requesters notified: 9.

### Blog post to social drafts

| Check | Rules only | AI + rules | AI, held out |
|---|---|---|---|
| all posts pass checks | 8/15 (53%) | - | - |
| claims flag | 15/15 (100%) | - | - |
| key facts in every post | 12/15 (80%) | - | - |
| no risky claim in ready posts | 14/15 (93%) | - | - |

What the AI run wrote to the mock systems: posts in the review queue: 45; posts published: 0.

## Model calls, latency and cost

Calls go through the caching gateway in the mock services: `live` calls reached the model, `cached` ones were answered from `eval-cache/ai/` (the same request always gets the same stored answer). Model latency is measured on live calls (cached answers keep the latency recorded when they were made). Cost assumes US$0.10 per million input tokens and US$0.40 per million output tokens.

| Workflow | Model calls | Live | Cached | Failed | Tokens in / out | Model p50 / p95 | n8n run time | Cost per item |
|---|---|---|---|---|---|---|---|---|

Total for the AI run: 0 model calls (0 live, 0 cached, 0 failed), 0 input and 0 output tokens.

## Time saved

Assumptions are in `data/time_model.csv`: minutes for doing each item by hand, minutes for a person to review an item that went straight through, minutes for a person to handle a flagged item (with the AI's work already in front of them), rework minutes for an item handled wrongly, and monthly volume. The straight-through and error rates are the measured ones from the AI run above.

`minutes after = straight × review + (1 − straight) × flagged + error × rework`

| Workflow | Manual min/item | Straight through | Error rate | Min/item after | Volume/month | Hours saved/month |
|---|---|---|---|---|---|---|
| **Total** | | | | | | **0** |
