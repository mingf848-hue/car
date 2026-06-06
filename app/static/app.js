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
  return number.toLocaleString("zh-CN", {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  });
}

function formatTime(seconds) {
  if (!seconds) return "-";
  return new Date(Number(seconds) * 1000).toLocaleString("zh-CN");
}

function modeLabel(mode, live) {
  if (live) return "实盘交易";
  if (mode === "dry_run") return "模拟模式";
  if (mode === "live") return "实盘模式未授权";
  return mode || "-";
}

function sellModeLabel(mode) {
  const labels = {
    close_full_on_leader_sell: "聪明钱包卖出时全平本地跟单仓位",
  };
  return labels[mode] || mode || "-";
}

function statusLabel(status) {
  const labels = {
    open: "持仓中",
    closed: "已平仓",
  };
  return labels[status] || status || "-";
}

function actionLabel(action) {
  const labels = {
    dry_run_buy: "模拟跟买",
    live_buy: "实盘跟买",
    dry_run_sell: "模拟跟卖",
    live_sell: "实盘跟卖",
    skip: "已跳过",
    blocked: "已阻止",
    warmup: "首次预热",
    config_error: "配置错误",
  };
  return labels[action] || action || "-";
}

function reasonLabel(reason) {
  if (/^copied_fixed_[0-9.]+_usdc$/.test(reason || "")) {
    const amount = reason.match(/^copied_fixed_([0-9.]+)_usdc$/)?.[1] || "";
    return `已按固定金额 ${amount} USDC 跟买`;
  }
  if (/^closed_tracked_position_[0-9.]+_shares$/.test(reason || "")) {
    const shares = reason.match(/^closed_tracked_position_([0-9.]+)_shares$/)?.[1] || "";
    return `已平掉本地跟单持仓 ${shares} 份`;
  }
  if (/^polymarket_geoblocked_/i.test(reason || "")) {
    return "Polymarket 判定当前服务器地区受限，已停止开仓";
  }
  if (/^polymarket_close_only_/i.test(reason || "")) {
    return "Polymarket 判定当前服务器地区为只允许平仓地区，已停止开仓";
  }
  if (/^geoblock_check_failed:/i.test(reason || "")) {
    return `地区检查失败：${reason.split(":").slice(1).join(":").trim()}`;
  }
  const labels = {
    simulated_buy: "模拟买入成功",
    simulated_sell: "模拟卖出成功",
    live_buy_submitted: "实盘买单已提交",
    live_sell_submitted: "实盘卖单已提交",
    token_on_cooldown: "同一选项仍在冷却时间内",
    not_sports_market: "不是体育市场",
    no_tracked_position_to_sell: "本程序没有可跟卖的本地持仓",
    slippage_too_high: "买入滑点过高",
    sell_slippage_too_high: "卖出滑点过高",
    daily_live_limit_reached: "已达到每日实盘买入上限",
    missing_current_price: "无法获取当前买入价格",
    missing_current_sell_price: "无法获取当前卖出价格",
    leader_trade_too_small: "聪明钱包这笔交易金额太小",
    unsupported_side: "暂不支持该交易方向",
    unsupported_leader_side: "暂不支持聪明钱包这类交易方向",
    price_check_failed: "买入价格检查失败",
    sell_price_check_failed: "卖出价格检查失败",
    auto_follow_sells_disabled: "自动跟卖已关闭",
    tracked_position_below_min_sell_shares: "本地持仓份额低于最小卖出数量",
    unsupported_sell_mode: "暂不支持当前卖出规则",
    geoblocked: "当前服务器地区受限，已停止开仓",
    no_recent_trades: "近期没有交易记录",
  };
  return labels[reason] || reason || "-";
}

function scanInsight(summary, config = {}) {
  if (!summary) {
    if (!config.smart_wallets?.length) {
      return {
        tone: "warn",
        title: "还没有可扫描的钱包",
        detail: "先点“发现钱包”，复制候选地址，再到 Zeabur Variables 填入 SMART_WALLETS。",
        next: "发现钱包",
      };
    }
    return {
      tone: "idle",
      title: "等待首次扫描",
      detail: "点击“立即扫描”后，会读取已配置钱包的近期交易。",
      next: "立即扫描",
    };
  }
  if (summary.errors?.length) {
    return {
      tone: "bad",
      title: "扫描遇到问题",
      detail: summary.errors.map(reasonLabel).join("；"),
      next: "点诊断",
    };
  }
  if (summary.blocked) {
    return {
      tone: "bad",
      title: "服务器地区被限制",
      detail: "Polymarket 判定当前部署地区不可开仓，换 Zeabur 区域后再试。",
      next: "换区域",
    };
  }
  if (summary.warmup_wallets) {
    return {
      tone: "ok",
      title: "首次预热完成",
      detail: `已初始化 ${summary.warmup_wallets} 个钱包，历史交易只记录不跟单，之后的新交易才会触发跟单。`,
      next: "等待新交易",
    };
  }
  if (summary.fetched === 0 && summary.processed === 0 && summary.copied === 0 && summary.skipped === 0) {
    return {
      tone: "warn",
      title: "没有读取到近期交易",
      detail: "已配置钱包近期没有公开交易，或这个地址不是 Polymarket 活跃钱包。",
      next: "换候选钱包",
    };
  }
  if (summary.processed === 0 && summary.fetched > 0) {
    return {
      tone: "idle",
      title: "没有新交易",
      detail: `读取到 ${summary.fetched} 条记录，但都是之前已经处理过的交易。`,
      next: "等待新交易",
    };
  }
  if (summary.copied === 0 && summary.skipped > 0) {
    return {
      tone: "warn",
      title: "本轮全部跳过",
      detail: `处理 ${summary.processed} 笔，跳过 ${summary.skipped} 笔。查看最近事件里的跳过原因。`,
      next: "看事件",
    };
  }
  return {
    tone: "ok",
    title: "扫描完成",
    detail: `本轮跟单 ${summary.copied || 0} 笔，跳过 ${summary.skipped || 0} 笔。`,
    next: "继续监控",
  };
}

