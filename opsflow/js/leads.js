// Lead intake: duplicate keys, spam rules, a keyword baseline and the final decision.
// Needs common.js.

const LEAD_CATEGORIES = ['wholesale', 'corporate_bulk', 'club_or_school', 'sponsorship_or_partnership',
  'retail_customer', 'spam'];
const SALES_CATEGORIES = ['wholesale', 'corporate_bulk', 'club_or_school', 'sponsorship_or_partnership'];
const LEAD_PRIORITIES = ['hot', 'warm', 'cold'];
const LEAD_OWNERS = {
  wholesale: 'Trade sales',
  corporate_bulk: 'Corporate sales',
  club_or_school: 'Community sales',
  sponsorship_or_partnership: 'Marketing',
};

function normEmail(email) {
  return String(email || '').trim().toLowerCase();
}

function normPhone(phone) {
  let digits = String(phone || '').replace(/\D/g, '');
  if (digits.startsWith('64')) digits = '0' + digits.slice(2);
  return digits;
}

const SPAM_PHRASES = /(\bseo\b|page 1 of google|first-page rankings?|backlinks?|do-follow|guest post|link exchange|swap links|crypto|token fund|bitcoin|monthly returns|\d+% (monthly|weekly) returns|free (seo )?audit)/i;

/** Plain rules that mark a form entry as spam whatever the model says. */
function spamSignals(lead) {
  const text = `${lead.company || ''} ${lead.message || ''}`;
  const signals = [];
  const links = (text.match(/https?:\/\//gi) || []).length;
  if (links >= 2) signals.push('two_or_more_links');
  const phrase = text.match(SPAM_PHRASES);
  if (phrase) signals.push(`spam_phrase:${phrase[0].toLowerCase()}`);
  if (/(account|bank) details|send (us )?your password/i.test(text)) signals.push('asks_for_account_details');
  return signals;
}

const VOLUME_RE = /(\$\s?[\d,]+|\b\d[\d,]*k\b|\b\d{2,}\s+(?:[a-z'-]+\s+){0,3}(?:packs?|bags?|tents?|mats?|bottles?|jackets?|shells?|units|items|people|members|staff|runners|students))/i;
const DATE_RE = /(\b\d{1,2}(st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}\b|this week|next week|in (two|three|four|\d) weeks)/i;

/** The keyword baseline: what a rule-only workflow would do without a model. */
function baselineLead(lead) {
  const text = `${lead.message || ''}`;
  const company = String(lead.company || '').trim();
  let category = 'wholesale';
  if (spamSignals(lead).length) category = 'spam';
  else if (!company && /(my order|order [a-z]?\d{3,}|return|refund|fit me|tracking|i bought)/i.test(text)) category = 'retail_customer';
  else if (/(sponsor|influencer|creator|ambassador|partnership|collab|free gear)/i.test(text)) category = 'sponsorship_or_partnership';
  else if (/(school|club|scouts?|students|camp)/i.test(`${company} ${text}`)) category = 'club_or_school';
  else if (/(staff|employees|logo|branded|conference|corporate|uniform)/i.test(text)) category = 'corporate_bulk';
  else if (!company) category = 'retail_customer';

  let priority = 'cold';
  const volume = VOLUME_RE.test(text);
  const dated = DATE_RE.test(text);
  if (volume && dated) priority = 'hot';
  else if (volume || /(quote|price list|pricing|catalogue|trade terms)/i.test(text)) priority = 'warm';
  return { category, priority: SALES_CATEGORIES.includes(category) ? priority : null };
}

const DRAFT_PROMISE_RE = /(\$\s?\d|\d+\s?%|\bdiscount|\bguarantee|\bwe (will|can) deliver by|\bin stock\b|\bconfirm(ed)? (stock|delivery))/i;

function templateDraft(lead, category) {
  const first = String(lead.name || 'there').split(' ')[0];
  const team = LEAD_OWNERS[category] || 'sales';
  return {
    subject: 'Thanks for getting in touch with Acme Outdoor Gear',
    body: `Hi ${first},\n\nThanks for your message. Someone from our ${team.toLowerCase()} team will reply within one business day with the details you asked for.\n\nNgā mihi,\nAcme Outdoor Gear`,
  };
}

/**
 * The model suggests; these rules decide. Returns the record written to the CRM and the approval queue.
 * ai: parsed model output or null. dup: { duplicate, matchedId, reason }.
 */
function decideLead(lead, ai, dup) {
  const flags = [];
  let source = 'ai';
  let category = ai ? oneOf(ai.category, LEAD_CATEGORIES, null) : null;
  let priority = ai ? oneOf(ai.priority, LEAD_PRIORITIES, null) : null;
  if (!category) {
    source = ai ? 'rules (model answer unusable)' : 'rules';
    const base = baselineLead(lead);
    category = base.category;
    priority = base.priority;
  }
  if (SALES_CATEGORIES.includes(category) && !priority) priority = baselineLead(lead).priority || 'warm';

  const spam = spamSignals(lead);
  if (spam.length && category !== 'spam') {
    flags.push(...spam);
    category = 'spam';
  }
  if (looksLikeInjection(lead.message)) {
    flags.push('instructions_in_message');
    if (priority === 'hot') priority = 'warm';
  }
  if (!SALES_CATEGORIES.includes(category)) priority = null;

  const route = category === 'spam' ? 'discard' : category === 'retail_customer' ? 'support' : 'sales_followup';
  let draft = null;
  if (route === 'sales_followup') {
    const aiDraft = ai && ai.follow_up_body ? { subject: String(ai.follow_up_subject || ''), body: String(ai.follow_up_body) } : null;
    draft = aiDraft || templateDraft(lead, category);
    if (!draft.subject) draft.subject = templateDraft(lead, category).subject;
    if (DRAFT_PROMISE_RE.test(`${draft.subject} ${draft.body}`)) flags.push('draft_mentions_price_or_promise');
  }
  return {
    category,
    priority,
    route,
    duplicate: Boolean(dup && dup.duplicate),
    matched_contact_id: dup ? dup.matchedId || null : null,
    owner: LEAD_OWNERS[category] || (route === 'support' ? 'Customer service' : null),
    summary: ai && ai.summary ? String(ai.summary).slice(0, 300) : '',
    decided_by: source,
    flags,
    needs_review: flags.length > 0,
    draft,
  };
}
