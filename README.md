# AI Forex Trading Bot

Dry-run-by-default AI trading bot: market data (Yahoo M15, or MetaTrader 5) is sent
to **any OpenAI-compatible LLM host** (OpenAI, OpenRouter, Ollama, vLLM, LiteLLM, ...)
which returns a strict JSON trading decision (BUY / SELL / CLOSE / NO_TRADE + SL/TP).
Python validates, clamps risk, computes lot size, optionally executes via MT5, and
journals everything.

Design rule: the LLM never touches execution. It proposes; Python disposes.

## Architecture

```
yahoo_provider / mt5_provider -> snapshot -> ai_client -> decision_parser -> risk -> executor -> journal
(yfinance 15m or MT5)           (ATR, H/L,      (POST /chat/  (strict JSON,   (lot,   (dry-run or  (JSONL:
                                session, HTF)    completions)   clamp,        dry)    MT5 order_send) audit trail)

scheduler.py: one cycle per closed M15 candle per symbol
advisor.py:   on-demand advisory (--backtest / --json / --provider)
backtest.py:  replay historical candles through the same pipeline
```

- `bot/config.py` — pydantic config from `config.yaml`; LLM settings + API key from env or `.env`
- `bot/ai_client.py` — OpenAI-compatible client (base_url/token/model in config), 3x retry
- `bot/market_data.py` — Yahoo snapshot builder (indicators + H4/14d context)
- `bot/mt5_provider.py` — MT5 bridge snapshot (real spread, account equity, positions)
- `bot/decision_parser.py` — malformed/unsafe LLM output → NO_TRADE with skip_reason
- `bot/risk.py` — simulated lot math + 3% daily-loss cap
- `bot/executor.py` — dry-run simulation or MT5 order_send (BUY/SELL/CLOSE)
- `bot/journal.py` — every cycle appended to `journal/decisions.jsonl`
- `bot/scheduler.py` — main loop (`--once`, `--loop`, `--symbols`, `--provider`, `--live`)
- `bot/prompt.py` — versioned prompts (`PROMPT_VERSION`), stamped on every journal entry
- `bot/backtest.py` — historical replay with simulated fills
- `bot/journal_analyzer.py` — action/skip/confidence stats per prompt version
- `docker/bridge.py` + `docker/docker-compose.yml` — MT5 REST bridge
- `forex_bank_symbols.json` / `.md` — reference dataset (pip size, category, central banks, active sessions)

## Setup

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt pytest

cp .env.example .env   # then fill in your key; see .env.example for provider examples
```

The LLM host is fully swappable — any OpenAI-compatible endpoint works.
Set in `.env` (env beats config.yaml):

```
LLM_BASE_URL=https://api.openai.com/v1          # or openrouter, Ollama, vLLM, ...
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=your-token
```

Phase 2 (MT5) additionally needs the bridge running and a broker login:

```bash
cd docker
docker compose up -d
# bridge listens on http://localhost:5001 (override via config.yaml trading.mt5_bridge_url)
# MT5_ACCOUNT / MT5_PASSWORD / MT5_SERVER are read by docker-compose
```

## Commands

```bash
# single cycle, all configured symbols (EURUSD, GBPUSD, AUDUSD, XAUUSD)
.venv/bin/python -m bot.scheduler --once

# single cycle, one symbol
.venv/bin/python -m bot.scheduler --once --symbols EURUSD

# continuous: one cycle per closed M15 candle (long-running)
.venv/bin/python -m bot.scheduler --loop

# override data provider for a run (yahoo is the default)
.venv/bin/python -m bot.scheduler --once --provider mt5
.venv/bin/python -m bot.scheduler --loop --provider mt5 --live   # demo execution — be careful

# on-demand AI trade advisor CLI (any symbol: EURUSD, GBPJPY, USDJPY, XAUUSD, etc.)
.venv/bin/python advisor.py EURUSD
.venv/bin/python advisor.py GBPJPY --equity 5000 --risk 1.0
.venv/bin/python advisor.py EURUSD --provider mt5
.venv/bin/python advisor.py EURUSD --json

# advisor backtest mode
.venv/bin/python advisor.py EURUSD --backtest --days 5 --limit 20

# backtest harness (replay historical candles through the same pipeline)
.venv/bin/python -m bot.backtest --days 5 --symbols EURUSD
.venv/bin/python -m bot.backtest --days 5 --limit 20

