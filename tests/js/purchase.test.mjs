import test from 'node:test';
import assert from 'node:assert/strict';
import { load } from './load.mjs';

const { decideRoute, baselineCategory } = load('common', 'purchase');
const policy = {
  auto_approve_max: 500, manager_max: 5000, split_window_days: 14,
  budget_codes: ['OPS-2026'], approved_suppliers: ['Known Ltd'], restricted_keywords: ['voucher', 'wine'],
  managers: { Operations: 'Luke Bennett' }, director: 'Sarah Mitchell', finance: 'Simon Porter',
};
const req = (extra) => ({
  requester: 'Owen Parata', department: 'Operations', supplier: 'Known Ltd', amount_nzd: 100, budget_code: 'OPS-2026',
  description: 'pens', date: '2026-10-05', ...extra,
});

test('small in-policy spend is auto-approved', () => {
  assert.equal(decideRoute(req({}), policy, [], 'office_and_equipment').route, 'auto_approve');
});

test('the policy order: budget code, restricted, director, manager', () => {
  assert.equal(decideRoute(req({ budget_code: '' }), policy, [], 'stock').route, 'return_to_requester');
  assert.equal(decideRoute(req({ description: 'gift vouchers' }), policy, [], 'office_and_equipment').route, 'finance_review');
  assert.equal(decideRoute(req({}), policy, [], 'restricted').route, 'finance_review');
  assert.equal(decideRoute(req({ amount_nzd: 9000 }), policy, [], 'stock').route, 'director');
  assert.equal(decideRoute(req({ amount_nzd: 900 }), policy, [], 'stock').route, 'manager');
  assert.equal(decideRoute(req({ supplier: 'New Co' }), policy, [], 'stock').route, 'manager');
});

test('splitting a purchase to stay under the limit goes to a manager', () => {
  const history = [{ requester: 'Owen Parata', supplier: 'Known Ltd', amount_nzd: 450, date: '2026-09-28' }];
  const r = decideRoute(req({}), policy, history, 'stock');
  assert.equal(r.route, 'manager');
  assert.ok(r.rules.some((x) => x.startsWith('R6')));
});

test('nobody approves their own request', () => {
  const r = decideRoute(req({ requester: 'Luke Bennett', amount_nzd: 900 }), policy, [], 'stock');
  assert.equal(r.route, 'director');
  assert.equal(r.approver, 'Sarah Mitchell');
});

test('baseline categories', () => {
  assert.equal(baselineCategory('Courier for an order', policy), 'packaging_and_freight');
  assert.equal(baselineCategory('a bottle of wine', policy), 'restricted');
});
