# AGENTS.md — AI Forex Trading Bot

Phase-1 dry-run trading bot: Yahoo Finance M15 data → any OpenAI-compatible LLM
(strict JSON decisions) → strict validation → JSONL journal. No execution
wired yet (phase 2 on Windows/MT5 adds `bot/mt5_provider.py` + `bot/executor.py`).
Plan doc: `.hermes/plans/2026-09-11_110000-ai-forex-trading-bot.md`.

## Dev environment

- Python venv at `.venv/` (Python 3.13). Always use `.venv/bin/python`.
- Install: `.venv/bin/pip install -r requirements.txt pytest`
- Required env: `LLM_API_KEY`, read from `.env` (see `.env.example`). Optional
  overrides: `LLM_BASE_URL` / `LLM_MODEL` (env beats config.yaml; defaults are
  OpenAI-compatible `https://api.openai.com/v1` + `gpt-4o-mini`). Never put keys
  in config.yaml or commit `.env`.

## Run & test

- Single cycle (all symbols): `.venv/bin/python -m bot.scheduler --once`
- Subset: `.venv/bin/python -m bot.scheduler --once --symbols EURUSD`
- Continuous (one cycle per closed M15 candle): `.venv/bin/python -m bot.scheduler --loop`
- Tests: `.venv/bin/python -m pytest tests/ -q`  (13 tests, fast, no network)
- LLM call verification needs a live key; parser/journal/risk are tested offline
  with mock responses.

## Conventions

- Config: single `config.yaml` loaded through pydantic models in `bot/config.py`.
  Add new settings as model fields there, not as ad-hoc dict keys.
- LLM contract: responses are strict JSON parsed by `bot/decision_parser.py`.
  Anything invalid → NO_TRADE with a `skip_reason`. Never loosen validation to
  make a bad LLM response "work".
- Risk math lives ONLY in `bot/risk.py`; the LLM never sets lot size directly.
- Journal: every cycle appends to `journal/decisions.jsonl` (raw LLM text,
  decision, skip_reason, simulated_lot). Don't write throwaway entries into it.
- Logging: `logging` module in modules, `print()` only for the one-line per-symbol
  status in the scheduler (user wants visible progress, no silent gaps).

## Pitfalls

- `yfinance` returns MultiIndex columns for single tickers — must flatten
  (`df.columns.get_level_values(0)`) before use; already handled in
  `market_data.py`, keep it when editing.
- Yahoo has no spread (snapshot `spread=None`) and its candles differ from any
  broker feed — phase-1 decisions validate signal shape, not tradability.
- XAUUSD uses `GC=F` (gold futures) as Yahoo proxy, not a real XAUUSD quote.
- Symbol Yahoo tickers live in `config.yaml` (`EURUSD=X`, `GBPUSD=X`), not in code.
- `trading.dry_run: true` is load-bearing — scheduler exits if it's false in
  phase 1. Don't flip it until `executor.py` exists.
- Float comparisons on prices: SL/TP distance checks are sensitive to FP noise
  at equal distances; keep test fixtures unambiguous (this bit once in tests).
- Don't commit `journal/` (contains per-run decisions) or `.venv/`.
