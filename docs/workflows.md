# The workflows in detail

Every workflow follows the same shape:

1. **Two ways in.** A production trigger (a webhook, which is a URL another system calls, or a schedule) and a
   manual **Try with sample data** trigger that loads labelled items from the mock services. Both feed the same
   nodes, so testing exercises the real path.
2. **Normalise.** One Code node turns either input into the same clean record.
3. **AI step behind a switch.** An `AI switched on?` gate sends items to one OpenAI-compatible HTTP call
   (Gemini by default) or, when the model is off or has no key, straight past it. The call retries three
   times and never fails the run: a missing or unreadable answer falls back to the rule-based baseline.
4. **Guard rules decide.** A Code node validates the model's answer against a fixed schema and applies the
   business rules. The model suggests; the rules decide.
5. **Write to drafts, queues and logs only.** Nothing is emailed, posted, approved or paid by a workflow.
   `python -m opsflow validate` checks this on every outbound call.
6. **Error workflow.** Every workflow names `Ops error handler` as its error workflow. A failed production run
   is logged and posted to `#ops-alerts` with a link to the failed execution.

The JavaScript in the Code nodes lives in `opsflow/js/*.js`; the builder inlines it, and `tests/js` tests it with
Node's built-in test runner.

## 1. Lead intake and enrichment

| | |
|---|---|
| Trigger | `POST /webhook/lead-form` (web form) |
| AI | category, priority (hot, warm, cold), one-line summary, first-reply draft |
| Guards | duplicate check against the CRM (email, or phone with `+64` normalised) and earlier items in the batch; spam rules (two or more links, SEO, link-selling and investment-scheme phrases) override the model; instructions inside the form are flagged and can never make a lead hot; drafts that mention prices, discounts or delivery promises are flagged |
| Writes | CRM row or a note on the existing contact, follow-up draft with status `awaiting approval`, support ticket for retail questions, spam log, a `#sales` summary of hot leads |

## 2. Supplier invoice to draft bill

| | |
|---|---|
| Trigger | `POST /webhook/supplier-invoice` with an attachment URL (from an inbound-email service) |
| AI | extraction of every header field and line into a fixed JSON schema |
| Guards | GST must be 15% of the subtotal (0 for overseas suppliers); subtotal + GST = total; lines add up to the subtotal; supplier must be known; no duplicate invoice number; PO amount within 5%; due date after invoice date; every amount and the invoice number must appear in the PDF text, so nothing invented reaches a bill |
| Writes | draft bill (always status `DRAFT`) or an exception with reasons, plus a `#accounts` summary |

## 3. Customer support triage

| | |
|---|---|
| Trigger | `POST /webhook/support-email` |
| AI | category (eight), priority (urgent, high, normal, low), needs-a-person flag, reason, reply draft |
| Guards | safety wording (injury, burns, fire, gas, overheating, cracked gear, children at risk) and New Zealand consumer-law wording (Disputes Tribunal, Commerce Commission, Consumer Guarantees Act, lawyers) make an email urgent and send it to a person, whatever the model said; instructions inside an email go to a person; drafts that promise refunds, replacements or compensation go to a person; complaints, warranty and wholesale always go to a person |
| Writes | helpdesk ticket with the draft (nothing is sent), `#support-escalations` alert for urgent tickets |

## 4. Daily KPI digest

| | |
|---|---|
| Trigger | every day at 7am (New Zealand time), reporting on yesterday |
| Data | one read-only SQL query grouped by day, channel, status and product; KPIs are computed in code |
| AI | a five-line summary written from the computed facts |
| Guards | exactly five lines; every number in the text must match a computed fact (whole-dollar and one-decimal rounding allowed); otherwise the template summary is posted instead |
| Writes | a Slack-format message (header, bullet section, context line) to the chat webhook |

## 5. Purchase approval routing

| | |
|---|---|
| Trigger | `POST /webhook/purchase-request` |
| AI | spending category, restricted-spend flag and a one-line summary for the approver; it never approves |
| Policy (in order) | R1 budget code must be valid, otherwise returned to the requester · R2 restricted spend (gifts, vouchers, alcohol, cash, personal use) goes to finance · R3 over $5,000 goes to the director · R4 over $500, R5 a supplier not on the approved list, or R6 a likely split purchase (same requester and supplier within 14 days adding up to more than $500) goes to the manager · R7 nobody approves their own request |
| Human step | the approver gets a chat message with a link to an n8n form (a **Wait** node that resumes on form submission). A decision from anyone other than the expected approver is recorded as "not decided". The loop handles one request at a time, so each approval has its own form |
| Writes | an audit entry for every routing and every decision, the approval record, and chat messages to the requester |

## 6. Blog post to social drafts

| | |
|---|---|
| Trigger | `POST /webhook/blog-published` (from the CMS) |
| AI | LinkedIn, Instagram and X drafts in one call |
| Guards | per-channel length (X counts links as 23 characters), link rules (required on LinkedIn and X, not allowed on Instagram), hashtag limits; every number must appear in the blog post; absolute claims (guaranteed, 100%, best, proven, completely safe, for life, ever made) are flagged in the drafts and in the source post |
| Writes | three review-queue items per post with their check results; a `#marketing` summary. Nothing is ever published |

## Moving from the mock services to real systems

Each mock endpoint stands for one node you would swap in:

| Mock endpoint | Real node |
|---|---|
| `/crm/*` | HubSpot, Pipedrive or Google Sheets |
| `/accounting/*` | Xero or MYOB (create bill as draft) |
| `/helpdesk/tickets` | Zendesk, Freshdesk or Gmail "create draft" |
| `/chat/*` | Slack or Telegram |
| `/sales/query` | Postgres or MySQL node with the same SQL |
| `/approvals`, `/audit` | Postgres tables or Airtable |
| `/content/review-queue` | Notion, Airtable or a Google Sheet |
