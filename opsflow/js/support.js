// Support triage: safety and legal guard words, a keyword baseline and the final routing decision.
// Needs common.js.

const TICKET_CATEGORIES = ['order_status', 'return_or_exchange', 'product_question', 'warranty_or_fault',
  'wholesale_enquiry', 'complaint', 'feedback', 'spam'];
const TICKET_PRIORITIES = ['urgent', 'high', 'normal', 'low'];
const PERSON_CATEGORIES = ['complaint', 'warranty_or_fault', 'wholesale_enquiry'];

/** Safety wording: any of these sends the email to a person as urgent, whatever the model said. */
const SAFETY_RE = /(injur|\bhurt\b|\bburn(s|ed|t)?\b|\bfire\b|flames?|smoke|gas leak|leak(ed|ing)? gas|carbon monoxide|explod|overheat|electric shock|\bcrack(ed|s)?\b|chok(e|ed|ing)|allerg|\brash\b|hospital|\bunsafe\b|danger)/i;
/** Legal or regulator wording (New Zealand consumer law). */
const LEGAL_RE = /(lawyer|solicitor|legal action|\bsue\b|disputes tribunal|small claims|commerce commission|consumer guarantees act|fair trading act|\bcourt\b)/i;
const DRAFT_PROMISE_RE = /(refund (is |has been )?approved|we will refund|we'll refund|full refund|will replace|replacement (is|has been) (sent|on)|guarantee|compensat)/i;

function baselineTicket(email) {
  const text = `${email.subject || ''} ${email.text || ''}`;
  let category = 'product_question';
  if (/(book a demo|limited (time )?offer|click (here|to buy|now)|boost (your )?(store )?sales|unsubscribe|\bseo\b)/i.test(text)) category = 'spam';
  else if (/(stock your|stockist|wholesale|trade pric|price list|minimum order)/i.test(text)) category = 'wholesale_enquiry';
  else if (/(third time|emailed twice|nobody (has )?repl|disappointed|poor service|unacceptable)/i.test(text) || LEGAL_RE.test(text)) category = 'complaint';
  else if (/(broke|broken|snapped|faulty|\bfault\b|warranty|crack|leak|delaminat)/i.test(text)) category = 'warranty_or_fault';
  else if (/(return|swap|exchange|store credit|wrong size)/i.test(text)) category = 'return_or_exchange';
  else if (/(order [a-z]?\d{3,}|tracking|deliver|shipped|where is my)/i.test(text)) category = 'order_status';
  else if (/(thank|brilliant|great service|awesome|loved)/i.test(text)) category = 'feedback';

  let priority = 'normal';
  if (SAFETY_RE.test(text) || LEGAL_RE.test(text)) priority = 'urgent';
  else if (['spam', 'feedback'].includes(category)) priority = 'low';
  else if (PERSON_CATEGORIES.includes(category)) priority = 'high';
  return { category, priority };
}

/** The model suggests; these rules decide. */
function decideTicket(email, ai) {
  const text = `${email.subject || ''} ${email.text || ''}`;
  const guardHits = [];
  let decidedBy = 'ai';
  let category = ai ? oneOf(ai.category, TICKET_CATEGORIES, null) : null;
  let priority = ai ? oneOf(ai.priority, TICKET_PRIORITIES, null) : null;
  let draft = ai && typeof ai.reply_draft === 'string' ? ai.reply_draft : '';
  if (!category || !priority) {
    decidedBy = ai ? 'rules (model answer unusable)' : 'rules';
    const base = baselineTicket(email);
    category = category || base.category;
    priority = priority || base.priority;
  }
  let needsPerson = (ai && ai.needs_person === true) || PERSON_CATEGORIES.includes(category);

  if (SAFETY_RE.test(text)) {
    guardHits.push('safety_wording');
    priority = 'urgent';
    needsPerson = true;
  }
  if (LEGAL_RE.test(text)) {
    guardHits.push('legal_wording');
    priority = 'urgent';
    needsPerson = true;
  }
  if (looksLikeInjection(text)) {
    guardHits.push('instructions_in_email');
    needsPerson = true;
  }
  if (DRAFT_PROMISE_RE.test(draft)) {
    guardHits.push('draft_makes_promise');
    needsPerson = true;
  }
  if (priority === 'urgent') needsPerson = true;
  if (category === 'spam') {
    draft = '';
    if (!guardHits.length) needsPerson = false;
  }
  if (!draft && category !== 'spam') {
    const first = String(email.from || '').split('@')[0].split('.')[0];
    draft = `Kia ora ${first ? first[0].toUpperCase() + first.slice(1) : 'there'},\n\nThanks for getting in touch. We've received your message and a member of our team will come back to you within one business day.\n\nNgā mihi,\nAcme Outdoor Gear`;
  }
  const queue = needsPerson
    ? (priority === 'urgent' ? 'escalations' : category === 'wholesale_enquiry' ? 'trade sales' : 'senior support')
    : (category === 'spam' ? 'closed' : 'reply drafts');
  return {
    category,
    priority,
    needs_person: needsPerson,
    queue,
    status: needsPerson ? 'waiting for a person' : category === 'spam' ? 'closed as spam' : 'draft ready for review',
    reason: ai && ai.reason ? String(ai.reason).slice(0, 300) : '',
    reply_draft: draft,
    guard_hits: guardHits,
    decided_by: decidedBy,
  };
}
