import test from 'node:test';
import assert from 'node:assert/strict';
import { load } from './load.mjs';

const { decideTicket, baselineTicket } = load('common', 'support');
const email = (text, subject = 'Hello') => ({ from: 'jo.smith@example.com', subject, text });

test('safety wording is urgent and goes to a person even if the model says otherwise', () => {
  const d = decideTicket(email('The stove leaked gas and caught fire'),
    { category: 'product_question', priority: 'low', needs_person: false, reply_draft: 'Thanks!' });
  assert.equal(d.priority, 'urgent');
  assert.equal(d.needs_person, true);
  assert.ok(d.guard_hits.includes('safety_wording'));
  assert.equal(d.queue, 'escalations');
});

test('legal wording is urgent', () => {
  const d = decideTicket(email('I am filing with the Disputes Tribunal'), null);
  assert.equal(d.priority, 'urgent');
  assert.ok(d.guard_hits.includes('legal_wording'));
});

test('a draft that promises a refund goes to a person', () => {
  const d = decideTicket(email('Can I return this?'),
    { category: 'return_or_exchange', priority: 'normal', needs_person: false, reply_draft: 'Your refund is approved.' });
  assert.equal(d.needs_person, true);
  assert.ok(d.guard_hits.includes('draft_makes_promise'));
});

test('routine questions get a draft for review', () => {
  const d = decideTicket(email('Is the Kea tent good for wind?'),
    { category: 'product_question', priority: 'normal', needs_person: false, reply_draft: 'Yes, it is.' });
  assert.equal(d.needs_person, false);
  assert.equal(d.status, 'draft ready for review');
});

test('spam is closed with no draft', () => {
  const d = decideTicket(email('Book a demo today, limited offer'), null);
  assert.equal(d.category, 'spam');
  assert.equal(d.reply_draft, '');
  assert.equal(baselineTicket(email('Book a demo')).priority, 'low');
});
