// Shared helpers for every workflow. The builder inlines this file into the Code nodes that need it, and the
// unit tests in tests/js load it the same way.

/** The webhook puts the payload in $json.body; the sample trigger passes it directly. */
function pickInput(json) {
  if (json && json.body && typeof json.body === 'object' && !Array.isArray(json.body)) return json.body;
  return json || {};
}

/** Reads the JSON object a chat-completions response carries. Returns null when there is none. */
function parseAiJson(response) {
  try {
    const content = response && response.choices && response.choices[0] && response.choices[0].message
      ? response.choices[0].message.content : null;
    if (typeof content !== 'string') return null;
    const cleaned = content.trim().replace(/^```(?:json)?\s*/i, '').replace(/```\s*$/, '');
    const start = cleaned.indexOf('{');
    const end = cleaned.lastIndexOf('}');
    if (start < 0 || end < start) return null;
    const parsed = JSON.parse(cleaned.slice(start, end + 1));
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch (err) {
    return null;
  }
}

function oneOf(value, allowed, fallback) {
  const v = typeof value === 'string' ? value.trim().toLowerCase() : value;
  return allowed.includes(v) ? v : fallback;
}

/** Text that tries to give the model orders is treated as data, and flagged for a person. */
const INJECTION_RE = /(ignore (all |any |your |the )?(previous |prior |above )?instructions|disregard (the |your )?(rules|instructions)|you are now|system prompt)/i;

function looksLikeInjection(text) {
  return INJECTION_RE.test(String(text || ''));
}

/** Numbers as written in text: "$1,234.50" -> 1234.5, "12.5%" -> 12.5, "3,000" -> 3000. */
function numbersIn(text) {
  const out = [];
  const re = /-?\d[\d,]*(?:\.\d+)?/g;
  let m;
  while ((m = re.exec(String(text || ''))) !== null) {
    const raw = m[0].replace(/,(?=\d{3}\b)/g, '');
    if (/,/.test(raw)) continue;
    const n = Number(raw);
    if (Number.isFinite(n)) out.push(n);
  }
  return out;
}

/** Builds an OpenAI-compatible chat request. Temperature 0 and JSON mode keep answers stable and parseable. */
function aiRequest(system, user, { model = 'gemini-flash-lite-latest', maxTokens = 700 } = {}) {
  return {
    model,
    temperature: 0,
    max_tokens: maxTokens,
    response_format: { type: 'json_object' },
    messages: [
      { role: 'system', content: system },
      { role: 'user', content: user },
    ],
  };
}

function round2(n) {
  return Math.round((Number(n) + Number.EPSILON) * 100) / 100;
}
