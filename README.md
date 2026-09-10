# AI Forex Trading Bot

Dry-run AI trading bot: market data from Yahoo Finance (M15 candles) is sent to
**any OpenAI-compatible LLM host** (OpenAI, OpenRouter, Ollama, vLLM, LiteLLM, ...)
which returns a strict JSON trading decision (BUY / SELL / CLOSE / NO_TRADE + SL/TP).
Python validates, clamps risk, computes lot size, and journals everything. **No
execution yet** — phase 1 is signal validation only; phase 2 wires MetaTrader 5 on
Windows.

Design rule: the LLM never touches execution. It proposes; Python disposes.

## Architecture

```
yahoo_provider ──> snapshot ──> ai_client ──> decision_parser ──> risk ──> journal
(yfinance 15m)   (ATR, H/L,    (POST /chat/   (strict JSON,     (lot,    (JSONL:
                  session)      completions)   clamp, geometry)  dry)     audit trail)

scheduler.py: one cycle per closed M15 candle per symbol
```

- `bot/config.py` — pydantic config from `config.yaml`; LLM settings + API key from env or `.env`
- `bot/ai_client.py` — OpenAI-compatible client (base_url/token/model in config), 3x retry
- `bot/market_data.py` — snapshot builder (Yahoo for now; MT5 provider planned)
- `bot/decision_parser.py` — malformed/unsafe LLM output → NO_TRADE with skip_reason
- `bot/risk.py` — simulated lot math + 3% daily-loss cap
- `bot/journal.py` — every cycle appended to `journal/decisions.jsonl`
- `bot/scheduler.py` — main loop (`--once`, `--loop`, `--symbols`)

## Setup

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env   # then fill in your key; see .env.example for provider examples
```

The LLM host is fully swappable — any OpenAI-compatible endpoint works.
Set in `.env` (env beats config.yaml):

```
LLM_BASE_URL=https://api.openai.com/v1          # or openrouter, Ollama, vLLM, ...
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=your-token
```

## Commands

```bash
# single cycle, all configured symbols (EURUSD, GBPUSD, XAUUSD)
.venv/bin/python -m bot.scheduler --once

# single cycle, one symbol
.venv/bin/python -m bot.scheduler --once --symbols EURUSD

# continuous: one cycle per closed M15 candle (long-running)
.venv/bin/python -m bot.scheduler --loop

# tests (offline, fast)
.venv/bin/python -m pytest tests/ -q
```

Config lives in `config.yaml`: LLM endpoint + model (fallbacks; `.env` overrides),
symbols + Yahoo tickers, risk limits (0.75%/trade, 3% daily loss cap), sessions
(London/NY UTC hours), journal path.

## Reading results

Each cycle prints one line per symbol:

```
[EURUSD] SELL conf=0.70 lot=0.43 skip=- reason=rejection at session high
[GBPUSD] NO_TRADE conf=0.80 lot=0.00 skip=- reason=mid-range, low conviction
```

Full audit (raw LLM text, parsed decision, skip reason, simulated lot) in
`journal/decisions.jsonl` — this is the dataset for prompt tuning.

## Phase plan

- [x] **Phase 1 — Linux, Yahoo data, dry-run** (current)
  - Yahoo M15 snapshots, LLM decisions, parser/risk/journal, unit tests
- [ ] **Phase 1.5 — prompt tuning on collected journal data**
  - Run `--loop` for a few days; tune system prompt against skip_reason stats
  - Add backtest.py: replay historical candles through the same pipeline
- [ ] **Phase 2 — Windows + MT5 execution**
  - `bot/mt5_provider.py` (real spread, account equity) + `bot/executor.py`
    (order_send with SL/TP, position management)
  - Set `trading.dry_run: false`; run against a **demo account** only
- [ ] **Phase 3 — live, small**
  - Demo 2–4 weeks first; compare journal vs backtest
  - Live at 0.25% risk with daily-loss cap enforced

## Caveats

- Yahoo has no spread and its candles differ from broker feeds — phase-1
  decisions validate signal shape, not tradability.
- XAUUSD uses `GC=F` (gold futures) as a Yahoo proxy until MT5.
- `.env` and `journal/` are gitignored; never commit the API key.
