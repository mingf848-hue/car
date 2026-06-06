# Polymarket 体育跟单助手

可部署到 Zeabur 的 Polymarket 体育预测市场跟单系统。目标是监控指定聪明钱包，只跟体育类预测市场，每次 BUY 固定跟单 `5 USDC`，并在聪明钱包 SELL 时自动卖出本系统跟买产生的本地持仓。

默认是 `dry_run` 模拟模式，不会真实下单。真实交易需要你在 Zeabur 环境变量里显式开启 `EXECUTION_MODE=live`、`ACK_TRADING_RISKS=yes` 并配置 Polymarket CLOB 密钥。

## 功能

- 监控 `SMART_WALLETS` 里的 Polymarket 钱包交易。
- 首次启动默认只做预热，不追历史单，面板会显示“首次预热”事件。
- 跟随买入开仓，跟随卖出自动平掉该 token 的本地跟单持仓。
- 每次 BUY 固定 `COPY_AMOUNT_USDC=5`。
- 首页就是中文控制台：状态、风控、持仓、事件、钱包评分、手动扫描。
- “发现钱包”会从 Polymarket 体育排行榜读取候选聪明钱包；复制地址后填入 `SMART_WALLETS` 才会真正跟踪。
- 体育市场筛选：Gamma 市场字段 -> 体育关键词 -> DeepSeek 兜底分类。
- 下单前检查当前买入/卖出价格，超过 `MAX_SLIPPAGE_BPS` 自动跳过。
- SQLite 去重、冷却时间、每日实盘最大金额控制。
- `/score-wallets` 轻量评分接口，用于筛选更像体育交易钱包的地址。
- Zeabur Dockerfile 部署。

## 目录

```text
app/
  config.py             环境变量配置
  engine.py             跟单决策核心
  executor.py           模拟 / 实盘 CLOB 下单适配器
  market_filter.py      体育市场规则 + DeepSeek 分类
  polymarket_client.py  Data API / Gamma API / CLOB price / geoblock
  scoring.py            钱包轻量评分
  main.py               FastAPI 服务入口
  static/               中文前端控制台
tests/                  无需真实密钥的核心测试
.github/workflows/      GitHub Actions CI
Dockerfile              Zeabur 部署入口
zeabur.json             Zeabur 端口配置
.env.example            环境变量样例
```

## Zeabur 部署

1. 把本项目推到 GitHub。
2. Zeabur 新建 Project，选择 GitHub 仓库。
3. 构建方式选择 Dockerfile。
4. 地区建议优先选 `Tokyo`。不要选择新加坡。是否受限以 Polymarket 官方接口实时返回为准，本程序默认会检查并在受限时停止开仓。
5. 在 Zeabur Variables 填入 `.env.example` 里的变量。
6. 启动后访问：

```text
https://你的-zeabur-域名/
https://你的-zeabur-域名/health
https://你的-zeabur-域名/events
```

## 必填环境变量

```env
SMART_WALLETS=0xSmartWallet1,0xSmartWallet2
COPY_AMOUNT_USDC=5
EXECUTION_MODE=dry_run
ACK_TRADING_RISKS=no
DEEPSEEK_API_KEY=sk-你的deepseek_key
AUTO_FOLLOW_SELLS=true
SELL_MODE=close_full_on_leader_sell
```

`SMART_WALLETS` 可以用逗号、空格、分号或换行分隔。在 Zeabur 的变量输入框里可以直接这样填：

```env
SMART_WALLETS=0x钱包1
0x钱包2
0x钱包3
```

`COPY_AMOUNT_USDC=5` 是本项目的核心规则：所有被复制的 BUY 都会按 5 USDC 走。

`SELL_MODE=close_full_on_leader_sell` 是当前自动跟卖规则：只要聪明钱包对某个 token 发出 SELL，本系统会检查自己是否曾经跟买并还有未平仓份额；如果有，就卖出这部分持仓。没有本地持仓时不会裸卖。

## 为什么扫描不到钱包

如果 Zeabur 已经部署成功，但页面看起来没有扫到钱包，优先按下面查：

