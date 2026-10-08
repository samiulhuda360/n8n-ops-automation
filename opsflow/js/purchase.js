// Purchase approvals: the spending policy as code. The model only reads the free-text description.
// Needs common.js.

const PURCHASE_CATEGORIES = ['stock', 'packaging_and_freight', 'marketing', 'travel', 'software',
  'office_and_equipment', 'restricted'];

function restrictedKeyword(description, policy) {
  const text = String(description || '').toLowerCase();
  return (policy.restricted_keywords || []).find((k) => text.includes(k.toLowerCase())) || null;
}

/** The baseline category without a model. */
function baselineCategory(description, policy) {
  const t = String(description || '').toLowerCase();
  if (restrictedKeyword(t, policy)) return 'restricted';
  if (/(freight|courier|shipping|pallet|packaging)/.test(t)) return 'packaging_and_freight';
  if (/(flight|hotel|travel|trip|accommodation|taxi)/.test(t)) return 'travel';
  if (/(licen[cs]e|software|app\b|seat|subscription|saas)/.test(t)) return 'software';
  if (/(poster|flyer|decal|print|banner|advert|business cards|marketing)/.test(t)) return 'marketing';
  if (/(restock|stock of|for resale|units of)/.test(t)) return 'stock';
  return 'office_and_equipment';
}

function daysBetween(a, b) {
  return Math.round((new Date(`${b}T00:00:00Z`) - new Date(`${a}T00:00:00Z`)) / 86400000);
}

/**
 * Applies the policy in order. Returns the route, the approver and every rule that fired, for the audit log.
 * history: earlier approved requests from the purchasing system.
 */
function decideRoute(req, policy, history, category) {
  const rules = [];
  const amount = Number(req.amount_nzd);
  const autoMax = policy.auto_approve_max;
  const managerMax = policy.manager_max;
  const knownSupplier = (policy.approved_suppliers || []).some((s) => s.toLowerCase() === String(req.supplier || '').toLowerCase());
  const keyword = restrictedKeyword(req.description, policy);
  const recent = (history || []).filter((h) => h.requester.toLowerCase() === String(req.requester).toLowerCase()
    && h.supplier.toLowerCase() === String(req.supplier).toLowerCase()
    && daysBetween(h.date, req.date) >= 0 && daysBetween(h.date, req.date) <= policy.split_window_days);
  const recentTotal = recent.reduce((a, h) => a + Number(h.amount_nzd), 0);

  let route;
  if (!(policy.budget_codes || []).includes(req.budget_code)) {
    route = 'return_to_requester';
    rules.push('R1 budget code missing or not valid');
  } else if (category === 'restricted' || keyword) {
    route = 'finance_review';
    rules.push(keyword ? `R2 restricted spend (keyword "${keyword}")` : 'R2 restricted spend (description)');
  } else if (amount > managerMax) {
    route = 'director';
    rules.push(`R3 over $${managerMax.toLocaleString('en-NZ')}`);
  } else if (amount > autoMax) {
    route = 'manager';
    rules.push(`R4 over $${autoMax}`);
  } else if (!knownSupplier) {
    route = 'manager';
    rules.push('R5 supplier not on the approved list');
  } else if (recent.length && recentTotal + amount > autoMax) {
    route = 'manager';
    rules.push(`R6 possible split purchase ($${recentTotal + amount} with the same supplier in ${policy.split_window_days} days)`);
  } else {
    route = 'auto_approve';
    rules.push(`R0 within policy (up to $${autoMax}, approved supplier, valid budget code)`);
  }
  if (route !== 'return_to_requester' && !knownSupplier && !rules.some((r) => r.startsWith('R5'))) {
    rules.push('R5 supplier not on the approved list');
  }

  let approver = null;
  if (route === 'manager') approver = (policy.managers || {})[req.department] || policy.director;
  if (route === 'director') approver = policy.director;
  if (route === 'finance_review') approver = policy.finance;
  if (route === 'return_to_requester') approver = req.requester;
  if (route === 'manager' && approver && approver.toLowerCase() === String(req.requester).toLowerCase()) {
    route = 'director';
    approver = policy.director;
    rules.push('R7 requester cannot approve their own request');
  }
  return { route, approver, rules, supplier_approved: knownSupplier };
}
