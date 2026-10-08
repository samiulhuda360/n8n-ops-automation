// Supplier invoices: a generic regex baseline, normalising the model's extraction, and the validation rules.
// Needs common.js.

const INVOICE_FIELDS = ['supplier_name', 'gst_number', 'invoice_number', 'invoice_date', 'due_date', 'po_number',
  'currency', 'subtotal', 'gst', 'total'];
const NZ_GST_RATE = 0.15;
const MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];

/** "1,234.50", "$1,234.50", 1234.5 -> 1234.5; anything else -> null. */
function toAmount(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? round2(value) : null;
  if (typeof value !== 'string') return null;
  const cleaned = value.replace(/[^0-9.-]/g, '');
  if (!cleaned) return null;
  const n = Number(cleaned);
  return Number.isFinite(n) ? round2(n) : null;
}

/** "2026-09-03", "03/09/2026" (NZ day-first), "3 September 2026", "Sep 3, 2026" -> "2026-09-03". */
function toIsoDate(value) {
  if (!value || typeof value !== 'string') return null;
  const s = value.trim();
  let m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (m) return `${m[1]}-${m[2].padStart(2, '0')}-${m[3].padStart(2, '0')}`;
  m = s.match(/^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$/);
  if (m) return `${m[3]}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}`;
  m = s.match(/^(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)\.?,?\s+(\d{4})$/i);
  if (m && MONTHS.includes(m[2].slice(0, 3).toLowerCase())) {
    return `${m[3]}-${String(MONTHS.indexOf(m[2].slice(0, 3).toLowerCase()) + 1).padStart(2, '0')}-${m[1].padStart(2, '0')}`;
  }
  m = s.match(/^([a-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})$/i);
  if (m && MONTHS.includes(m[1].slice(0, 3).toLowerCase())) {
    return `${m[3]}-${String(MONTHS.indexOf(m[1].slice(0, 3).toLowerCase()) + 1).padStart(2, '0')}-${m[2].padStart(2, '0')}`;
  }
  return null;
}

function cleanText(v) {
  if (v === null || v === undefined) return null;
  const s = String(v).trim();
  return s && !/^(null|none|n\/a|-)$/i.test(s) ? s : null;
}

/** Coerces whatever the model returned into the invoice schema; unknown values become null. */
function normaliseInvoice(raw) {
  const r = raw || {};
  const lines = Array.isArray(r.lines) ? r.lines.map((l) => ({
    description: cleanText(l && l.description) || '',
    quantity: toAmount(l && l.quantity),
    unit_price: toAmount(l && l.unit_price),
    amount: toAmount(l && l.amount),
  })) : [];
  const currency = (cleanText(r.currency) || 'NZD').toUpperCase().slice(0, 3);
  return {
    supplier_name: cleanText(r.supplier_name),
    gst_number: cleanText(r.gst_number),
    invoice_number: cleanText(r.invoice_number),
    invoice_date: toIsoDate(cleanText(r.invoice_date)),
    due_date: toIsoDate(cleanText(r.due_date)),
    po_number: cleanText(r.po_number),
    currency,
    lines,
    subtotal: toAmount(r.subtotal),
    gst: toAmount(r.gst),
    total: toAmount(r.total),
  };
}

/**
 * The baseline without a model: generic label patterns of the kind you'd write before seeing any supplier's
 * layout ("Invoice number", "Invoice date", "Due date", "Subtotal", "GST", "Total").
 */
