const state = {
  status: null,
  events: [],
  positions: [],
};

const $ = (id) => document.getElementById(id);

function formatUsdc(value) {
  const number = Number(value || 0);
  return `$${number.toFixed(2)}`;
}

function formatNumber(value, digits = 4) {
  const number = Number(value || 0);
  return number.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  });
}

function formatTime(seconds) {
  if (!seconds) return "-";
  return new Date(Number(seconds) * 1000).toLocaleString();
}

function toast(message) {
  const el = $("toast");
  el.textContent = message;
  el.classList.add("show");
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => el.classList.remove("show"), 2800);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

function renderStatus(payload) {
  state.status = payload;
  const config = payload.config || {};
  const stats = payload.stats || {};
  const mode = config.execution_mode || "-";
  const live = Boolean(config.live_trading_enabled);

  $("side-mode").textContent = live ? "Live trading" : `${mode} mode`;
  $("side-dot").className = live ? "dot live" : "dot";
  if (payload.last_error) $("side-dot").className = "dot error";

  $("subline").textContent = payload.last_error
    ? `Last error: ${payload.last_error}`
    : `Watching ${config.smart_wallets?.length || 0} wallets, sports-only ${config.sports_only ? "on" : "off"}.`;

  $("metric-mode").textContent = mode.toUpperCase();
  $("metric-live").textContent = live ? "Real orders enabled" : "Simulation only";
  $("metric-copy-size").textContent = formatUsdc(config.copy_amount_usdc || 5);
  $("metric-positions").textContent = stats.open_positions ?? "-";
  $("metric-shares").textContent = `${formatNumber(stats.open_shares || 0)} open shares`;
  $("metric-events").textContent = stats.events ?? "-";
  $("metric-flow").textContent = `${formatUsdc(stats.buy_usdc)} bought / ${formatUsdc(stats.sell_usdc)} sold`;

  $("risk-sports").textContent = config.sports_only ? "On" : "Off";
  $("risk-sells").textContent = config.auto_follow_sells ? "On" : "Off";
  $("risk-sell-mode").textContent = config.sell_mode || "-";
  $("risk-slippage").textContent = `${config.max_slippage_bps || 0} bps`;
  $("risk-daily-cap").textContent = formatUsdc(config.max_live_daily_usdc);
}

function renderPositions(items) {
  state.positions = items;
  const body = $("positions-body");
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="7" class="empty">No tracked positions.</td></tr>';
    return;
  }
  body.innerHTML = items
    .map((item) => {
      return `<tr>
        <td>${escapeHtml(item.market_slug || item.token_id)}</td>
        <td>${escapeHtml(item.outcome || "-")}</td>
        <td>${formatNumber(item.open_shares)}</td>
        <td>${Number(item.avg_entry_price || 0).toFixed(4)}</td>
        <td>${formatUsdc(item.total_buy_usdc)}</td>
        <td>${formatUsdc(item.total_sell_usdc)}</td>
        <td><span class="pill ${escapeHtml(item.status)}">${escapeHtml(item.status)}</span></td>
      </tr>`;
    })
    .join("");
}

function renderEvents(items) {
  state.events = items;
  const body = $("events-body");
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="6" class="empty">No events yet.</td></tr>';
    return;
  }
  body.innerHTML = items
    .map((item) => {
      return `<tr>
        <td>${formatTime(item.created_at)}</td>
        <td><span class="pill ${escapeHtml(item.action)}">${escapeHtml(item.action)}</span></td>
        <td>${escapeHtml(item.reason || "-")}</td>
        <td>${escapeHtml(item.market_slug || "-")}</td>
        <td>${escapeHtml(item.outcome || "-")}</td>
        <td>${formatUsdc(item.amount_usdc)}</td>
      </tr>`;
    })
    .join("");
}

function renderScores(items) {
  const list = $("wallet-score-list");
  if (!items.length) {
    list.innerHTML = '<div class="empty-block">No wallet scores returned.</div>';
    return;
  }
  list.innerHTML = items
    .map((item) => {
      return `<div class="score-row">
        <strong>${escapeHtml(item.wallet)}</strong>
        <span>${formatNumber(item.score, 2)}</span>
      </div>`;
    })
    .join("");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

async function refreshAll() {
  const includeClosed = $("include-closed").checked;
  const [status, positions, events] = await Promise.all([
    api("/api/status"),
    api(`/positions?include_closed=${includeClosed}`),
    api("/events?limit=80"),
  ]);
  renderStatus(status);
  renderPositions(positions.positions || []);
  renderEvents(events.events || []);
}

async function runScan() {
  const button = $("scan-button");
  button.disabled = true;
  button.textContent = "Scanning";
  try {
    const result = await api("/scan", { method: "POST" });
    toast(`Scan done: ${result.copied} copied, ${result.skipped} skipped`);
    await refreshAll();
  } catch (error) {
    toast(`Scan failed: ${error.message}`);
  } finally {
    button.disabled = false;
    button.textContent = "Run Scan";
  }
}

async function scoreWallets() {
  const button = $("score-button");
  button.disabled = true;
  button.textContent = "Scoring";
  try {
    const result = await api("/score-wallets", { method: "POST", body: "{}" });
    renderScores(result.wallets || []);
    toast("Wallet scores updated");
  } catch (error) {
    toast(`Score failed: ${error.message}`);
  } finally {
    button.disabled = false;
    button.textContent = "Score";
  }
}

window.addEventListener("DOMContentLoaded", () => {
  $("refresh-button").addEventListener("click", () => refreshAll().catch((error) => toast(error.message)));
  $("scan-button").addEventListener("click", runScan);
  $("score-button").addEventListener("click", scoreWallets);
  $("include-closed").addEventListener("change", () => refreshAll().catch((error) => toast(error.message)));

  refreshAll().catch((error) => toast(`Load failed: ${error.message}`));
  window.setInterval(() => refreshAll().catch(() => undefined), 15000);
});
