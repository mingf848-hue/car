const appState = {
  status: null,
  wallets: [],
  candidates: [],
  selectedWallet: "",
  selectedLabel: "",
  selectedTrades: [],
  tradeFilter: "ALL",
};

const $ = (id) => document.getElementById(id);

function usdc(value) {
  return `$${Number(value || 0).toFixed(2)}`;
}

function number(value, digits = 2) {
  return Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: digits });
}

function timeText(seconds) {
  if (!seconds) return "-";
  return new Date(Number(seconds) * 1000).toLocaleString("zh-CN");
}

function relative(seconds) {
  if (!seconds) return "-";
  const diff = Math.round(Number(seconds) - Date.now() / 1000);
  if (Math.abs(diff) < 2) return "现在";
  return diff > 0 ? `${diff} 秒后` : `${Math.abs(diff)} 秒前`;
}

function shortWallet(wallet) {
  const text = String(wallet || "");
  return text.length > 16 ? `${text.slice(0, 8)}...${text.slice(-6)}` : text || "-";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function toast(message, long = false) {
  const el = $("toast");
  el.textContent = message;
  el.classList.add("show");
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => el.classList.remove("show"), long ? 7000 : 2800);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function reasonText(reason) {
  if (!reason) return "-";
  if (/^copied_fixed_([0-9.]+)_usdc$/.test(reason)) {
    return `按固定金额 ${reason.match(/^copied_fixed_([0-9.]+)_usdc$/)[1]} USDC 跟买`;
  }
  const labels = {
    not_sports_market: "非体育市场，已跳过",
    token_on_cooldown: "同一选项冷却中",
    no_tracked_position_to_sell: "没有本地跟单仓位可卖",
    slippage_too_high: "买入滑点过高",
    sell_slippage_too_high: "卖出滑点过高",
    missing_current_price: "无法获取当前买价",
    missing_current_sell_price: "无法获取当前卖价",
    leader_trade_too_small: "聪明钱包交易金额太小",
    price_check_failed: "价格检查失败",
    auto_follow_sells_disabled: "自动跟卖关闭",
  };
  return labels[reason] || reason;
}

function actionText(action) {
  const labels = {
    dry_run_buy: "模拟跟买",
    live_buy: "实盘跟买",
    dry_run_sell: "模拟跟卖",
    live_sell: "实盘跟卖",
    skip: "跳过",
    blocked: "阻止",
    warmup: "预热",
    config_error: "配置",
  };
  return labels[action] || action || "-";
}

function tradeSideKey(side) {
  return side === "BUY" || side === "SELL" ? side : "UNKNOWN";
}

function tradeSideText(side) {
  const key = tradeSideKey(side);
  if (key === "BUY") return "买入";
  if (key === "SELL") return "卖出";
  return "未识别";
}

function insight(status) {
  const config = status?.config || {};
  const automation = status?.automation || {};
  const summary = status?.last_summary;
  if (!automation.enabled) return ["bad", "自动跟单未开启", "设置 AUTO_START=true 后重启服务。"];
  if (!automation.running) return ["bad", "自动任务未运行", "服务已启动但后台轮询任务没有运行。"];
  if (!config.effective_wallets?.length) return ["warn", "等待选择钱包", "从候选钱包查看下注详情，然后点“跟单此钱包”。"];
  if (!summary) return ["idle", "自动跟单运行中", `每 ${automation.poll_interval_seconds || 20} 秒检查一次。`];
  if (summary.errors?.length) return ["bad", "自动检查有问题", summary.errors.map(reasonText).join("；")];
  if (summary.warmup_wallets) return ["ok", "预热完成", "历史交易已记录，之后的新交易才会触发跟单。"];
  if (summary.processed === 0) return ["idle", "等待新交易", `最近读取 ${summary.fetched || 0} 条，没有未处理的新交易。`];
  if (!summary.copied && summary.skipped) return ["warn", "本轮全部跳过", "查看事件流水里的具体原因。"];
  return ["ok", "自动跟单正常", `跟单 ${summary.copied || 0} 笔，跳过 ${summary.skipped || 0} 笔。`];
}

function renderStatus() {
  const status = appState.status || {};
  const config = status.config || {};
  const automation = status.automation || {};
  const [tone, title, detail] = insight(status);
  $("state-card").className = `ops-card main-state ${tone}`;
  $("state-title").textContent = title;
  $("state-detail").textContent = detail;
  $("system-line").textContent = automation.running
    ? `自动轮询运行中，下次检查 ${relative(automation.next_scan_at)}`
    : "自动轮询未运行，请检查 Zeabur Variables";
  $("active-wallet-count").textContent = `${config.effective_wallets?.length || 0} 个`;
  $("active-wallet-detail").textContent = config.effective_wallets?.length
    ? "这些钱包的新交易会被自动检查。"
    : "还没有选择任何跟单钱包。";
  $("copy-size").textContent = usdc(config.copy_amount_usdc || 5);
  $("last-check").textContent = automation.last_scan_at ? relative(automation.last_scan_at) : "尚未检查";
  $("next-check").textContent = `间隔 ${automation.poll_interval_seconds || config.poll_interval_seconds || 20} 秒；累计 ${automation.scan_count || 0} 次。`;
}

function walletRow(wallet) {
  const active = Boolean(wallet.active);
  const locked = Boolean(wallet.locked);
  return `<div class="wallet-row ${active ? "active" : "paused"}" data-wallet="${escapeHtml(wallet.wallet)}">
    <button class="wallet-main" data-action="select" data-wallet="${escapeHtml(wallet.wallet)}">
      <strong>${escapeHtml(wallet.label || shortWallet(wallet.wallet))}</strong>
      <span>${escapeHtml(shortWallet(wallet.wallet))} · ${locked ? "环境变量" : wallet.source || "页面选择"}</span>
    </button>
    <button class="mini-button" data-action="${active ? "pause" : "resume"}" data-wallet="${escapeHtml(wallet.wallet)}" ${locked ? "disabled" : ""}>
      ${locked ? "固定" : active ? "暂停" : "恢复"}
    </button>
  </div>`;
}

function renderWallets() {
  const list = $("followed-wallets");
  if (!appState.wallets.length) {
    list.innerHTML = `<div class="empty-state">
      <strong>还没有跟单钱包</strong>
      <p>先在候选区查看钱包下注，再点“跟单此钱包”。</p>
    </div>`;
    return;
  }
  list.innerHTML = appState.wallets.map(walletRow).join("");
}

function renderCandidates() {
  const list = $("candidate-wallets");
  if (!appState.candidates.length) {
    list.innerHTML = `<div class="empty-state">
      <strong>候选池为空</strong>
      <p>点击“加载候选”读取体育排行榜钱包。</p>
    </div>`;
    return;
  }
  const followed = new Set(appState.wallets.filter((item) => item.active).map((item) => item.wallet.toLowerCase()));
  list.innerHTML = appState.candidates
    .map((item) => {
      const wallet = item.proxyWallet || item.proxy_wallet || item.wallet || "";
      const selected = wallet.toLowerCase() === appState.selectedWallet.toLowerCase();
      return `<div class="candidate-card ${selected ? "selected" : ""}">
        <button class="candidate-main" data-action="select-candidate" data-wallet="${escapeHtml(wallet)}" data-label="${escapeHtml(item.userName || item.username || "")}">
          <span class="rank">#${escapeHtml(item.rank || "-")}</span>
          <strong>${escapeHtml(item.userName || item.username || "未命名钱包")}</strong>
          <small>${escapeHtml(shortWallet(wallet))}</small>
        </button>
        <div class="candidate-metrics">
          <span>盈亏 ${usdc(item.pnl)}</span>
          <span>成交 ${usdc(item.vol)}</span>
        </div>
        <button class="secondary-button" data-action="follow-candidate" data-wallet="${escapeHtml(wallet)}" data-label="${escapeHtml(item.userName || item.username || "")}" ${followed.has(wallet.toLowerCase()) ? "disabled" : ""}>
          ${followed.has(wallet.toLowerCase()) ? "已跟单" : "跟单"}
        </button>
      </div>`;
    })
    .join("");
}

function renderDetail() {
  $("follow-selected-button").disabled = !appState.selectedWallet;
  $("detail-subtitle").textContent = appState.selectedWallet
    ? `${appState.selectedLabel || "已选钱包"} · ${shortWallet(appState.selectedWallet)}`
    : "选择一个钱包后查看近期买卖。";
  if (!appState.selectedWallet) {
    $("detail-summary").innerHTML = "";
    $("trade-list").innerHTML = `<div class="empty-state"><strong>未选择钱包</strong><p>从候选池或跟单列表选择一个钱包。</p></div>`;
    return;
  }
  const buys = appState.selectedTrades.filter((item) => item.side === "BUY").length;
  const sells = appState.selectedTrades.filter((item) => item.side === "SELL").length;
  const unknown = appState.selectedTrades.filter((item) => tradeSideKey(item.side) === "UNKNOWN").length;
  const total = appState.selectedTrades.reduce((sum, item) => sum + Number(item.usdc_size || 0), 0);
  $("detail-summary").innerHTML = `
    <div><span>近期交易</span><strong>${appState.selectedTrades.length}</strong></div>
    <div><span>买入 / 卖出 / 未识别</span><strong>${buys} / ${sells} / ${unknown}</strong></div>
    <div><span>名义金额</span><strong>${usdc(total)}</strong></div>
  `;
  const filteredTrades = appState.selectedTrades.filter((item) => {
    if (appState.tradeFilter === "ALL") return true;
    return tradeSideKey(item.side) === appState.tradeFilter;
  });
  if (!filteredTrades.length) {
    const filterText = appState.tradeFilter === "ALL" ? "近期下注" : tradeSideText(appState.tradeFilter);
    $("trade-list").innerHTML = `<div class="empty-state"><strong>没有读取到近期下注</strong><p>这个钱包可能近期不活跃，或数据接口没有返回公开交易。</p></div>`;
    if (appState.selectedTrades.length) {
      $("trade-list").innerHTML = `<div class="empty-state"><strong>没有${escapeHtml(filterText)}记录</strong><p>Polymarket 本次返回的近期交易里没有这一类方向。</p></div>`;
    }
    return;
  }
  $("trade-list").innerHTML = filteredTrades
    .map((trade) => `<div class="trade-row">
      <div>
        <strong>${escapeHtml(trade.market_title || trade.market_slug || "未知市场")}</strong>
        <span>${escapeHtml(trade.outcome || "-")} · ${timeText(trade.timestamp)} · 原始方向 ${escapeHtml(trade.raw_side || trade.side || "-")}</span>
      </div>
      <div class="trade-numbers">
        <b class="${tradeSideKey(trade.side).toLowerCase()}">${tradeSideText(trade.side)}</b>
        <span>${usdc(trade.usdc_size)} · ${number(trade.size, 4)} 份 · ${Number(trade.price || 0).toFixed(4)}</span>
      </div>
    </div>`)
    .join("");
}

function renderPositions(items) {
  const list = $("positions-list");
  if (!items.length) {
    list.innerHTML = `<div class="empty-state compact"><strong>暂无持仓</strong><p>只有本程序跟买后才会出现仓位。</p></div>`;
    return;
  }
  list.innerHTML = items.map((item) => `<div class="compact-row">
    <strong>${escapeHtml(item.market_slug || item.token_id)}</strong>
    <span>${escapeHtml(item.outcome || "-")} · ${number(item.open_shares, 4)} 份 · 买入 ${usdc(item.total_buy_usdc)}</span>
  </div>`).join("");
}

function renderEvents(items) {
  const list = $("events-list");
  if (!items.length) {
    list.innerHTML = `<div class="empty-state compact"><strong>暂无事件</strong><p>后台自动检查后会记录结果。</p></div>`;
    return;
  }
  list.innerHTML = items.map((item) => `<div class="event-row">
    <span class="event-action ${escapeHtml(item.action)}">${escapeHtml(actionText(item.action))}</span>
    <div>
      <strong>${escapeHtml(reasonText(item.reason))}</strong>
      <small>${timeText(item.created_at)} · ${escapeHtml(item.market_slug || item.wallet || "-")}</small>
    </div>
    <b>${item.amount_usdc ? usdc(item.amount_usdc) : ""}</b>
  </div>`).join("");
}

async function refreshAll() {
  const [status, wallets, positions, events] = await Promise.all([
    api("/api/status"),
    api("/wallets"),
    api("/positions?include_closed=false"),
    api("/events?limit=40"),
  ]);
  appState.status = status;
  appState.wallets = wallets.wallets || [];
  renderStatus();
  renderWallets();
  renderCandidates();
  renderPositions(positions.positions || []);
  renderEvents(events.events || []);
}

async function loadCandidates() {
  const button = $("discover-button");
  button.disabled = true;
  button.textContent = "加载中";
  try {
    const result = await api("/leaderboard?category=SPORTS&time_period=WEEK&order_by=PNL&limit=30");
    appState.candidates = result.wallets || [];
    renderCandidates();
    toast(`已加载 ${appState.candidates.length} 个候选钱包`);
  } catch (error) {
    toast(`候选加载失败：${error.message}`, true);
  } finally {
    button.disabled = false;
    button.textContent = "加载候选";
  }
}

async function selectWallet(wallet, label = "") {
  appState.selectedWallet = wallet;
  appState.selectedLabel = label;
  appState.selectedTrades = [];
  renderCandidates();
  renderWallets();
  renderDetail();
  try {
    const result = await api(`/wallets/${encodeURIComponent(wallet)}/trades?limit=30`);
    if (result.ok === false) {
      appState.selectedTrades = [];
      renderDetail();
      toast(`数据接口不可达：${result.error || "未知错误"}`, true);
      return;
    }
    appState.selectedTrades = result.trades || [];
    renderDetail();
  } catch (error) {
    toast(`下注详情读取失败：${error.message}`, true);
  }
}

async function followWallet(wallet, label = "") {
  if (!wallet) return;
  await api("/wallets/follow", {
    method: "POST",
    body: JSON.stringify({ wallet, label, source: "leaderboard" }),
  });
  toast("已加入自动跟单");
  await refreshAll();
}

async function pauseWallet(wallet) {
  await api(`/wallets/${encodeURIComponent(wallet)}/pause`, { method: "POST" });
  toast("已暂停跟单");
  await refreshAll();
}

async function resumeWallet(wallet) {
  await api(`/wallets/${encodeURIComponent(wallet)}/resume`, { method: "POST" });
  toast("已恢复跟单");
  await refreshAll();
}

async function manualScan() {
  const button = $("manual-scan-button");
  button.disabled = true;
  button.textContent = "补查中";
  try {
    await api("/scan", { method: "POST" });
    await refreshAll();
    toast("手动补查完成");
  } catch (error) {
    toast(`补查失败：${error.message}`, true);
  } finally {
    button.disabled = false;
    button.textContent = "手动补查";
  }
}

async function diagnose() {
  try {
    const result = await api("/diagnostics");
    const checks = result.checks || {};
    const leaderboard = checks.sports_leaderboard?.ok ? "榜单正常" : `榜单失败：${checks.sports_leaderboard?.error || "-"}`;
    const activity = checks.first_wallet_activity?.ok ? `首个钱包 ${checks.first_wallet_activity.raw_count} 条交易` : `钱包读取失败：${checks.first_wallet_activity?.error || "-"}`;
    toast(`${leaderboard}；${activity}`, true);
  } catch (error) {
    toast(`诊断失败：${error.message}`, true);
  }
}

function bindEvents() {
  $("refresh-button").addEventListener("click", () => refreshAll().catch((error) => toast(error.message, true)));
  $("diagnose-button").addEventListener("click", diagnose);
  $("manual-scan-button").addEventListener("click", manualScan);
  $("discover-button").addEventListener("click", loadCandidates);
  $("follow-selected-button").addEventListener("click", () => followWallet(appState.selectedWallet, appState.selectedLabel).catch((error) => toast(error.message, true)));

  document.addEventListener("click", (event) => {
    const target = event.target.closest("[data-action]");
    if (!target) return;
    const action = target.dataset.action;
    const wallet = target.dataset.wallet || "";
    const label = target.dataset.label || "";
    if (action === "select" || action === "select-candidate") selectWallet(wallet, label);
    if (action === "follow-candidate") followWallet(wallet, label).catch((error) => toast(error.message, true));
    if (action === "pause") pauseWallet(wallet).catch((error) => toast(error.message, true));
    if (action === "resume") resumeWallet(wallet).catch((error) => toast(error.message, true));
  });

  document.querySelectorAll(".rail-action").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".rail-action").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      document.getElementById(button.dataset.section)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });

  $("trade-filter").addEventListener("click", (event) => {
    const button = event.target.closest("[data-filter]");
    if (!button) return;
    appState.tradeFilter = button.dataset.filter;
    document.querySelectorAll("#trade-filter button").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    renderDetail();
  });
}

window.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  renderDetail();
  refreshAll().catch((error) => toast(`加载失败：${error.message}`, true));
  window.setInterval(() => refreshAll().catch(() => undefined), 8000);
});
