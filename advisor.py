"""Interactive AI Forex Trading Advisor CLI.

Fetches live market data + indicators for any currency pair, sends it to the AI LLM,
and formats a clean advisory summary with recommended action, timing, entry, SL, TP,
Risk-to-Reward ratio, pip distances, and technical rationale.

Usage:
  .venv/bin/python advisor.py EURUSD
  .venv/bin/python advisor.py GBPJPY
  .venv/bin/python advisor.py USDJPY --equity 5000 --risk 1.0
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from bot.ai_client import get_decision
from bot.backtest import run_backtest
from bot.config import load_config
from bot.decision_parser import parse_decision
from bot.journal import append_entry
from bot.market_data import build_snapshot
from bot.prompt import PROMPT_VERSION
from bot.risk import compute_lot


def resolve_yahoo_ticker(symbol: str, cfg) -> str:
    symbol_upper = symbol.upper().strip()
    # Check if configured in config.yaml first
    for s in cfg.symbols:
        if s.symbol.upper() == symbol_upper:
            return s.yahoo
    # Standard FX convention: add =X if not present
    if not symbol_upper.endswith("=X"):
        return f"{symbol_upper}=X"
    return symbol_upper


def format_advisor_output(symbol: str, snapshot: dict, raw_llm: str,
                          decision, skip: str, equity: float, pip_size: float = 0.0001) -> None:
    # JPY pairs use 0.01 pip size
    if "JPY" in symbol.upper():
        pip_size = 0.01

    last_price = snapshot["last_close"]
    atr = snapshot["atr14"]
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    print("\n" + "=" * 65)
    print(f"  AI FOREX ADVISOR - {symbol.upper()}")
    print(f"  Generated at: {now_utc}")
    print("=" * 65)

    print("\n[1] MARKET SNAPSHOT & INDICATORS")
    print(f"  Current Price : {last_price}")
    print(f"  Market Session: {snapshot['session'].upper()}")
    if snapshot.get("htf_trend") and snapshot.get("htf_trend") != "UNKNOWN":
        print(f"  HTF Trend (H4): {snapshot['htf_trend']}")
        print(f"  14-Day Range  : {snapshot.get('low_htf')} - {snapshot.get('high_htf')} (Price at {snapshot.get('range_pos_htf')}% of macro range)")
    print(f"  M15 Trend     : {snapshot.get('trend', 'N/A')} (EMA20: {snapshot.get('ema20')}, EMA50: {snapshot.get('ema50')})")
    print(f"  RSI(14)       : {snapshot.get('rsi14', 'N/A')}")
    print(f"  ATR(14)       : {atr}")
    print(f"  20-Bar Range  : {snapshot['low20']} - {snapshot['high20']} (Price at {snapshot.get('range_pos_pct')}% of range)")
    print(f"  Day Open      : {snapshot['day_open']}")

    print("\n[2] AI RECOMMENDATION")
    action_color = decision.action
    print(f"  Action        : >>> {action_color} <<<")
    print(f"  Confidence    : {decision.confidence * 100:.1f}%")
    print(f"  Rationale     : {decision.reason}")

    if decision.action in ("BUY", "SELL") and decision.sl_price and decision.tp_price:
        sl = decision.sl_price
        tp = decision.tp_price
        sl_dist = abs(last_price - sl)
        tp_dist = abs(tp - last_price)
        sl_pips = sl_dist / pip_size
        tp_pips = tp_dist / pip_size
        rr = (tp_dist / sl_dist) if sl_dist > 0 else 0.0
        lot = compute_lot(equity, decision.risk_pct or 0.75, sl_dist)

        print("\n[3] TRADE EXECUTION DETAILS")
        print(f"  Recommended Timing: Immediate M15 candle close (Next 0-15m)")
        print(f"  Entry Price       : ~{last_price}")
        print(f"  Stop Loss (SL)    : {sl} ({sl_pips:.1f} pips)")
        print(f"  Take Profit (TP)  : {tp} ({tp_pips:.1f} pips)")
        print(f"  Risk / Reward     : 1 : {rr:.2f}")
        print(f"  Risk Allocation   : {decision.risk_pct or 0.75}% of equity (${equity * ((decision.risk_pct or 0.75) / 100.0):.2f})")
        print(f"  Recommended Lot   : {lot} lot (based on ${equity:,.2f} balance)")
        if skip:
            print(f"  Safety Warning    : Clamped / Note: {skip}")
    else:
        print("\n[3] ADVISORY NOTE")
        if decision.action == "NO_TRADE":
            print("  Recommended Timing: STAND BY / WAIT.")
            print("  Market does not show a clear directional edge or favorable risk/reward.")
            print("  Wait for clearer breakout or pullback confirmation near key EMA/range levels.")
        elif skip:
            print(f"  Execution Gate: Filtered out due to rule: '{skip}'")

    print("\n" + "=" * 65 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI Forex Advisor — On-demand AI trade recommendation with entry, SL, TP, and timing."
    )
    parser.add_argument("symbol", help="Currency pair symbol, e.g. EURUSD, GBPJPY, USDJPY, XAUUSD")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--equity", type=float, default=None, help="Custom equity balance in USD (default from config)")
    parser.add_argument("--risk", type=float, default=None, help="Risk percentage per trade (default from config)")
    parser.add_argument("--backtest", action="store_true",
                        help="Run a historical backtest for this symbol instead of a live advisory")
    parser.add_argument("--days", type=int, default=5, help="Backtest: days of history to replay (default 5)")
    parser.add_argument("--limit", type=int, default=20, help="Backtest: max LLM calls (default 20)")
    args = parser.parse_args()

    cfg = load_config(args.config)
    equity = args.equity or cfg.risk.equity_simulated
    if args.risk:
        cfg.risk.risk_pct = args.risk

    symbol_clean = args.symbol.upper().replace("/", "").replace("-", "")

    if args.backtest:
        result = run_backtest(cfg, [symbol_clean], args.days, args.limit)
        sys.exit(0 if result["fills"] else 1)

    yahoo_ticker = resolve_yahoo_ticker(symbol_clean, cfg)

    print(f"Fetching market data for {symbol_clean} ({yahoo_ticker})...")
    snapshot = build_snapshot(symbol_clean, yahoo_ticker, cfg)
    if snapshot is None:
        print(f"Error: Unable to fetch market data for {symbol_clean} via Yahoo ({yahoo_ticker}).", file=sys.stderr)
        print("Tip: Make sure the ticker exists on Yahoo Finance (e.g. EURUSD=X, GBPJPY=X).", file=sys.stderr)
        sys.exit(1)

    print(f"Requesting AI analysis from model '{cfg.llm.model}' at {cfg.llm.base_url}...")
    try:
        raw_llm = get_decision(cfg, snapshot)
    except Exception as e:
        print(f"Error calling LLM: {e}", file=sys.stderr)
        sys.exit(1)

    decision, skip = parse_decision(
        raw_llm,
        symbol_clean,
        snapshot["last_close"],
        snapshot["atr14"],
        spread=snapshot["spread"] if snapshot["spread"] is not None else cfg.spread_for(symbol_clean),
        max_risk_pct=cfg.risk.max_risk_pct_allowed,
        min_confidence=cfg.llm.min_confidence,
        min_rr_ratio=cfg.risk.min_rr_ratio,
        rsi14=snapshot.get("rsi14"),
        range_pos_htf=snapshot.get("range_pos_htf")
    )

    format_advisor_output(symbol_clean, snapshot, raw_llm, decision, skip, equity)

    # journal the advisory so analyzer/backtest stats include manual sessions
    append_entry(cfg.journal.path, {
        "symbol": symbol_clean,
        "last_close": snapshot["last_close"],
        "raw_llm": raw_llm,
        "decision": decision.model_dump(),
        "skip_reason": skip,
        "simulated_lot": compute_lot(equity, decision.risk_pct or 0.75,
                                     abs(snapshot["last_close"] - (decision.sl_price or 0)))
        if decision.action in ("BUY", "SELL") and decision.sl_price else 0.0,
        "dry_run": cfg.trading.dry_run,
        "prompt_version": PROMPT_VERSION,
    })


if __name__ == "__main__":
    main()
