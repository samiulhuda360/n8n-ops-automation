// Content repurposing: channel rules, a claims check, number grounding and the template baseline.
// Needs common.js.

const CONTENT_CHANNELS = {
  linkedin: { maxChars: 3000, link: 'required', maxHashtags: 5 },
  instagram: { maxChars: 2200, link: 'forbidden', maxHashtags: 8 },
  x: { maxChars: 280, link: 'required', maxHashtags: 2 },
};

/** Absolute advertising claims that need evidence before anyone repeats them (NZ Fair Trading Act territory). */
const CLAIM_RE = /(guarantee[ds]?|\b100\s?%|\bbest\b|(clinically|scientifically) proven|(completely|totally|100%) safe|\bsafest\b|world'?s (first|best|lightest|strongest)|number one|\bunbeatable\b|\bfor life\b|\bever made\b|than any other)/gi;
const URL_RE = /https?:\/\/\S+/gi;

function claimsIn(text) {
  return [...new Set((String(text || '').match(CLAIM_RE) || []).map((c) => c.toLowerCase()))];
}

/** X counts every link as 23 characters. */
function postLength(channel, text) {
  const t = String(text || '');
  if (channel !== 'x') return t.length;
  return t.replace(URL_RE, 'x'.repeat(23)).length;
}

function checkPost(channel, text, blog) {
  const rules = CONTENT_CHANNELS[channel];
  const t = String(text || '');
  const flags = [];
  const checks = {};
  checks.length = t.trim().length > 0 && postLength(channel, t) <= rules.maxChars;
  if (!checks.length) flags.push(t.trim() ? `too_long:${postLength(channel, t)}/${rules.maxChars}` : 'empty');
  const hasLink = t.includes(blog.url);
  const anyLink = URL_RE.test(t);
  URL_RE.lastIndex = 0;
  checks.link = rules.link === 'required' ? hasLink : !anyLink;
  if (!checks.link) flags.push(rules.link === 'required' ? 'missing_blog_link' : 'link_not_allowed');
  const tags = (t.match(/#[\p{L}\p{N}_]+/gu) || []).length;
  checks.hashtags = tags <= rules.maxHashtags;
  if (!checks.hashtags) flags.push(`too_many_hashtags:${tags}`);

  // Every number in the post must come from the blog post: no invented prices, dates or discounts.
  const sourceNumbers = new Set(numbersIn(`${blog.title} ${blog.body}`).map((n) => Math.abs(n)));
  const postNumbers = numbersIn(t.replace(URL_RE, ' ').replace(/#[\p{L}\p{N}_]+/gu, ' ')).map((n) => Math.abs(n));
  const invented = postNumbers.filter((n) => !sourceNumbers.has(n));
  checks.numbers_grounded = invented.length === 0;
  if (invented.length) flags.push(`numbers_not_in_blog:${[...new Set(invented)].join(',')}`);

  const claims = claimsIn(t);
  checks.no_risky_claims = claims.length === 0;
  if (claims.length) flags.push(`risky_claim:${claims.join(',')}`);
  return { checks, flags, ok: flags.length === 0 };
}

function firstSentences(body, n) {
  // Split after sentence punctuation followed by a space, so "19.4 km" stays whole.
  return String(body || '').split(/(?<=[.!?])\s+/).slice(0, n).join(' ').trim();
}

/** The baseline without a model: title, opening sentences and the link, trimmed to each channel. */
function templatePosts(blog) {
  const tags = '#AcmeOutdoorGear #NZOutdoors';
  let x = `${blog.title} ${blog.url}`;
  if (postLength('x', x) > 280) x = `${blog.title.slice(0, 280 - 25)}… ${blog.url}`;
  return {
    linkedin: `${blog.title}\n\n${firstSentences(blog.body, 2)}\n\nRead more: ${blog.url}\n\n${tags}`,
    instagram: `${blog.title}\n\n${firstSentences(blog.body, 2)}\n\nLink in bio.\n\n${tags} #Tramping`,
    x,
  };
}