function regexExtract(text) {
  const t = String(text || '');
  const grab = (re) => { const m = t.match(re); return m ? m[1].trim() : null; };
  const firstLine = t.split(/\n/).map((l) => l.trim()).find((l) => l.length > 2) || null;
  return normaliseInvoice({
    supplier_name: firstLine ? firstLine.split('|')[0].trim() : null,
    gst_number: grab(/GST\s*(?:number|no\.?|#)?\s*:?\s*(\d{2,3}-\d{3}-\d{3})/i),
    invoice_number: grab(/Invoice\s*(?:number|no\.?|#)\s*:?\s*([A-Z0-9][A-Z0-9/-]+)/i),
    invoice_date: grab(/Invoice\s+date\s*:?\s*([0-9/.-]{8,10})/i),
    due_date: grab(/Due\s+date\s*:?\s*([0-9/.-]{8,10})/i),
    po_number: grab(/\b(PO-\d{4}-\d{3,5})\b/),
    currency: grab(/\b(NZD|AUD|USD)\b/) || 'NZD',
    subtotal: grab(/Subtotal\s*:?\s*\$?\s*([\d,]+\.\d{2})/i),
    gst: grab(/GST(?:\s*15%)?\s*:?\s*\$?\s*([\d,]+\.\d{2})/i),
    total: grab(/\bTotal(?:\s+[A-Z]{3})?\s*:?\s*\$?\s*([\d,]+\.\d{2})/),
  });
}

function supplierKey(name) {
  return String(name || '').toLowerCase().replace(/\blimited\b/g, 'ltd').replace(/[^a-z0-9]/g, '');
}

function amountInText(amount, text) {
  if (amount === null || amount === undefined) return false;
  const plain = Number(amount).toFixed(2);
  const withCommas = Number(amount).toLocaleString('en-NZ', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return text.includes(plain) || text.includes(withCommas);
}

/**
 * Validation rules for a draft bill. ctx: { suppliers, existingBills, po, pdfText }.
 * Returns { route, reasons, supplier }.
 */
function checkInvoice(inv, ctx) {
  const reasons = [];
  const text = String(ctx.pdfText || '');
  for (const f of ['supplier_name', 'invoice_number', 'invoice_date', 'subtotal', 'gst', 'total']) {
    if (inv[f] === null || inv[f] === undefined || inv[f] === '') reasons.push(`missing_field:${f}`);
  }
  const suppliers = ctx.suppliers || [];
  const supplier = suppliers.find((s) => supplierKey(s.name) === supplierKey(inv.supplier_name))
    || suppliers.find((s) => s.gst_number && inv.gst_number && s.gst_number === inv.gst_number) || null;
  if (!supplier) reasons.push('unknown_supplier');

  const overseas = supplier ? supplier.country !== 'NZ' : inv.currency !== 'NZD';
  if (inv.subtotal !== null && inv.gst !== null) {
    const expected = overseas ? 0 : round2(inv.subtotal * NZ_GST_RATE);
    if (Math.abs(inv.gst - expected) > 0.05) reasons.push('gst_mismatch');
  }
  if (inv.subtotal !== null && inv.gst !== null && inv.total !== null
      && Math.abs(round2(inv.subtotal + inv.gst) - inv.total) > 0.02) reasons.push('total_mismatch');
  const lineAmounts = (inv.lines || []).map((l) => l.amount).filter((a) => a !== null);
  if (lineAmounts.length && inv.subtotal !== null
      && Math.abs(round2(lineAmounts.reduce((a, b) => a + b, 0)) - inv.subtotal) > 0.02) reasons.push('lines_mismatch');

  const dup = (ctx.existingBills || []).find((b) => (!supplier || b.supplier_id === supplier.supplier_id)
    && String(b.invoice_number).toLowerCase() === String(inv.invoice_number || '').toLowerCase());
  if (dup) reasons.push('duplicate_invoice');

  if (inv.po_number) {
    if (!ctx.po) reasons.push('po_not_found');
    else if (inv.subtotal !== null && Math.abs(inv.subtotal - ctx.po.amount_excl_gst) / ctx.po.amount_excl_gst > 0.05) {
      reasons.push('po_mismatch');
    }
  }
  if (inv.invoice_date && inv.due_date && inv.due_date < inv.invoice_date) reasons.push('due_before_invoice_date');

  // Grounding: every amount and the invoice number must appear in the PDF text, so nothing invented gets billed.
  if (text) {
    for (const f of ['subtotal', 'gst', 'total']) {
      if (inv[f] !== null && !(inv[f] === 0 && overseas) && !amountInText(inv[f], text)) reasons.push(`not_in_pdf:${f}`);
    }
    if (inv.invoice_number && !text.includes(inv.invoice_number)) reasons.push('not_in_pdf:invoice_number');
  }
  return { route: reasons.length ? 'exception' : 'draft_bill', reasons, supplier };
}