function toast(message) {
  const el = $("toast");
  el.textContent = message;
  el.classList.add("show");
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => el.classList.remove("show"), 2800);
}

function longToast(message) {
  const el = $("toast");
  el.textContent = message;
  el.classList.add("show");
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => el.classList.remove("show"), 7000);
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

  $("side-mode").textContent = modeLabel(mode, live);
  $("side-dot").className = live ? "dot live" : "dot";
  if (payload.last_error) $("side-dot").className = "dot error";

  $("subline").textContent = payload.last_error
    ? `最近错误：${payload.last_error}`
    : `正在监控 ${config.smart_wallets?.length || 0} 个钱包，只跟体育：${config.sports_only ? "开启" : "关闭"}。`;

  $("metric-mode").textContent = modeLabel(mode, live);
  $("metric-live").textContent = live ? "真实订单已开启" : "当前只模拟，不会真实下单";
  $("metric-copy-size").textContent = formatUsdc(config.copy_amount_usdc || 5);
  $("metric-positions").textContent = stats.open_positions ?? "-";
  $("metric-shares").textContent = `${formatNumber(stats.open_shares || 0)} 份未平仓`;
  $("metric-events").textContent = stats.events ?? "-";
  $("metric-flow").textContent = `买入 ${formatUsdc(stats.buy_usdc)} / 卖出 ${formatUsdc(stats.sell_usdc)}`;

  $("risk-sports").textContent = config.sports_only ? "开启" : "关闭";
  $("risk-sells").textContent = config.auto_follow_sells ? "开启" : "关闭";
  $("risk-sell-mode").textContent = sellModeLabel(config.sell_mode);
  $("risk-slippage").textContent = `${config.max_slippage_bps || 0} 基点`;
  $("risk-daily-cap").textContent = formatUsdc(config.max_live_daily_usdc);

  const insight = scanInsight(payload.last_summary, config);
  $("status-card").className = `status-card primary-status ${insight.tone}`;
  $("status-title").textContent = insight.title;
  $("status-detail").textContent = insight.detail;
  $("configured-wallets").textContent = `${config.smart_wallets?.length || 0} 个`;
  $("configured-wallets-detail").textContent = config.smart_wallets?.length
    ? `扫描会读取这些地址，每次跟买固定 ${formatUsdc(config.copy_amount_usdc || 5)}。`
    : "现在扫描不会有结果，因为 SMART_WALLETS 为空。";
  $("scan-summary").textContent = payload.last_summary
    ? `${payload.last_summary.copied || 0} 跟单 / ${payload.last_summary.skipped || 0} 跳过`
    : "尚未扫描";
  $("scan-summary-detail").textContent = payload.last_summary
    ? `读取 ${payload.last_summary.fetched || 0} 条，处理 ${payload.last_summary.processed || 0} 条。`
    : "自动轮询或手动扫描后会更新。";
  $("next-action").textContent = insight.next;
  $("next-action-detail").textContent = config.smart_wallets?.length
    ? "先看最近事件，再决定是否换钱包。"
    : "先复制候选钱包，再填入 Zeabur Variables。";
}

