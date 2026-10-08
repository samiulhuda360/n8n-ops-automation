import test from 'node:test';
import assert from 'node:assert/strict';
import { load } from './load.mjs';

const { kpisFromRows, groundingCheck, templateSummary, chatMessage } = load('common', 'kpi');
const rows = [
  { order_date: '2026-09-10', channel: 'online', status: 'paid', product: 'Trailhead 45L pack', orders: 2, units: 2, revenue: 498 },
  { order_date: '2026-09-10', channel: 'store', status: 'paid', product: 'Kea daypack 22L', orders: 1, units: 1, revenue: 119 },
  { order_date: '2026-09-10', channel: 'online', status: 'refunded', product: 'Kea daypack 22L', orders: 1, units: 1, revenue: 119 },
  { order_date: '2026-09-03', channel: 'online', status: 'paid', product: 'Kea daypack 22L', orders: 5, units: 5, revenue: 1000 },
];

test('KPIs come from the grouped rows', () => {
  const k = kpisFromRows(rows, '2026-09-10');
  assert.equal(k.revenue, 617);
  assert.equal(k.orders, 3);
  assert.equal(k.refunds, 1);
  assert.equal(k.refund_rate_pct, 25);
  assert.equal(k.change_vs_week_before_pct, -38.3);
  assert.equal(k.top_product, 'Trailhead 45L pack');
  assert.deepEqual(k.alerts, ['revenue_drop', 'refund_spike']);
});

test('the template summary passes its own number check', () => {
  const k = kpisFromRows(rows, '2026-09-10');
  const lines = templateSummary(k);
  assert.equal(lines.length, 5);
  assert.equal(groundingCheck(lines, k).ok, true);
  assert.match(chatMessage(k, lines, 'template').text, /needs a look/);
});

test('an invented number fails the check', () => {
  const k = kpisFromRows(rows, '2026-09-10');
  const lines = templateSummary(k);
  lines[1] = 'Average order $777.77.';
  const r = groundingCheck(lines, k);
  assert.equal(r.ok, false);
  assert.deepEqual(r.ungrounded, [777.77]);
});

test('rounded money is accepted, a wrong line count is not', () => {
  const k = kpisFromRows(rows, '2026-09-10');
  assert.equal(groundingCheck(['Revenue $617 from 3 orders.', 'a', 'b', 'c', 'No alerts today.'], k).ok, true);
  assert.deepEqual(groundingCheck(['Revenue $617.'], k).problems, ['not_five_lines']);
});
