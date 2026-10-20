# AI Forex Trading Bot — Plan

Date: 2026-09-11
Workspace: /home/aldi/experiance/trading-bot/

## Goal

Trading bot that reads market data (OHLCV + indicators), sends it to an LLM via an
**OpenAI-compatible endpoint** (configurable `base_url` + `api_token` + `model_name`),
parses a structured JSON trading decision, and executes it on a MetaTrader 5 account.

Defaults chosen (user did not answer clarifying questions):
- Python 3.11+ bot. **Phase 1 (now, Linux): market data from Yahoo Finance (yfinance) —**
  **no execution, dry-run + journal only.** **Phase 2 (later, Windows): swap to MT5 —**
  market data + execution via the MetaTrader5 python package with the MT5 terminal running.
- AI = full signal generator via **poolside/laguna** (OpenAI-compatible host), returns
  entry/SL/TP as strict JSON.
- Demo account first, then small live. Intraday M15–H1. Pairs: EURUSD, GBPUSD, XAUUSD (configurable).
- Risk per trade: 0.5–1% of equity, hard-capped daily loss at 3%.

## Architecture

```
+------------------+     +----------------+     +---------------------+
| market_data.py   | --> | ai_client.py   | --> | decision_parser.py  |
| provider-agnostic|     | POST {chat/    |     | validate JSON schema|
| snapshot builder |     | completions}   |     | clamp risk values   |
+--------+---------+     | base_url+token |     +---------------------+
         ^               +----------------+                       |
         | swaps per phase                                         v
+--------+---------+     +----------------+     +---------------------+
| yahoo_provider   |     | journal.py     | <-- | risk.py / executor  |
| yfinance OHLCV   |     | JSONL log of   |     | MT5 only (phase 2)  |
| (phase 1: Linux) |     | every decision |     | lot math, SL/TP,    |
+------------------+     +----------------+     | daily loss cap      |
+------------------+                            +---------------------+
| mt5_provider     |
| MT5 rates, ATR   |
| (phase 2: Win)   |
+------------------+

scheduler.py  = main loop: on closed M15 candle -> full cycle
config.yaml   = base_url, api_token, model_name, symbols, risk, sessions
```

Key rule: the LLM NEVER touches execution directly. It returns a decision; Python
validates, applies risk math, and executes. A malformed or dangerous LLM response
(no trade / clamped values) is the safe default.

## OpenAI-compatible client contract

```python
# ai_client.py — works with any OpenAI-compatible host. The 3 config keys are the
# only things that change per provider:
#   base_url:   poolside native:  https://api.poolside.ai/v1   (confirm in poolside docs)
#               or OpenRouter:    https://openrouter.ai/api/v1
#   api_token:  your poolside API key (Bearer), or OpenRouter key
#   model_name: e.g. "poolside/laguna-xs.2" (OpenRouter slug) or the name given by
#               your poolside endpoint / proxy — Laguna family, pick the small/cheap
#               one for 96 calls/day/pair

POST {base_url}/chat/completions
Headers: Authorization: Bearer {api_token}
Body: {
  "model": {model_name},
  "messages": [...system prompt + market snapshot...],
  "temperature": 0.2,
  "response_format": {"type": "json_object"},   # omit if host lacks it
  "max_tokens": 500
}
```

Expected decision JSON (validated with a pydantic schema, anything else = NO_TRADE):

```json
{
  "action": "BUY | SELL | CLOSE | NO_TRADE",
  "symbol": "EURUSD",
  "confidence": 0.0-1.0,
  "entry_type": "MARKET | LIMIT",
  "entry_price": null,
  "sl_price": 1.0832,
  "tp_price": 1.0910,
  "risk_pct": 0.75,
  "reason": "one-line rationale quoted in the journal"
}
```

Parser clamps: `risk_pct` to [0, configured max], SL distance to >= 1.5x spread,
confidence below threshold => NO_TRADE.

## System prompt (v1)

Role: intraday forex analyst. Input per cycle: last 100 M15 candles summary
(recent OHLCV rows), current price, spread, ATR(14), daily/session high-low,
open position if any, recent journal outcome. Output: ONLY the decision JSON.
Rules baked into prompt: trade only with session liquidity, never risk more than
allowed, always define SL, NO_TRADE is a valid and expected answer (~70% of cycles).

## Step-by-step plan

1. **Scaffold + config** — files:
   - `config.yaml` (base_url, api_token, model_name, symbols, risk_pct, max_daily_loss, session hours)
   - `bot/__init__.py`, `bot/config.py` (load + validate yaml, mask token in logs)
   - `requirements.txt`: MetaTrader5, pydantic, pyyaml, requests (or httpx), pandas
