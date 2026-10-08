import test from 'node:test';
import assert from 'node:assert/strict';
import { load } from './load.mjs';

const { toIsoDate, toAmount, normaliseInvoice, regexExtract, checkInvoice } = load('common', 'invoice');
const suppliers = [
  { supplier_id: 'SUP-01', name: 'Southern Alps Textiles Ltd', gst_number: '112-345-678', country: 'NZ' },
  { supplier_id: 'SUP-06', name: 'Bluegum Outdoor Pty Ltd', gst_number: '', country: 'AU' },
];
const text = 'Southern Alps Textiles Ltd\nInvoice number: SAT-1\nSubtotal 1,000.00\nGST 15% 150.00\nTotal NZD 1,150.00';
const good = normaliseInvoice({
  supplier_name: 'Southern Alps Textiles Limited', invoice_number: 'SAT-1', invoice_date: '02/09/2026', currency: 'NZD',
  lines: [{ description: 'x', quantity: 1, unit_price: 1000, amount: '1,000.00' }], subtotal: '1,000.00', gst: 150, total: 1150,
});

test('dates and amounts normalise', () => {
  assert.equal(toIsoDate('02/09/2026'), '2026-09-02');
  assert.equal(toIsoDate('3 September 2026'), '2026-09-03');
  assert.equal(toAmount('$1,234.50'), 1234.5);
  assert.equal(toAmount('n/a'), null);
});

test('a clean invoice becomes a draft bill', () => {
  const r = checkInvoice(good, { suppliers, existingBills: [], po: null, pdfText: text });
  assert.deepEqual(r.reasons, []);
  assert.equal(r.route, 'draft_bill');
  assert.equal(r.supplier.supplier_id, 'SUP-01');
});

test('wrong GST, wrong total and duplicates are exceptions', () => {
  const r = checkInvoice({ ...good, gst: 100, total: 1300 },
    { suppliers, existingBills: [{ supplier_id: 'SUP-01', invoice_number: 'sat-1' }], po: null, pdfText: '' });
  assert.ok(r.reasons.includes('gst_mismatch'));
  assert.ok(r.reasons.includes('total_mismatch'));
  assert.ok(r.reasons.includes('duplicate_invoice'));
  assert.equal(r.route, 'exception');
});

test('overseas suppliers must charge no GST', () => {
  const inv = { ...good, supplier_name: 'Bluegum Outdoor Pty Ltd', currency: 'AUD', gst: 0, total: 1000 };
  assert.deepEqual(checkInvoice(inv, { suppliers, pdfText: '' }).reasons, []);
});

test('amounts that are not in the PDF text are rejected', () => {
  const r = checkInvoice(good, { suppliers, pdfText: 'Invoice number: SAT-1 Total 999.00' });
  assert.ok(r.reasons.includes('not_in_pdf:total'));
});

test('PO amounts more than 5% apart are flagged', () => {
  const r = checkInvoice({ ...good, po_number: 'PO-1' }, { suppliers, po: { amount_excl_gst: 800 }, pdfText: text });
  assert.ok(r.reasons.includes('po_mismatch'));
});

test('the regex baseline reads the common labels', () => {
  const r = regexExtract('Acme Supplier Ltd\nInvoice number: AB-12\nInvoice date: 03/09/2026\nSubtotal 100.00\nGST 15% 15.00\nTotal 115.00');
  assert.equal(r.invoice_number, 'AB-12');
  assert.equal(r.invoice_date, '2026-09-03');
  assert.equal(r.total, 115);
});