1. `SMART_WALLETS` 没填或填错：控制台会出现“配置错误”。Zeabur 的 Variables 里必须填真实 Polymarket 钱包地址。
2. “扫描”和“发现”不是一回事：扫描只看 `SMART_WALLETS`；要看别人钱包，先点“发现”，复制体育榜单钱包，再填回 Zeabur Variables。
3. 第一次扫描是预热：默认 `COPY_HISTORICAL_ON_FIRST_RUN=false`，历史交易只记录不跟单，之后出现的新交易才会触发跟买/跟卖。页面事件里会显示“首次预热”。
4. 钱包近期没有交易：程序会显示“这个钱包近期没有读取到可跟踪交易”。换一个近期活跃的钱包，或等它有新交易。
5. 服务器地区受限：默认 `BLOCK_ON_GEOBLOCK=true`，如果 Polymarket 判定当前服务器地区受限或只允许平仓，程序会停止开仓并在事件里显示原因。
6. 只跟体育过滤：默认 `SPORTS_ONLY=true`，非体育市场会被跳过，事件原因会显示“不是体育市场”。
7. 地址类型不对：如果你填的是交易所地址、非 Polymarket 活跃地址、或没有公开交易记录的地址，Polymarket 数据接口可能返回空。
8. 数据接口不通：点击“诊断”，如果体育榜单接口失败，说明当前服务器访问 Polymarket 数据接口有问题，需要换 Zeabur 区域或等接口恢复。

## 实盘真实下单

先跑至少一天 `dry_run`，看 `/events` 里的跳过原因和模拟跟单是否符合预期。确认后再开启：

```env
EXECUTION_MODE=live
ACK_TRADING_RISKS=yes
POLYMARKET_PRIVATE_KEY=你的私钥
POLYMARKET_FUNDER=你的Polymarket代理钱包地址
POLYMARKET_SIGNATURE_TYPE=1或2或留空
CLOB_API_KEY=
CLOB_API_SECRET=
CLOB_API_PASSPHRASE=
DERIVE_API_KEY_IF_MISSING=true
```

如果没有填 CLOB API key，SDK 会在 `DERIVE_API_KEY_IF_MISSING=true` 时尝试从私钥派生。不要把私钥发到聊天里，只放在 Zeabur Variables 或本地 `.env`。

## 接口

### 打开控制台

```text
https://你的域名/
```

控制台包含运行模式、固定跟单金额、自动卖出状态、持仓表、事件流水、手动扫描和钱包评分。

### 查看状态

```bash
curl https://你的域名/api/status
```

### 手动扫描一次

```bash
curl -X POST https://你的域名/scan
```

### 查看事件

```bash
curl https://你的域名/events
```

### 查看本地持仓

```bash
curl https://你的域名/positions
```

### 给钱包打分

```bash
curl -X POST https://你的域名/score-wallets \
  -H 'Content-Type: application/json' \
  -d '{"wallets":["0xWallet1","0xWallet2"]}'
```

评分只是筛选辅助，不代表盈利承诺。它会参考近期交易数、体育市场占比、名义成交额、可识别 PnL 字段和活跃度。

## 本地运行

```bash
cp .env.example .env
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

本机如果是 Python `3.9.6` 会装不上 `py-clob-client-v2`，Zeabur Dockerfile 已固定 `python:3.11-slim`，部署环境没这个问题。

## 风控逻辑

- `MAX_SLIPPAGE_BPS=150`：当前价格比聪明钱包成交价贵超过 1.5% 就跳过。
- `MAX_LIVE_DAILY_USDC=50`：live 模式每天最多真实买入 50 USDC。
- `AUTO_FOLLOW_SELLS=true`：跟随聪明钱包 SELL，卖出本系统记录的本地跟单持仓。
- `SELL_MODE=close_full_on_leader_sell`：当前策略为聪明钱包一卖，本地该 token 跟单仓位全部平掉。
- `COOLDOWN_SECONDS_PER_TOKEN=120`：同一 outcome token 两分钟内只跟一次 BUY；SELL 不受 BUY 冷却影响。
- `COPY_HISTORICAL_ON_FIRST_RUN=false`：首次启动只记录已看到的旧交易，不追旧单。
- `BLOCK_ON_GEOBLOCK=true`：启动扫描时调用官方 geoblock 检查，受限或 close-only 时不做开仓。

## GitHub 自动测试

推到 GitHub 后会自动运行 `.github/workflows/ci.yml`：

```bash
python -m unittest discover -s tests
python -m compileall app tests
```

自动测试不需要真实 Polymarket 密钥，也不会发真实订单。

## 参考

- Polymarket API Docs: https://docs.polymarket.com/
- Polymarket Geographic Restrictions: https://docs.polymarket.com/api-reference/geoblock
- Polymarket CLOB Python SDK: https://pypi.org/project/py-clob-client-v2/
- DeepSeek API: https://api-docs.deepseek.com/
- Zeabur: https://zeabur.com/

## 下一步可扩展

- 自动发现 sports top traders，而不是只跟手工输入的钱包。
- 接 Telegram/Discord 推送。
- 接 n8n / Firecrawl / Tavily，把体育新闻和盘口变化做成额外信号层。
