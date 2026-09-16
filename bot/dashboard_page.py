"""Dashboard HTML template - extracted from dashboard.py."""

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Polymarket Survival Bot — Paper Dashboard</title>
<style>
  :root {
    --bg: #0d1117; --panel: #161b22; --border: #30363d;
    --text: #e6edf3; --muted: #8b949e;
    --green: #3fb950; --red: #f85149; --blue: #58a6ff; --amber: #d29922;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg);
    color: var(--text); padding: 20px;
  }
  header { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }
  h1 { font-size: 20px; }
  .badge { padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }
  .badge.paper { background: #1f6feb33; color: var(--blue); }
  .badge.live { background: #f8514933; color: var(--red); }
  .live-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--green);
    animation: pulse 1.5s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 12px; margin-bottom: 20px; }
  .card { background: var(--panel); border: 1px solid var(--border);
    border-radius: 8px; padding: 14px; }
  .card .label { font-size: 11px; color: var(--muted); text-transform: uppercase;
    letter-spacing: 0.5px; margin-bottom: 6px; }
  .card .value { font-size: 22px; font-weight: 700; }
  .pos { color: var(--green); } .neg { color: var(--red); }
  h2 { font-size: 14px; color: var(--muted); margin: 24px 0 10px;
    text-transform: uppercase; letter-spacing: 0.5px; }
  table { width: 100%; border-collapse: collapse; background: var(--panel);
    border: 1px solid var(--border); border-radius: 8px; overflow: hidden;
    font-size: 13px; }
  th { background: #1c2129; padding: 8px 10px; text-align: left; font-size: 11px;
    color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }
  td { padding: 8px 10px; border-top: 1px solid var(--border); }
  tr:hover td { background: #1c212950; }
  .status { padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
  .status.open { background: #d2992233; color: var(--amber); }
  .status.take_profit { background: #3fb95033; color: var(--green); }
  .status.stop_loss, .status.timeout { background: #f8514933; color: var(--red); }
  .side-yes { color: var(--green); font-weight: 600; }
  .side-no { color: var(--red); font-weight: 600; }
  #curve { width: 100%; height: 220px; background: var(--panel);
    border: 1px solid var(--border); border-radius: 8px; }
  .empty { color: var(--muted); font-style: italic; padding: 20px; text-align: center; }
  .footer { margin-top: 24px; color: var(--muted); font-size: 11px; text-align: center; }
  .reasoning { max-width: 260px; white-space: nowrap; overflow: hidden;
    text-overflow: ellipsis; cursor: help; }
  .table-scroll { max-height: 520px; overflow-y: auto; }
  .table-scroll th { position: sticky; top: 0; z-index: 2;
    box-shadow: 0 1px 0 var(--border); }
  .table-scroll::-webkit-scrollbar { width: 10px; }
  .table-scroll::-webkit-scrollbar-track { background: transparent; }
  .table-scroll::-webkit-scrollbar-thumb { background: var(--border);
    border-radius: 5px; }
  .table-scroll::-webkit-scrollbar-thumb:hover { background: #3d444d; }
</style>
</head>
<body>
<header>
  <span class="live-dot"></span>
  <h1>Polymarket Survival Bot</h1>
  <span class="badge paper" id="mode-badge">PAPER</span>
  <span style="color:var(--muted);font-size:12px" id="updated"></span>
</header>

<div class="grid" id="cards"></div>

<h2>Equity Curve (cumulative PnL)</h2>
<canvas id="curve"></canvas>

<h2>Trades</h2>
<div class="table-scroll">
<table id="trades-table">
  <thead><tr>
    <th>#</th><th>Market</th><th>Side</th><th>Entry</th><th>Exit</th>
    <th>Size</th><th>Shares</th><th>Status</th><th>PnL</th><th>Fees</th><th>Edge</th>
    <th>Signal</th><th>Opened</th>
  </tr></thead>
  <tbody id="trades-body"></tbody>
</table>
</div>

<h2>Survival Events</h2>
<div class="table-scroll">
<table>
  <thead><tr><th>Time</th><th>Event</th><th>Detail</th></tr></thead>
  <tbody id="events-body"></tbody>
</table>
</div>

<div class="footer">Auto-refresh 2s &middot; reads data/trades.db (WAL) &middot; bot keeps running independently</div>

<script>
let lastData = null;

async function refresh() {
  try {
    const r = await fetch('/api/data');
    const d = await r.json();
    lastData = d;
    render(d);
  } catch (e) {
    document.getElementById('updated').textContent = 'connection lost — retrying';
  }
}

function fmtPnl(v) {
  if (v === null || v === undefined) return '—';
  const s = v >= 0 ? '+' : '-';
  return s + '$' + Math.abs(v).toFixed(2);
}

function pnlClass(v) { return v >= 0 ? 'pos' : 'neg'; }

function render(d) {
  document.getElementById('mode-badge').textContent = d.mode;
  document.getElementById('mode-badge').className = 'badge ' + d.mode.toLowerCase();
  document.getElementById('updated').textContent =
    'updated ' + new Date(d.server_time).toLocaleTimeString();

  const s = d.stats;
  const cards = [
    ['Total PnL', fmtPnl(s.total_pnl), pnlClass(s.total_pnl)],
    ['Total Fees', '$' + s.total_fees.toFixed(2), ''],
    ['Today', fmtPnl(s.day_pnl), pnlClass(s.day_pnl)],
    ['This Month', fmtPnl(s.month_pnl), pnlClass(s.month_pnl)],
    ['Win Rate', s.win_rate + '%', s.win_rate >= 50 ? 'pos' : 'neg'],
    ['Closed Trades', s.closed_trades, ''],
    ['Open Positions', s.open_positions + ' ($' + s.open_exposure.toFixed(0) + ')', ''],
    ['Capital', '$' + d.capital.toFixed(0), ''],
    ['Equity', '$' + (d.capital + s.total_pnl).toFixed(2), pnlClass(s.total_pnl)],
  ];
  document.getElementById('cards').innerHTML = cards.map(c =>
    `<div class="card"><div class="label">${c[0]}</div>
     <div class="value ${c[2]}">${c[1]}</div></div>`).join('');

  renderCurve(d.equity_curve);

  const tb = document.getElementById('trades-body');
  if (!d.trades.length) {
    tb.innerHTML = '<tr><td colspan="13" class="empty">No trades yet — bot is scanning…</td></tr>';
  } else {
    tb.innerHTML = d.trades.map(t => {
      const sideCls = t.side === 'YES' ? 'side-yes' : 'side-no';
      const statusCls = (t.status || '').replace(/ /g, '_');
      return `<tr>
        <td>${t.id}</td>
        <td class="reasoning" title="${(t.market_question || '').replace(/"/g, '&quot;')}">${t.market_question || '—'}</td>
        <td class="${sideCls}">${t.side}</td>
        <td>${t.entry_price !== null ? t.entry_price.toFixed(3) : '—'}</td>
        <td>${t.exit_price !== null ? t.exit_price.toFixed(3) : '—'}</td>
        <td>$${t.amount_usd.toFixed(2)}</td>
        <td>${t.shares.toFixed(1)}</td>
        <td><span class="status ${statusCls}">${t.status.replace(/_/g, ' ')}</span></td>
        <td class="${t.pnl_usd === null ? '' : pnlClass(t.pnl_usd)}">${fmtPnl(t.pnl_usd)}</td>
        <td>${t.fees_paid !== null ? '$' + t.fees_paid.toFixed(2) : '—'}</td>
        <td>${t.edge !== null ? (t.edge * 100).toFixed(0) + '%' : '—'}</td>
        <td>${t.classification || '—'}</td>
        <td>${t.entry_at || ''}</td>
      </tr>`;
    }).join('');
  }

  const eb = document.getElementById('events-body');
  if (!d.survival_events.length) {
    eb.innerHTML = '<tr><td colspan="3" class="empty">No events yet</td></tr>';
  } else {
    eb.innerHTML = d.survival_events.map(e =>
      `<tr><td>${e.created_at}</td><td>${e.event}</td><td>${e.detail || ''}</td></tr>`
    ).join('');
  }
}

function renderCurve(points) {
  const c = document.getElementById('curve');
  const ctx = c.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const W = c.clientWidth, H = c.clientHeight;
  c.width = W * dpr; c.height = H * dpr;
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, W, H);

  if (!points || points.length < 2) {
    ctx.fillStyle = '#8b949e';
    ctx.font = '13px Segoe UI';
    ctx.textAlign = 'center';
    ctx.fillText(points && points.length === 1
      ? '1 closed trade — need 2+ for a curve'
      : 'No closed trades yet', W / 2, H / 2);
    return;
  }

  const pad = { l: 50, r: 15, t: 15, b: 25 };
  let cum = 0;
  const vals = points.map(p => (cum += p.pnl_usd));
  const min = Math.min(0, ...vals), max = Math.max(0, ...vals);
  const span = (max - min) || 1;
  const x = i => pad.l + (i / (points.length - 1)) * (W - pad.l - pad.r);
  const y = v => pad.t + (1 - (v - min) / span) * (H - pad.t - pad.b);

  // grid + zero line
  ctx.strokeStyle = '#30363d'; ctx.fillStyle = '#8b949e'; ctx.font = '10px Segoe UI';
  for (let g = 0; g <= 4; g++) {
    const v = min + (span * g) / 4;
    const gy = y(v);
    ctx.beginPath(); ctx.moveTo(pad.l, gy); ctx.lineTo(W - pad.r, gy); ctx.stroke();
    ctx.textAlign = 'right';
    ctx.fillText('$' + v.toFixed(1), pad.l - 6, gy + 3);
  }
  // zero line stronger
  ctx.strokeStyle = '#58a6ff66';
  ctx.beginPath(); ctx.moveTo(pad.l, y(0)); ctx.lineTo(W - pad.r, y(0)); ctx.stroke();

  // line
  ctx.strokeStyle = '#3fb950'; ctx.lineWidth = 2; ctx.beginPath();
  vals.forEach((v, i) => i ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v)));
  ctx.stroke();

  // fill under line
  const grad = ctx.createLinearGradient(0, pad.t, 0, H - pad.b);
  grad.addColorStop(0, '#3fb95033'); grad.addColorStop(1, '#3fb95005');
  ctx.lineTo(x(points.length - 1), y(Math.max(min, 0)));
  ctx.lineTo(x(0), y(Math.max(min, 0)));
  ctx.closePath(); ctx.fillStyle = grad; ctx.fill();

  // end dot + label
  const last = vals[vals.length - 1];
  ctx.fillStyle = last >= 0 ? '#3fb950' : '#f85149';
  ctx.beginPath(); ctx.arc(x(vals.length - 1), y(last), 4, 0, Math.PI * 2); ctx.fill();
  ctx.font = 'bold 12px Segoe UI'; ctx.textAlign = 'left';
  ctx.fillText((last >= 0 ? '+$' : '-$') + Math.abs(last).toFixed(2),
    Math.min(x(vals.length - 1) + 8, W - 60), y(last) - 8);
}

refresh();
setInterval(refresh, 2000);
window.addEventListener('resize', () => lastData && renderCurve(lastData.equity_curve));
</script>
</body>
</html>"""
