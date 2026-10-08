// KPI digest: turns the SQL result into KPIs, checks every number the model writes, and formats the message.
// Needs common.js.

const KPI_CHANNELS = ['online', 'store', 'wholesale'];
const KPI_SQL = `SELECT order_date, channel, status, product,
       COUNT(*) AS orders, SUM(qty) AS units, ROUND(SUM(total_nzd), 2) AS revenue
FROM orders
WHERE order_date IN (?, ?)
GROUP BY order_date, channel, status, product
ORDER BY order_date, channel, status, product`;

function shiftDate(iso, days) {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** rows: grouped SQL rows for the report date and the same weekday a week before. */
function kpisFromRows(rows, reportDate) {
  const prevDate = shiftDate(reportDate, -7);
  const day = rows.filter((r) => r.order_date === reportDate);
  const prev = rows.filter((r) => r.order_date === prevDate);
  const paid = day.filter((r) => r.status === 'paid');
  const sum = (list, key) => list.reduce((a, r) => a + Number(r[key] || 0), 0);
  const revenue = round2(sum(paid, 'revenue'));
  const orders = sum(paid, 'orders');
  const refunds = sum(day.filter((r) => r.status === 'refunded'), 'orders');
  const allOrders = sum(day, 'orders');
  const byChannel = {};
  const ordersByChannel = {};
  for (const c of KPI_CHANNELS) {
    byChannel[c] = round2(sum(paid.filter((r) => r.channel === c), 'revenue'));
    ordersByChannel[c] = sum(paid.filter((r) => r.channel === c), 'orders');
  }
  const perProduct = {};
  for (const r of paid) perProduct[r.product] = (perProduct[r.product] || 0) + Number(r.revenue);
  const top = Object.entries(perProduct)
    .map(([p, v]) => [p, round2(v)])
    .sort((a, b) => (b[1] - a[1]) || a[0].localeCompare(b[0]))[0] || null;
  const prevRevenue = round2(sum(prev.filter((r) => r.status === 'paid'), 'revenue'));
  const change = prevRevenue ? Math.round(1000 * (revenue - prevRevenue) / prevRevenue) / 10 : null;
  const refundRate = allOrders ? Math.round(1000 * refunds / allOrders) / 10 : 0;
  const alerts = [];
  if (change !== null && change <= -20) alerts.push('revenue_drop');
  if (refundRate > 5) alerts.push('refund_spike');
  for (const c of ['online', 'store']) if (ordersByChannel[c] === 0) alerts.push(`${c}_zero`);
  return {
    report_date: reportDate,
    revenue,
    orders,
    aov: orders ? round2(revenue / orders) : 0,
    units: sum(paid, 'units'),
    refunds,
    refund_rate_pct: refundRate,
    revenue_by_channel: byChannel,
    orders_by_channel: ordersByChannel,
    wholesale_share_pct: revenue ? Math.round(1000 * byChannel.wholesale / revenue) / 10 : 0,
    revenue_week_before: prevRevenue,
    change_vs_week_before_pct: change,
    top_product: top ? top[0] : null,
    top_product_revenue: top ? top[1] : 0,
    alerts,
  };
}

/** Every number a summary may use, in the forms people write them (exact, 1 dp, whole, thousands). */
function allowedNumbers(k) {
  const base = [k.revenue, k.orders, k.aov, k.units, k.refunds, k.refund_rate_pct, k.wholesale_share_pct,
    k.revenue_week_before, k.top_product_revenue, ...Object.values(k.revenue_by_channel),
    ...Object.values(k.orders_by_channel)];
  if (k.change_vs_week_before_pct !== null) base.push(k.change_vs_week_before_pct, Math.abs(k.change_vs_week_before_pct));
  const out = new Set();
  for (const v of base) {
    out.add(round2(v));
    out.add(Math.round(v * 10) / 10);
    out.add(Math.round(v));
    if (Math.abs(v) >= 1000) {
      out.add(Math.round(v / 100) / 10); // 9.7 for "$9.7k"
      out.add(Math.round(v / 1000));
    }
  }
  const [y, m, d] = k.report_date.split('-').map(Number);
  const [py, pm, pd] = shiftDate(k.report_date, -7).split('-').map(Number);
  // dates, the alert thresholds (20% drop, 5% refunds) and numbers inside the top product's name
  [y, m, d, py, pm, pd, 7, 20, 5, ...numbersIn(k.top_product || '')].forEach((n) => out.add(Math.abs(n)));
  return out;
}

/** Checks a summary: exactly five lines, and every number in it traceable to the query result. */
function groundingCheck(lines, k) {
  const problems = [];
  if (!Array.isArray(lines) || lines.length !== 5) problems.push('not_five_lines');
  const allowed = allowedNumbers(k);
  const ungrounded = [];
  for (const line of Array.isArray(lines) ? lines : []) {
    for (const n of numbersIn(line)) {
      const ok = [...allowed].some((a) => Math.abs(Math.abs(a) - Math.abs(n)) < 0.051 * (Number.isInteger(n) ? 0.2 : 1));
      if (!ok) ungrounded.push(n);
    }
    if (String(line).length > 160) problems.push('line_too_long');
  }
  if (ungrounded.length) problems.push('ungrounded_numbers');
  return { ok: problems.length === 0, problems, ungrounded };
}

const money = (n) => `$${Number(n).toLocaleString('en-NZ', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/** The deterministic summary: used without a model, and whenever the model's text fails the check. */
function templateSummary(k) {
  const change = k.change_vs_week_before_pct;
  const trend = change === null ? 'no comparison available' : `${change >= 0 ? 'up' : 'down'} ${Math.abs(change)}% on the same day last week (${money(k.revenue_week_before)})`;
  const alertText = {
    revenue_drop: 'revenue down 20% or more on last week',
    refund_spike: `refund rate ${k.refund_rate_pct}% is above 5%`,
    online_zero: 'no online orders',
    store_zero: 'no store orders',
  };
  return [
    `Revenue ${money(k.revenue)} from ${k.orders} orders, ${trend}.`,
    `Average order ${money(k.aov)}; ${k.units} units sold.`,
    `Online ${money(k.revenue_by_channel.online)}, store ${money(k.revenue_by_channel.store)}, wholesale ${money(k.revenue_by_channel.wholesale)} (${k.wholesale_share_pct}% of revenue).`,
    `Top product: ${k.top_product || 'none'} at ${money(k.top_product_revenue)}. Refunds: ${k.refunds} (${k.refund_rate_pct}%).`,
    k.alerts.length ? `Check: ${k.alerts.map((a) => alertText[a] || a).join('; ')}.` : 'No alerts today.',
  ];
}

/** Slack-style payload (also readable as plain text by a Telegram bridge). */
function chatMessage(k, lines, source) {
  const title = `Daily KPIs for ${k.report_date}${k.alerts.length ? ' (needs a look)' : ''}`;
  return {
    text: `${title}\n${lines.map((l) => `- ${l}`).join('\n')}`,
    blocks: [
      { type: 'header', text: { type: 'plain_text', text: title } },
      { type: 'section', text: { type: 'mrkdwn', text: lines.map((l) => `• ${l}`).join('\n') } },
      { type: 'context', elements: [{ type: 'mrkdwn', text: `Summary: ${source}. Every number is checked against the sales query.` }] },
    ],
  };
}
