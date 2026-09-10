"""Phase 1.5 backtest: replay historical M15 candles through the same decision
pipeline (snapshot -> LLM -> parser -> risk) with simulated fills at next bar
open + spread. LLM calls dominate runtime; --limit / --symbols bound them.

Usage:
  LLM_API_KEY=... .venv/bin/python -m bot.backtest --days 5 --symbols EURUSD
"""
from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from .ai_client import get_decision
from .config import load_config
from .decision_parser import parse_decision
from .market_data import _session_name
from .prompt import PROMPT_VERSION
from .risk import compute_lot

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("backtest")


def df_snapshot(symbol: str, tail: pd.DataFrame, now: datetime, sessions) -> dict:
    """Snapshot from an in-memory candle frame (same shape as live provider)."""
    close = float(tail["Close"].iloc[-1])
    tr = pd.concat([tail["High"] - tail["Low"],
                    (tail["High"] - tail["Close"].shift()).abs(),
                    (tail["Low"] - tail["Close"].shift()).abs()], axis=1).max(axis=1)
    recent = tail.tail(10).reset_index()
    recent_rows = [
        [str(r.iloc[0])[:16], round(float(r["Open"]), 5), round(float(r["High"]), 5),
         round(float(r["Low"]), 5), round(float(r["Close"]), 5), int(r.get("Volume", 0) or 0)]
        for _, r in recent.iterrows()
    ]
    return {
        "symbol": symbol,
        "time_utc": now.strftime("%Y-%m-%d %H:%M"),
        "last_close": round(close, 5),
        "spread": None,
        "atr14": round(float(tr.rolling(14).mean().iloc[-1]), 5),
        "high20": round(float(tail["High"].tail(20).max()), 5),
        "low20": round(float(tail["Low"].tail(20).min()), 5),
        "day_open": round(float(tail["Open"].iloc[0]), 5),
        "recent_candles": recent_rows,
        "open_position": None,
        "session": _session_name(now.hour, sessions),
    }


def simulate_fill(decision, entry_price: float, bars_after: pd.DataFrame,
                  spread: float = 0.0002) -> dict:
    """Walk forward until SL or TP hits (checked against bar High/Low)."""
    sl, tp = decision.sl_price, decision.tp_price
    if decision.action == "BUY":
        entry = entry_price + spread  # pay spread on entry
    else:
        entry = entry_price - spread
    for ts, bar in bars_after.iterrows():
        if decision.action == "BUY":
            if bar["Low"] <= sl:
                return {"outcome": "LOSS", "exit": sl, "ts": str(ts)[:16]}
            if bar["High"] >= tp:
                return {"outcome": "WIN", "exit": tp, "ts": str(ts)[:16]}
        else:
            if bar["High"] >= sl:
                return {"outcome": "LOSS", "exit": sl, "ts": str(ts)[:16]}
            if bar["Low"] <= tp:
                return {"outcome": "WIN", "exit": tp, "ts": str(ts)[:16]}
    last = float(bars_after["Close"].iloc[-1])
    pnl = (last - entry) if decision.action == "BUY" else (entry - last)
    return {"outcome": "OPEN" if pnl > 0 else "LOSS", "exit": last,
            "ts": str(bars_after.index[-1])[:16], "closed": False}


def run_backtest(cfg, symbols: list[str] | None, days: int, limit: int) -> dict:
    import yfinance as yf

    results = []
    sessions = [s.model_dump() for s in cfg.trading.sessions]
    for sc in cfg.symbols:
        if symbols and sc.symbol not in symbols:
            continue
        df = yf.download(sc.yahoo, period=f"{days + 2}d", interval=cfg.data.interval,
                         progress=False, auto_adjust=False)
        if df is None or df.empty:
            log.error("no data for %s", sc.symbol)
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.dropna()
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")

        window = df[df.index >= df.index.max() - timedelta(days=days)]
        positions = window.index[::cfg.data.bars // 2]  # step through non-overlapping
        if limit:
            positions = positions[:limit]

        for i, ts in enumerate(positions):
            idx = window.index.get_loc(ts)
            tail = window.iloc[max(0, idx - cfg.data.bars):idx + 1]
            if len(tail) < cfg.data.bars // 2:
                continue
            snap = df_snapshot(sc.symbol, tail, ts.to_pydatetime(), sessions)
            try:
                raw = get_decision(cfg, snap)
            except RuntimeError as e:
                log.error("%s @ %s: LLM failed: %s", sc.symbol, ts, e)
                continue
            decision, skip = parse_decision(
                raw, sc.symbol, snap["last_close"], snap["atr14"], 0.0,
                cfg.risk.max_risk_pct_allowed, cfg.llm.min_confidence)
            entry = {"symbol": sc.symbol, "ts": str(ts)[:16],
                     "prompt_version": PROMPT_VERSION, "raw_llm": raw,
                     "decision": decision.model_dump(), "skip_reason": skip}
            if skip == "" and decision.action in ("BUY", "SELL") and decision.sl_price:
                rest = window.iloc[idx + 1: idx + 1 + 48]  # max 12h hold
                if len(rest):
                    fill = simulate_fill(decision, snap["last_close"], rest)
                    lot = compute_lot(cfg.risk.equity_simulated, decision.risk_pct,
                                      abs(snap["last_close"] - decision.sl_price))
                    fill["simulated_lot"] = lot
                    entry["fill"] = fill
                    mark = "WIN" if fill["outcome"] == "WIN" else "LOSS"
                    print(f"[{sc.symbol}] {entry['ts']} {decision.action} "
                          f"conf={decision.confidence:.2f} -> {mark} "
                          f"(exit {fill['exit']} @ {fill['ts']})")
            else:
                print(f"[{sc.symbol}] {entry['ts']} {decision.action} "
                      f"conf={decision.confidence:.2f} skip={skip or '-'}")
            results.append(entry)
            time.sleep(0.5)  # be gentle with the API

    # summary
    fills = [r["fill"] for r in results if "fill" in r]
    wins = sum(1 for f in fills if f["outcome"] == "WIN")
    print("\n=== BACKTEST SUMMARY ===")
    print(f"decisions: {len(results)}, taken: {len(fills)}, "
          f"wins: {wins}, losses: {len(fills) - wins}, "
          f"win rate: {wins / len(fills) * 100:.0f}%" if fills else
          "no trades taken")
    return {"decisions": len(results), "fills": fills}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="backtest harness (phase 1.5)")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--symbols", nargs="*")
    ap.add_argument("--days", type=int, default=5)
    ap.add_argument("--limit", type=int, default=20, help="max LLM calls per symbol")
    a = ap.parse_args()
    cfg = load_config(a.config)
    run_backtest(cfg, a.symbols, a.days, a.limit)