2. **ai_client.py** — single `get_decision(snapshot) -> dict` function.
   POST to `{base_url}/chat/completions`, Bearer token, retries (3x backoff),
   timeout 30s. Log request/response token counts. Unit test with a mocked host
   (local http server or requests-mock).
3. **decision_parser.py** — pydantic schema as above + clamping rules.
   Tests: valid JSON, missing fields, out-of-range risk, garbage => NO_TRADE.
4. **market_data.py** — thin provider dispatch: `get_snapshot(symbol) -> dict` contract.
   Phase 1: `yahoo_provider.py` using yfinance (`EURUSD=X`, `GBPUSD=X`, `XAUUSD=X`;
   interval="15m", 100 bars, ATR(14) via pandas, recent high/low, session hours, UTC
   timestamp). Yahoo has no spread — store 0 and let the snapshot say "phase_1: no
   spread data". Phase 2: `mt5_provider.py` — MT5 `copy_rates_from_pos`, real spread,
   account equity. No network beyond yfinance.
5. **risk.py** — lot size = (equity * risk_pct) / (sl_points * value_per_point),
   rounded to broker volume step; daily loss cap check (3% equity => stop trading
   until next day); one-position-per-symbol lock. In phase 1 with no broker equity,
   risk.py still validates SL/TP geometry and computes a *simulated* lot (journal only).
6. **executor.py** — MT5 `order_send` MARKET/LIMIT with SL/TP; `CLOSE` action
   closes matching position. **Not wired in phase 1** (no MT5 terminal on Linux);
   entry stays dry-run. This is the only file that touches a broker.
7. **journal.py** — JSONL: every cycle's snapshot hash, raw LLM text, parsed
   decision, executed ticket or skip reason. This is what you tune prompts against.
8. **scheduler.py / main.py** — loop: sleep to next closed M15 candle per symbol,
   run cycle, print one-line status (user wants visible progress, no silence).
   CLI flags: `--dry-run`, `--symbols`, `--once`, `--provider yahoo|mt5`.
9. **Phase 2 (Windows + MT5)**: install MT5 terminal + `MetaTrader5` python package,
   run `--provider mt5`; same ai_client/decision_parser/journal, now with real
   execution. Backtest harness (`backtest.py`) replays historical M15 candles
   through the same decision pipeline with simulated fills.
10. **Demo live (phase 3)** — demo account 2–4 weeks, journal vs backtest comparison,
    prompt tuning, then small live (0.25% risk) with daily-loss cap on.

## Files created

- config.yaml
- requirements.txt  (MetaTrader5, yfinance, pydantic, pyyaml, requests/httpx, pandas)
- bot/config.py, bot/ai_client.py, bot/decision_parser.py, bot/market_data.py,
  bot/yahoo_provider.py, bot/mt5_provider.py (phase 2), bot/risk.py, bot/executor.py
  (phase 2), bot/journal.py, bot/scheduler.py, main.py
- tests/test_ai_client.py, tests/test_decision_parser.py, tests/test_risk.py
- backtest.py (phase 2)

## Tests / validation

- Unit: decision parser (all malformed cases), risk math (lot rounding, cap),
  ai_client with mocked host (timeout, 401, bad JSON, rate limit).
- Integration: `--dry-run --once` against MT5 demo = full cycle, journal entry written.
- End-to-end: leave dry-run on demo for 3 days; journal shows sensible
  NO_TRADE ratio and valid SL/TP geometry before enabling order_send.

## Risks / tradeoffs

- **LLM latency/cost**: M15 cycle = 96 calls/day/pair worst case; cache NO_TRADE
  streaks, use a cheap model (Laguna XS class on OpenRouter has a :free tier, else
  poolside native), temperature 0.2.
- **Yahoo data ≠ broker data**: Yahoo has no spread, delayed-ish quotes, and its M15
  candles won't exactly match the broker's. Phase 1 decisions are signal-shape
  validation, NOT trade-ready. Journal every snapshot hash so phase 2 can diff
  provider drift.
- **MT5 package needs the MT5 terminal on the same machine** — that's why phase 2 is
  on Windows. executor.py is the only broker-touching file; data swap is isolated in
  market_data providers.
- **LLM non-determinism**: temperature 0.2 + strict JSON schema + clamping;
  journal everything for auditability.
- **Overfitting to prompt**: backtest before live; treat prompt changes like code
  changes (version them in journal).
- **Never let the AI set lot size directly** — risk.py is the single source of truth.

## Open questions (for user)

1. Poolside key via native api.poolside.ai, or OpenRouter (`poolside/laguna-xs.2:free`
   has a free tier for tuning)? base_url/token/model go in config.yaml either way.
2. Which pairs + any news filter (avoid trading 15min around red-folder events)?
3. Phase-2 broker: which one (IC Markets / Exness / other) — determines MT5 server
   + symbol names on Windows.