# journal stats per prompt version
.venv/bin/python -m bot.journal_analyzer
.venv/bin/python -m bot.journal_analyzer --symbol EURUSD

# tests (offline, fast)
.venv/bin/python -m pytest tests/ -q
```

Config lives in `config.yaml`: model hyperparameters (`temperature`, `max_tokens`,
`min_confidence`), symbols + Yahoo tickers, risk limits (0.75%/trade, SL/TP ATR
multipliers, 3% daily loss cap), sessions (London/NY UTC hours), default spreads,
journal path, MT5 bridge URL.
Host, model, and API key live strictly in `.env`.

## Reading results

Each scheduler cycle prints one line per symbol:

```
[EURUSD] SELL @ 1.0842 SL=1.0870 TP=1.0800 (R:R 1.4) lot=0.43 conf=0.70 skip=- reason=rejection at session high
[GBPUSD] NO_TRADE @ 1.2710 conf=0.62 skip=- reason=mid-range, low conviction
```

The advisor prints a human-readable report by default, or machine-readable JSON
with `--json`.

Full audit (raw LLM text, parsed decision, skip reason, simulated lot, execution
result) in `journal/decisions.jsonl` — this is the dataset for prompt tuning and
confidence calibration.

## Phase plan

- [x] **Phase 1 — Linux, Yahoo data, dry-run**
  - Yahoo M15 snapshots, LLM decisions, parser/risk/journal, unit tests
- [x] **Phase 1.5 — prompt tuning + backtest** (ongoing, empirical)
  - `bot/prompt.py`: versioned prompts (currently `v4`), stamped on every
    journal entry
  - `bot/backtest.py`: historical replay with simulated fills (next-bar open + spread)
  - `bot/journal_analyzer.py`: action/skip/confidence stats + confidence calibration
  - Multi-timeframe context (H4/14-day macro), market-structure Premium/Discount gates
  - HTF alignment gate, HTF range gates, RSI gates, auto-clamp of SL/TP to ATR geometry
  - 30-day backtest (2026-08-12 -> 2026-09-11): 165 decisions, 81 taken trades,
    27 wins (33% win rate); 76/81 directional trades were SELL (short bias under
    the Aug 2026 downtrend)
  - Confidence calibration: 0.75+ (122 fills) -> 42% win vs 0.55-0.65 -> 36% win;
    calibration is directionally OK but edge is not yet positive
- [~] **Phase 2 — MT5 execution (in progress, code-ready; needs Windows + broker)**
  - [x] `docker/bridge.py` — MT5 REST bridge (`/health`, `/account`, `/rates`,
    `/symbol_info`, `/positions`, `/order`, `/close`) + docker-compose
  - [x] `bot/mt5_provider.py` — real broker candles, dynamic spread, account equity,
    open-position lookup (960 bars, 14d warmup)
  - [x] `bot/executor.py` — dry-run simulation + live order_send with SL/TP
  - [x] scheduler `--provider mt5` / `--live`, advisor `--provider mt5`, `--json`
  - [ ] run against a Windows-hosted MT5 terminal with a real broker login
  - [ ] demo-account validation via `--live` / `trading.dry_run: false`
  - [ ] enforce `one_position_per_symbol` using the bridge `/positions` result
  - [ ] wire `risk.daily_loss_allowed` into the scheduler loop (cap respected)
- [ ] **Phase 3 — live, small**
  - Demo 2–4 weeks first; compare journal vs backtest
  - Live at 0.25% risk with daily-loss cap enforced

## Phase 1.5 — next levers (per backtest data)

- Edge is negative (33% win vs >= 60% needed at 1:2 R:R): review prompt bias
  (heavy SELL under Aug 2026 14-day downtrend) and revisit R:R expectations.
- Confirm confidence calibration on a *rising* market (current sample is one regime).
- Bump `PROMPT_VERSION` on any prompt change; re-run backtest; compare win rate
  per confidence bucket via `bot/journal_analyzer`.

## Caveats

- Yahoo has no spread and its candles differ from broker feeds — phase-1
  decisions validate signal shape, not tradability.
- XAUUSD uses `GC=F` (gold futures) as a Yahoo proxy until MT5.
- `.env` and `journal/` are gitignored; never commit the API key.
- `trading.dry_run: true` is the safe default. Live orders need `--live` **and**
  the MT5 provider; use a demo account first.
- `tests/` are fast and offline (34 tests, no network). Verifying the LLM call
  path needs a live key.