function renderPositions(items) {
  state.positions = items;
  const body = $("positions-body");
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="7" class="empty">暂无跟单持仓。</td></tr>';
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
        <td><span class="pill ${escapeHtml(item.status)}">${escapeHtml(statusLabel(item.status))}</span></td>
      </tr>`;
    })
    .join("");
}

function renderEvents(items) {
  state.events = items;
  const body = $("events-body");
  if (!items.length) {
    body.innerHTML = '<tr><td colspan="6" class="empty">暂无事件。点击“立即扫描”后，这里会显示扫描结果。</td></tr>';
    return;
  }
  body.innerHTML = items
    .map((item) => {
      return `<tr>
        <td>${formatTime(item.created_at)}</td>
        <td><span class="pill ${escapeHtml(item.action)}">${escapeHtml(actionLabel(item.action))}</span></td>
        <td>${escapeHtml(reasonLabel(item.reason))}</td>
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
    list.innerHTML = '<div class="empty-block">没有返回钱包评分。请先在 Zeabur Variables 里填写 SMART_WALLETS。</div>';
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

function shortWallet(wallet) {
  const text = String(wallet || "");
  if (text.length <= 14) return text || "-";
  return `${text.slice(0, 8)}...${text.slice(-6)}`;
}

function renderLeaderboard(items) {
  const list = $("leaderboard-list");
  if (!items.length) {
    list.innerHTML = '<div class="empty-block">没有返回体育榜单钱包。稍后再试，或检查服务器是否能访问 Polymarket 数据接口。</div>';
    return;
  }
  list.innerHTML = items
    .map((item) => {
      const wallet = item.proxyWallet || item.proxy_wallet || item.wallet || "";
      const name = item.userName || item.username || "未命名钱包";
      return `<div class="score-row leaderboard-row">
        <div>
          <strong>${escapeHtml(name)}</strong>
          <small>排名 ${escapeHtml(item.rank || "-")} · 地址 ${escapeHtml(shortWallet(wallet))}</small>
        </div>
        <div class="score-actions">
          <span>盈亏 ${formatUsdc(item.pnl)} · 成交 ${formatUsdc(item.vol)}</span>
          <button class="mini-button" data-wallet="${escapeHtml(wallet)}">复制</button>
        </div>
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
  button.textContent = "扫描中";
  try {
    const result = await api("/scan", { method: "POST" });
    const insight = scanInsight(result, state.status?.config || {});
    longToast(`${insight.title}：${insight.detail}`);
    await refreshAll();
  } catch (error) {
    toast(`扫描失败：${error.message}`);
  } finally {
    button.disabled = false;
    button.textContent = "立即扫描";
  }
}

async function scoreWallets() {
  const button = $("score-button");
  button.disabled = true;
  button.textContent = "评分中";
  try {
    const result = await api("/score-wallets", { method: "POST", body: "{}" });
    renderScores(result.wallets || []);
    toast("钱包评分已更新");
  } catch (error) {
    toast(`评分失败：${error.message}`);
  } finally {
    button.disabled = false;
    button.textContent = "评分";
  }
}

async function discoverWallets() {
  const button = $("discover-button");
  button.disabled = true;
  button.textContent = "发现中";
  try {
    const result = await api("/leaderboard?category=SPORTS&time_period=WEEK&order_by=PNL&limit=25");
    renderLeaderboard(result.wallets || []);
    toast("体育榜单钱包已加载");
  } catch (error) {
    toast(`发现失败：${error.message}`);
  } finally {
    button.disabled = false;
    button.textContent = "发现";
  }
}

async function copyWallet(wallet) {
  if (!wallet) return;
  await navigator.clipboard.writeText(wallet);
  toast("钱包地址已复制");
}

async function diagnose() {
  const button = $("diagnose-button");
  button.disabled = true;
  button.textContent = "诊断中";
  try {
    const result = await api("/diagnostics");
    const checks = result.checks || {};
    const walletText = result.configured_wallets
      ? `已配置 ${result.configured_wallets} 个钱包`
      : "未配置 SMART_WALLETS";
    const leaderboardText = checks.sports_leaderboard?.ok
      ? `体育榜单接口正常，返回 ${checks.sports_leaderboard.count} 个样例`
      : `体育榜单接口失败：${checks.sports_leaderboard?.error || "未知错误"}`;
    const activityText = checks.first_wallet_activity?.ok
      ? `第一个钱包读取到 ${checks.first_wallet_activity.raw_count} 条近期记录`
      : `钱包活动读取失败：${checks.first_wallet_activity?.error || "未知错误"}`;
    longToast(`${walletText}。${leaderboardText}。${activityText}。`);
  } catch (error) {
    longToast(`诊断失败：${error.message}`);
  } finally {
    button.disabled = false;
    button.textContent = "诊断";
  }
}

window.addEventListener("DOMContentLoaded", () => {
  $("refresh-button").addEventListener("click", () => refreshAll().catch((error) => toast(error.message)));
  $("scan-button").addEventListener("click", runScan);
  $("diagnose-button").addEventListener("click", diagnose);
  $("score-button").addEventListener("click", scoreWallets);
  $("discover-button").addEventListener("click", discoverWallets);
  $("discover-top-button").addEventListener("click", discoverWallets);
  $("leaderboard-list").addEventListener("click", (event) => {
    const button = event.target.closest("[data-wallet]");
    if (button) copyWallet(button.dataset.wallet).catch((error) => toast(`复制失败：${error.message}`));
  });
  $("include-closed").addEventListener("change", () => refreshAll().catch((error) => toast(error.message)));

  refreshAll().catch((error) => toast(`加载失败：${error.message}`));
  window.setInterval(() => refreshAll().catch(() => undefined), 15000);
});
