const appState = {
  status: null,
  portfolio: null,
  wallets: [],
  recommendations: [],
  selectedWallet: "",
  selectedLabel: "",
  selectedTrades: [],
  selectedSummary: null,
  tradeFilter: "ALL",
  detailLoading: false,
  detailError: "",
  activeScreen: "home",
  aiLoading: false,
  aiError: "",
  aiMode: "rules",
};

const $ = (id) => document.getElementById(id);

function usdc(value) {
  const num = Number(value || 0);
  const sign = num < 0 ? "-" : "";
  return `${sign}$${Math.abs(num).toFixed(2)}`;
}

function number(value, digits = 2) {
  return Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: digits });
}

function pct(value) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

function hasPnl(item, key = "pnl") {
  return Boolean(item?.[`${key}_available`]) && item?.[key] !== null && item?.[key] !== undefined;
}

function pnlClass(value, available) {
  if (!available) return "profit-muted";
  return Number(value || 0) >= 0 ? "profit-positive" : "profit-negative";
}

function pnlText(value, available) {
  return available ? usdc(value) : "未返回";
}

function timeText(seconds) {
  if (!seconds) return "-";
  return new Date(Number(seconds) * 1000).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function relative(seconds) {
  if (!seconds) return "-";
  const diff = Math.round(Number(seconds) - Date.now() / 1000);
  if (Math.abs(diff) < 2) return "现在";
  if (Math.abs(diff) < 60) return diff > 0 ? `${diff} 秒后` : `${Math.abs(diff)} 秒前`;
  const minutes = Math.round(Math.abs(diff) / 60);
  if (minutes < 60) return diff > 0 ? `${minutes} 分钟后` : `${minutes} 分钟前`;
  const hours = Math.round(minutes / 60);
  return diff > 0 ? `${hours} 小时后` : `${hours} 小时前`;
}

function shortWallet(wallet) {
  const text = String(wallet || "");
  return text.length > 16 ? `${text.slice(0, 6)}...${text.slice(-4)}` : text || "-";
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

function validWalletAddress(wallet) {
  return /^0x[a-fA-F0-9]{40}$/.test(String(wallet || "").trim());
}

function actionText(action) {
  const labels = {
    dry_run_buy: "模拟买入",
    live_buy: "实盘买入",
    dry_run_sell: "模拟卖出",
    live_sell: "实盘卖出",
    skip: "跳过",
    blocked: "阻止",
    warmup: "预热",
    config_error: "配置",
  };
  return labels[action] || action || "-";
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
    daily_live_limit_reached: "达到每日实盘上限",
  };
  return labels[reason] || reason;
}

function sourceText(source) {
  const labels = {
    leaderboard: "AI 推荐",
    manual: "手动添加",
    ui: "页面选择",
  };
  return labels[source] || source || "页面选择";
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

function switchScreen(screen) {
  appState.activeScreen = screen;
  document.querySelectorAll(".screen").forEach((item) => item.classList.toggle("active", item.dataset.screen === screen));
  document.querySelectorAll(".bottom-nav button").forEach((item) => item.classList.toggle("active", item.dataset.nav === screen));
}

function statusTone() {
  const status = appState.status || {};
  const config = status.config || {};
  const automation = status.automation || {};
  if (!automation.enabled || !automation.running) return ["离线", "自动轮询未运行"];
  if (!config.effective_wallets?.length) return ["待选择", "添加钱包后自动检查新交易"];
  if (status.last_summary?.errors?.length) return ["告警", status.last_summary.errors.map(reasonText).join("；")];
  if (status.last_summary?.warmup_wallets) return ["预热", "历史交易已记录，新交易才会跟单"];
  return ["运行中", `下次检查 ${relative(automation.next_scan_at)}`];
}

function renderHeader() {
  const status = appState.status || {};
  const config = status.config || {};
  const portfolio = appState.portfolio || {};
  const perf = portfolio.performance || {};
  const balance = portfolio.balance || {};
  const [mode, detail] = statusTone();
  $("mode-pill").textContent = mode;
  $("state-detail").textContent = detail;
  $("net-pnl").textContent = usdc(perf.realized_pnl || 0);
  $("net-pnl").style.color = Number(perf.realized_pnl || 0) >= 0 ? "var(--green)" : "var(--red)";
  $("balance-value").textContent = balance.available_usdc == null ? "--" : usdc(balance.available_usdc);
  $("balance-label").textContent = balance.label || "未接入";
  $("buy-total").textContent = usdc(perf.buy_usdc || 0);
  $("copy-size").textContent = `每单 ${usdc(config.copy_amount_usdc || 5)}`;
  $("position-count").textContent = String(perf.open_positions || 0);
  $("open-cost").textContent = `${usdc(perf.open_cost || 0)} 成本`;
  $("active-wallet-detail").textContent = config.effective_wallets?.length
    ? `${config.effective_wallets.length} 个钱包正在自动跟单`
    : "还没有选择钱包。";
}

function emptyState(title, detail) {
  return `<div class="empty-state"><div><strong>${escapeHtml(title)}</strong><p>${escapeHtml(detail)}</p></div></div>`;
}

function recommendationCard(item, compact = false) {
  const followed = appState.wallets.some((wallet) => wallet.wallet.toLowerCase() === item.wallet.toLowerCase());
  const tradesLabel = `${item.trades || 0} 笔`;
  const recentPnlAvailable = hasPnl(item, "recent_pnl");
  return `<article class="recommend-card" data-wallet="${escapeHtml(item.wallet)}">
    <div class="card-top">
      <div>
        <h3>${escapeHtml(item.label || shortWallet(item.wallet))}</h3>
        <small>${escapeHtml(shortWallet(item.wallet))} · ${escapeHtml(item.ai_label || "AI 推荐")}</small>
      </div>
      <div class="score-ring">${number(item.score, 0)}</div>
    </div>
    <p>${escapeHtml(item.ai_reason || "正在生成推荐理由。")}</p>
    <div class="metric-row">
      <div class="metric-pill"><span>榜单盈利</span><strong>${usdc(item.leaderboard_pnl)}</strong></div>
      <div class="metric-pill"><span>近期盈亏</span><strong class="${pnlClass(item.recent_pnl, recentPnlAvailable)}">${pnlText(item.recent_pnl, recentPnlAvailable)}</strong></div>
      <div class="metric-pill"><span>体育占比</span><strong>${pct(item.sports_ratio)}</strong></div>
    </div>
    <p class="mini-note">近期 ${tradesLabel} · 盈亏样本 ${item.recent_pnl_trades || 0} 笔</p>
    ${compact ? "" : `<p>风险：${escapeHtml(item.risk || "注意滑点和集中交易。")}</p>`}
    <div class="card-actions">
      <button class="card-action" data-action="inspect-recommendation" data-wallet="${escapeHtml(item.wallet)}" data-label="${escapeHtml(item.label || "")}">看下注</button>
      <button class="card-action primary" data-action="follow-recommendation" data-wallet="${escapeHtml(item.wallet)}" data-label="${escapeHtml(item.label || "")}" ${followed ? "disabled" : ""}>${followed ? "已跟单" : "跟单"}</button>
    </div>
  </article>`;
}

function renderRecommendations() {
  const aiSourceText = appState.aiMode === "deepseek" ? "DeepSeek AI" : "规则评分";
  const aiText = appState.aiLoading
    ? "AI 正在分析排行榜钱包。"
    : appState.aiError
      ? `推荐失败：${appState.aiError}`
      : appState.recommendations.length
        ? `${aiSourceText}已筛出 ${appState.recommendations.length} 个候选。`
        : "点击刷新读取排行榜。";
  $("ai-mode").textContent = aiText;
  const home = $("home-recommendations");
  const list = $("recommendation-list");
  if (appState.aiLoading) {
    const loading = emptyState("正在分析钱包", "读取排行榜、近期下注和盈利数据。");
    home.innerHTML = loading;
    list.innerHTML = loading;
    return;
  }
  if (appState.aiError) {
    const error = emptyState("AI 推荐不可用", appState.aiError);
    home.innerHTML = error;
    list.innerHTML = error;
    return;
  }
  if (!appState.recommendations.length) {
    const empty = emptyState("暂无推荐", "点击重新分析，读取体育排行榜钱包。");
    home.innerHTML = empty;
    list.innerHTML = empty;
    return;
  }
  home.innerHTML = appState.recommendations.slice(0, 5).map((item) => recommendationCard(item, true)).join("");
  list.innerHTML = appState.recommendations.map((item) => recommendationCard(item)).join("");
}

function walletCard(wallet) {
  const active = Boolean(wallet.active);
  const selected = wallet.wallet.toLowerCase() === appState.selectedWallet.toLowerCase();
  return `<article class="wallet-card ${selected ? "selected" : ""}">
    <div class="wallet-line">
      <div>
        <h3>${escapeHtml(wallet.label || shortWallet(wallet.wallet))}</h3>
        <small>${escapeHtml(shortWallet(wallet.wallet))} · ${escapeHtml(sourceText(wallet.source))}</small>
      </div>
      <span class="status-pill">${active ? "运行" : "暂停"}</span>
    </div>
    <div class="wallet-actions">
      <button class="card-action" data-action="select-wallet" data-wallet="${escapeHtml(wallet.wallet)}" data-label="${escapeHtml(wallet.label || "")}">看下注</button>
      <button class="card-action" data-action="${active ? "pause" : "resume"}" data-wallet="${escapeHtml(wallet.wallet)}">${active ? "暂停" : "恢复"}</button>
      <button class="card-action danger" data-action="delete-wallet" data-wallet="${escapeHtml(wallet.wallet)}">删除</button>
    </div>
  </article>`;
}

function renderWallets() {
  const list = $("followed-wallets");
  if (!appState.wallets.length) {
    list.innerHTML = emptyState("还没有跟单钱包", "从 AI 推荐点跟单，或手动粘贴 0x 地址。");
    return;
  }
  list.innerHTML = appState.wallets.map(walletCard).join("");
}

function renderPositions() {
  const list = $("positions-list");
  const positions = appState.portfolio?.positions || [];
  if (!positions.length) {
    list.innerHTML = emptyState("暂无持仓", "跟买成功后会在这里显示市场、方向和成本。");
    return;
  }
  list.innerHTML = positions.slice(0, 6).map((item) => `<article class="position-card">
    <h3>${escapeHtml(item.market_title_zh || item.market_slug || item.token_id)}</h3>
    <p>${escapeHtml(item.outcome_zh || item.outcome || "-")} · ${number(item.open_shares, 4)} 份</p>
    <div class="metric-row">
      <div class="metric-pill"><span>成本</span><strong>${usdc(item.total_buy_usdc)}</strong></div>
      <div class="metric-pill"><span>已卖出</span><strong>${usdc(item.total_sell_usdc)}</strong></div>
      <div class="metric-pill"><span>均价</span><strong>${number(item.avg_entry_price, 4)}</strong></div>
    </div>
  </article>`).join("");
}

function renderEvents(items) {
  const list = $("events-list");
  const visibleItems = (items || []).filter((item) => !(
    item.action === "config_error" && String(item.reason || "").startsWith("未选择跟单钱包")
  ));
  if (!visibleItems.length) {
    list.innerHTML = emptyState("暂无事件", "后台自动检查后会记录跟买、跳过和风控结果。");
    return;
  }
  list.innerHTML = visibleItems.map((item) => `<article class="event-card">
    <div class="event-top">
      <span class="event-tag ${escapeHtml(item.action)}">${escapeHtml(actionText(item.action))}</span>
      <small>${timeText(item.created_at)}</small>
    </div>
    <p>${escapeHtml(reasonText(item.reason))}</p>
    <small>${escapeHtml(item.market_title_zh || item.market_slug || item.wallet || "-")} ${item.amount_usdc ? `· ${usdc(item.amount_usdc)}` : ""}</small>
  </article>`).join("");
}

function renderDetail() {
  const selectedFollowed = appState.wallets.some(
    (item) => item.wallet.toLowerCase() === appState.selectedWallet.toLowerCase(),
  );
  $("follow-selected-button").disabled = !appState.selectedWallet || selectedFollowed;
  $("follow-selected-button").textContent = selectedFollowed ? "已在跟单" : "跟单此钱包";
  $("detail-title").textContent = appState.selectedLabel || (appState.selectedWallet ? shortWallet(appState.selectedWallet) : "选择钱包");
  $("detail-subtitle").textContent = appState.selectedWallet
    ? appState.selectedWallet
    : "从 AI 推荐或跟单钱包进入。";
  if (!appState.selectedWallet) {
    $("detail-summary").innerHTML = "";
    $("trade-list").innerHTML = emptyState("未选择钱包", "从 AI 推荐或钱包列表点“看下注”。");
    return;
  }
  if (appState.detailLoading) {
    $("detail-summary").innerHTML = "";
    $("trade-list").innerHTML = emptyState("正在读取下注", "正在加载这个钱包的近期买入和卖出。");
    return;
  }
  if (appState.detailError) {
    $("detail-summary").innerHTML = "";
    $("trade-list").innerHTML = emptyState("下注读取失败", appState.detailError);
    return;
  }
  const buys = appState.selectedTrades.filter((item) => item.side === "BUY").length;
  const sells = appState.selectedTrades.filter((item) => item.side === "SELL").length;
  const summary = appState.selectedSummary || {};
  const detailPnlAvailable = Boolean(summary.pnl_available);
  $("detail-summary").innerHTML = `
    <div><span>近期交易</span><strong>${appState.selectedTrades.length}</strong></div>
    <div><span>买入 / 卖出</span><strong>${buys} / ${sells}</strong></div>
    <div><span>近期盈亏</span><strong class="${pnlClass(summary.pnl, detailPnlAvailable)}">${pnlText(summary.pnl, detailPnlAvailable)}</strong></div>
  `;
  const filtered = appState.selectedTrades.filter((item) => appState.tradeFilter === "ALL" || tradeSideKey(item.side) === appState.tradeFilter);
  if (!filtered.length) {
    $("trade-list").innerHTML = emptyState("没有这一类下注", "换个筛选条件，或这个钱包近期没有公开交易。");
    return;
  }
  $("trade-list").innerHTML = filtered.map(tradeCard).join("");
}

function tradeCard(trade) {
  const side = tradeSideKey(trade.side).toLowerCase();
  const tradePnlAvailable = hasPnl(trade);
  return `<article class="trade-card ${side}" data-action="open-trade" data-trade="${escapeHtml(trade.trade_id)}">
    <div class="trade-meta">
      <span class="side-pill ${side}">${tradeSideText(trade.side)}</span>
      <small>${timeText(trade.timestamp)}</small>
    </div>
    <h3>${escapeHtml(trade.market_title_zh || trade.market_title || trade.market_slug || "未知市场")}</h3>
    <p>${escapeHtml(trade.outcome_zh || trade.outcome || "-")} · ${number(trade.size, 4)} 份 · 价格 ${number(trade.price, 4)}</p>
    <div class="metric-row">
      <div class="metric-pill"><span>金额</span><strong>${usdc(trade.usdc_size)}</strong></div>
      <div class="metric-pill"><span>盈亏</span><strong class="${pnlClass(trade.pnl, tradePnlAvailable)}">${pnlText(trade.pnl, tradePnlAvailable)}</strong></div>
      <div class="metric-pill"><span>时间</span><strong>${relative(trade.timestamp)}</strong></div>
    </div>
  </article>`;
}

async function refreshCore() {
  const [status, portfolio, wallets, events] = await Promise.all([
    api("/api/status"),
    api("/portfolio"),
    api("/wallets"),
    api("/events?limit=50"),
  ]);
  appState.status = status;
  appState.portfolio = portfolio;
  appState.wallets = wallets.wallets || [];
  renderHeader();
  renderWallets();
  renderPositions();
  renderEvents(events.events || []);
  renderDetail();
  renderRecommendations();
}

async function loadRecommendations() {
  appState.aiLoading = true;
  appState.aiError = "";
  renderRecommendations();
  try {
    const result = await api("/recommendations?limit=12");
    appState.recommendations = result.wallets || [];
    appState.aiMode = result.ai_mode || "rules";
    appState.aiError = result.error ? "Polymarket 数据接口暂不可达，无法分析排行榜。" : "";
  } catch (error) {
    appState.aiError = `推荐接口异常：${error.message}`;
  } finally {
    appState.aiLoading = false;
    renderRecommendations();
  }
}

async function selectWallet(wallet, label = "") {
  appState.selectedWallet = wallet;
  appState.selectedLabel = label;
  appState.selectedTrades = [];
  appState.selectedSummary = null;
  appState.detailLoading = true;
  appState.detailError = "";
  switchScreen("detail");
  renderWallets();
  renderDetail();
  try {
    const result = await api(`/wallets/${encodeURIComponent(wallet)}/trades?limit=40`);
    if (result.ok === false) {
      appState.detailError = `数据接口不可达：${result.error || "未知错误"}`;
      return;
    }
    appState.selectedTrades = result.trades || [];
    appState.selectedSummary = result.summary || null;
  } catch (error) {
    appState.detailError = error.message;
  } finally {
    appState.detailLoading = false;
    renderDetail();
  }
}

async function followWallet(wallet, label = "", source = "leaderboard") {
  if (!wallet) return;
  if (!validWalletAddress(wallet)) {
    throw new Error("钱包地址格式不对，请粘贴完整 0x 地址");
  }
  await api("/wallets/follow", {
    method: "POST",
    body: JSON.stringify({ wallet, label, source }),
  });
  toast("已加入自动跟单");
  await refreshCore();
}

async function pauseWallet(wallet) {
  await api(`/wallets/${encodeURIComponent(wallet)}/pause`, { method: "POST" });
  toast("已暂停跟单");
  await refreshCore();
}

async function resumeWallet(wallet) {
  await api(`/wallets/${encodeURIComponent(wallet)}/resume`, { method: "POST" });
  toast("已恢复跟单");
  await refreshCore();
}

async function deleteWallet(wallet) {
  await api(`/wallets/${encodeURIComponent(wallet)}`, { method: "DELETE" });
  if (wallet.toLowerCase() === appState.selectedWallet.toLowerCase()) {
    appState.selectedWallet = "";
    appState.selectedLabel = "";
    appState.selectedTrades = [];
    appState.selectedSummary = null;
    appState.detailError = "";
    appState.detailLoading = false;
  }
  toast("已删除跟单钱包");
  await refreshCore();
}

async function manualScan() {
  const button = $("manual-scan-button");
  button.disabled = true;
  button.textContent = "补查中";
  try {
    await api("/scan", { method: "POST" });
    await refreshCore();
    toast("手动补查完成");
  } catch (error) {
    toast(`补查失败：${error.message}`, true);
  } finally {
    button.disabled = false;
    button.textContent = "立即补查";
  }
}

async function diagnose() {
  try {
    const result = await api("/diagnostics");
    const checks = result.checks || {};
    const leaderboard = checks.sports_leaderboard?.ok ? "榜单正常" : `榜单失败：${checks.sports_leaderboard?.error || "-"}`;
    const activity = checks.first_wallet_activity?.ok ? `钱包 ${checks.first_wallet_activity.raw_count} 条交易` : `钱包读取：${checks.first_wallet_activity?.error || "-"}`;
    toast(`${leaderboard}；${activity}`, true);
  } catch (error) {
    toast(`诊断失败：${error.message}`, true);
  }
}

function openTradeSheet(tradeId) {
  const trade = appState.selectedTrades.find((item) => item.trade_id === tradeId);
  if (!trade) return;
  const tradePnlAvailable = hasPnl(trade);
  $("sheet-content").innerHTML = `<h2>${escapeHtml(trade.market_title_zh || trade.market_title || trade.market_slug || "下注详情")}</h2>
    <p>${escapeHtml(trade.outcome_zh || trade.outcome || "-")} · ${tradeSideText(trade.side)} · ${timeText(trade.timestamp)}</p>
    <div class="sheet-grid">
      <div><span>金额</span><strong>${usdc(trade.usdc_size)}</strong></div>
      <div><span>单笔盈亏</span><strong class="${pnlClass(trade.pnl, tradePnlAvailable)}">${pnlText(trade.pnl, tradePnlAvailable)}</strong></div>
      <div><span>份额</span><strong>${number(trade.size, 6)}</strong></div>
      <div><span>价格</span><strong>${number(trade.price, 6)}</strong></div>
      <div><span>成交时间</span><strong>${timeText(trade.timestamp)}</strong></div>
      <div><span>市场</span><strong>${escapeHtml(trade.market_slug || "-")}</strong></div>
      <div><span>Token</span><strong>${escapeHtml(trade.token_id || "-")}</strong></div>
      <div><span>钱包</span><strong>${escapeHtml(shortWallet(trade.wallet || appState.selectedWallet))}</strong></div>
    </div>`;
  $("sheet-backdrop").classList.add("show");
  $("trade-sheet").classList.add("show");
  $("trade-sheet").setAttribute("aria-hidden", "false");
}

function closeTradeSheet() {
  $("sheet-backdrop").classList.remove("show");
  $("trade-sheet").classList.remove("show");
  $("trade-sheet").setAttribute("aria-hidden", "true");
}

function bindEvents() {
  $("refresh-button").addEventListener("click", () => refreshCore().catch((error) => toast(error.message, true)));
  $("diagnose-button").addEventListener("click", diagnose);
  $("manual-scan-button").addEventListener("click", manualScan);
  $("recommend-refresh-button").addEventListener("click", loadRecommendations);
  $("ai-load-button").addEventListener("click", loadRecommendations);
  $("follow-selected-button").addEventListener("click", () => followWallet(appState.selectedWallet, appState.selectedLabel).catch((error) => toast(error.message, true)));
  $("wallet-add-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = $("wallet-address-input");
    const wallet = input.value.trim();
    followWallet(wallet, "手动添加", "manual")
      .then(() => {
        input.value = "";
      })
      .catch((error) => toast(error.message, true));
  });
  $("sheet-close-button").addEventListener("click", closeTradeSheet);
  $("sheet-backdrop").addEventListener("click", closeTradeSheet);

  document.querySelectorAll(".bottom-nav button").forEach((button) => {
    button.addEventListener("click", () => switchScreen(button.dataset.nav));
  });

  document.addEventListener("click", (event) => {
    const target = event.target.closest("[data-action]");
    if (!target) return;
    const action = target.dataset.action;
    const wallet = target.dataset.wallet || "";
    const label = target.dataset.label || "";
    if (action === "inspect-recommendation" || action === "select-wallet") selectWallet(wallet, label);
    if (action === "follow-recommendation") followWallet(wallet, label, "leaderboard").catch((error) => toast(error.message, true));
    if (action === "pause") pauseWallet(wallet).catch((error) => toast(error.message, true));
    if (action === "resume") resumeWallet(wallet).catch((error) => toast(error.message, true));
    if (action === "delete-wallet") deleteWallet(wallet).catch((error) => toast(error.message, true));
    if (action === "open-trade") openTradeSheet(target.dataset.trade || "");
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
  refreshCore().catch((error) => toast(`加载失败：${error.message}`, true));
  loadRecommendations().catch((error) => toast(`推荐失败：${error.message}`, true));
  window.setInterval(() => refreshCore().catch(() => undefined), 5000);
});
