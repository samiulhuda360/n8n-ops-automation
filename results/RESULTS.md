# Evaluation results

Run on 2026-10-14 with `python -m opsflow eval` (model `gemini-flash-lite-latest`, gateway `live`). Every workflow ran for real inside n8n from its **Try with sample data** trigger, against the mock systems, on every labelled item. Two modes:

- **rules**: `AI_MODE=off`. The keyword/regex/template baseline that each workflow falls back to.
- **ai**: the shipped workflow: the model suggests, the guard rules decide.

Items in the **heldout** split were written with the rest but never looked at while prompts and rules were tuned. An item counts as handled correctly only when every check on it is right.

## Summary

| Workflow | Items | Rules only | AI + rules | AI, dev | AI, held out | Guard hits (AI) | Straight through (AI) |
|---|---|---|---|---|---|---|---|
| Lead intake and enrichment | 24  | 20/24 (83%) | 23/24 (96%) | 16/16 (100%) | 7/8 (88%) | 3 | 21/24 (88%) |
| Supplier invoice to draft bill | 24  | 9/24 (38%) | 24/24 (100%) | 16/16 (100%) | 8/8 (100%) | 12 | 12/24 (50%) |
| Customer support triage | 24  | 23/24 (96%) | 24/24 (100%) | 16/16 (100%) | 8/8 (100%) | 5 | 12/24 (50%) |
| Daily KPI digest | 21 report days | 21/21 (100%) | 21/21 (100%) | 14/14 (100%) | 7/7 (100%) | 2 | 21/21 (100%) |
| Purchase approval routing | 24  | 18/24 (75%) | 24/24 (100%) | 16/16 (100%) | 8/8 (100%) | 18 | 8/24 (33%) |
| Blog post to social drafts | 15 blog posts (3 drafts each) | 7/15 (47%) | 11/15 (73%) | 7/10 (70%) | 4/5 (80%) | 7 | 12/15 (80%) |

## Checks per workflow

### Lead intake and enrichment

| Check | Rules only | AI + rules | AI, held out |
|---|---|---|---|
| category | 22/24 (92%) | 24/24 (100%) | 8/8 (100%) |
| duplicate | 24/24 (100%) | 24/24 (100%) | 8/8 (100%) |
| priority | 15/17 (88%) | 16/17 (94%) | 5/6 (83%) |
| route | 23/24 (96%) | 24/24 (100%) | 8/8 (100%) |

What the AI run wrote to the mock systems: new CRM rows: 13; notes on existing contacts: 4; follow-up drafts awaiting approval: 17; forwarded to support: 3; discarded as spam (logged): 4.

Items not handled correctly (AI + rules):

| Item | Split | Failed checks | Expected | Got |
|---|---|---|---|---|
| L21 | heldout | priority | club_or_school / warm / dup=False | club_or_school / hot / dup=False |

### Supplier invoice to draft bill

| Check | Rules only | AI + rules | AI, held out |
|---|---|---|---|
| field:currency | 24/24 (100%) | 24/24 (100%) | 8/8 (100%) |
| field:due date | 10/24 (42%) | 24/24 (100%) | 8/8 (100%) |
| field:gst | 10/24 (42%) | 24/24 (100%) | 8/8 (100%) |
| field:gst number | 16/24 (67%) | 24/24 (100%) | 8/8 (100%) |
| field:invoice date | 10/24 (42%) | 24/24 (100%) | 8/8 (100%) |
| field:invoice number | 18/24 (75%) | 24/24 (100%) | 8/8 (100%) |
| field:po number | 24/24 (100%) | 24/24 (100%) | 8/8 (100%) |
| field:subtotal | 10/24 (42%) | 24/24 (100%) | 8/8 (100%) |
| field:supplier name | 24/24 (100%) | 24/24 (100%) | 8/8 (100%) |
| field:total | 10/24 (42%) | 24/24 (100%) | 8/8 (100%) |
| reasons | 19/24 (79%) | 24/24 (100%) | 8/8 (100%) |
| route | 15/24 (62%) | 24/24 (100%) | 8/8 (100%) |

What the AI run wrote to the mock systems: draft bills: 12; exception queue: 12; bills created that should have been exceptions: 0.

Every item was handled correctly.

### Customer support triage

| Check | Rules only | AI + rules | AI, held out |
|---|---|---|---|
| category | 23/24 (96%) | 24/24 (100%) | 8/8 (100%) |
| needs person | 23/24 (96%) | 24/24 (100%) | 8/8 (100%) |
| priority | 23/24 (96%) | 24/24 (100%) | 8/8 (100%) |

What the AI run wrote to the mock systems: helpdesk tickets: 24; urgent alerts posted: 5; emails sent to customers: 0.

Every item was handled correctly.

### Daily KPI digest

