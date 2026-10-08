import test from 'node:test';
import assert from 'node:assert/strict';
import { load } from './load.mjs';

const { checkPost, claimsIn, postLength, templatePosts } = load('common', 'content');
const blog = {
  title: 'Meet the Kea tent',
  url: 'https://acmeoutdoorgear.example.com/blog/kea',
  body: 'The Kea weighs 1.9 kg and costs $449. It is guaranteed to keep you dry.',
};

test('claims are found in the source', () => {
  assert.deepEqual(claimsIn(blog.body), ['guaranteed']);
});

test('X counts a link as 23 characters', () => {
  assert.equal(postLength('x', `Hi ${blog.url}`), 3 + 23);
});

test('invented numbers, missing links and claims are flagged', () => {
  const r = checkPost('linkedin', 'The Kea is now $399 and guaranteed dry.', blog);
  assert.equal(r.ok, false);
  assert.equal(r.checks.numbers_grounded, false);
  assert.equal(r.checks.link, false);
  assert.equal(r.checks.no_risky_claims, false);
});

test('instagram posts must not carry links', () => {
  assert.equal(checkPost('instagram', `Kea tent ${blog.url}`, blog).checks.link, false);
  assert.equal(checkPost('instagram', 'Kea tent, 1.9 kg. Link in bio. #Tramping', blog).ok, true);
});

test('template posts keep decimals whole and respect the X length', () => {
  const posts = templatePosts({ ...blog, body: 'It is 19.4 km long. Bring water.' });
  assert.match(posts.linkedin, /19\.4 km/);
  assert.ok(postLength('x', posts.x) <= 280);
});