| Check | Rules only | AI + rules | AI, held out |
|---|---|---|---|
| alerts | 21/21 (100%) | 21/21 (100%) | 7/7 (100%) |
| five lines | 21/21 (100%) | 21/21 (100%) | 7/7 (100%) |
| kpis | 21/21 (100%) | 21/21 (100%) | 7/7 (100%) |
| posted numbers grounded | 21/21 (100%) | 21/21 (100%) | 7/7 (100%) |

What the AI run wrote to the mock systems: digests posted: 21.

Every item was handled correctly.

### Purchase approval routing

| Check | Rules only | AI + rules | AI, held out |
|---|---|---|---|
| category | 18/24 (75%) | 24/24 (100%) | 8/8 (100%) |
| route | 21/24 (88%) | 24/24 (100%) | 8/8 (100%) |

What the AI run wrote to the mock systems: audit entries: 24; approval requests opened (the run pauses at the first approver form): 1; requesters notified: 8.

Every item was handled correctly.

### Blog post to social drafts

| Check | Rules only | AI + rules | AI, held out |
|---|---|---|---|
| all posts pass checks | 10/15 (67%) | 12/15 (80%) | 4/5 (80%) |
| claims flag | 15/15 (100%) | 15/15 (100%) | 5/5 (100%) |
| key facts in every post | 12/15 (80%) | 14/15 (93%) | 5/5 (100%) |
| no risky claim in ready posts | 14/15 (93%) | 15/15 (100%) | 5/5 (100%) |

What the AI run wrote to the mock systems: posts in the review queue: 45; posts published: 0.

Items not handled correctly (AI + rules):

| Item | Split | Failed checks | Expected | Got |
|---|---|---|---|---|
| B02 | dev | all_posts_pass_checks | claims=False mention=['Kea'] | claims=[] passed=2/3 |
| B05 | dev | all_posts_pass_checks | claims=False mention=['24 hours'] | claims=[] passed=2/3 |
| B06 | dev | key_facts_in_every_post | claims=False mention=['Wellington', '14 November'] | claims=[] passed=3/3 |
| B15 | heldout | all_posts_pass_checks | claims=True mention=['Lumen'] | claims=['ever made'] passed=0/3 |

## Model calls, latency and cost

Calls go through the caching gateway in the mock services: `live` calls reached the model, `cached` ones were answered from `eval-cache/ai/` (the same request always gets the same stored answer). Model latency is measured on live calls (cached answers keep the latency recorded when they were made). Cost assumes US$0.10 per million input tokens and US$0.40 per million output tokens.

| Workflow | Model calls | Live | Cached | Failed | Tokens in / out | Model p50 / p95 | n8n run time | Cost per item |
|---|---|---|---|---|---|---|---|---|
| Lead intake and enrichment | 24 | 3 | 21 | 0 | 11,806 / 3,174 | 1.8s / 6.9s | 38.9s for 24 | US$0.00010 |
| Supplier invoice to draft bill | 24 | 0 | 24 | 0 | 11,216 / 5,622 | 3.0s / 16.3s | 7.1s for 24 | US$0.00014 |
| Customer support triage | 24 | 0 | 24 | 0 | 10,736 / 2,267 | 1.9s / 10.1s | 6.0s for 24 | US$0.00008 |
| Daily KPI digest | 21 | 0 | 21 | 0 | 9,876 / 2,384 | 5.8s / 9.3s | 5.6s for 21 | US$0.00009 |
| Purchase approval routing | 24 | 6 | 18 | 0 | 7,522 / 1,748 | 3.1s / 15.4s | 57.1s for 24 | US$0.00006 |
| Blog post to social drafts | 15 | 0 | 15 | 0 | 5,587 / 5,339 | 6.1s / 8.9s | 4.4s for 15 | US$0.00018 |

Total for the AI run: 132 model calls (9 live, 123 cached, 0 failed), 56,743 input and 20,534 output tokens.

## Time saved

Assumptions are in `data/time_model.csv`: minutes for doing each item by hand, minutes for a person to review an item that went straight through, minutes for a person to handle a flagged item (with the AI's work already in front of them), rework minutes for an item handled wrongly, and monthly volume. The straight-through and error rates are the measured ones from the AI run above.

`minutes after = straight × review + (1 − straight) × flagged + error × rework`

| Workflow | Manual min/item | Straight through | Error rate | Min/item after | Volume/month | Hours saved/month |
|---|---|---|---|---|---|---|
| Lead intake and enrichment | 9 | 88% | 4% | 2.4 | 120 | 13.3 |
| Supplier invoice to draft bill | 7 | 50% | 0% | 3.0 | 220 | 14.7 |
| Customer support triage | 6 | 50% | 0% | 3.5 | 600 | 25.0 |
| Daily KPI digest | 30 | 100% | 0% | 1.0 | 30 | 14.5 |
| Purchase approval routing | 10 | 33% | 0% | 2.2 | 80 | 10.4 |
| Blog post to social drafts | 45 | 80% | 27% | 12.1 | 8 | 4.4 |
| **Total** | | | | | | **82** |
