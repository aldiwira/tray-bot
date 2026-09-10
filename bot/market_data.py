"""Market data providers. Contract: get_snapshot(symbol_cfg) -> dict.

Phase 1: yahoo_provider (yfinance). Phase 2: mt5_provider (MetaTrader5).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

log = logging.getLogger(__name__)


def _session_name(utc_hour: int, sessions: list[dict]) -> str:
    for s in sessions:
        if s["start"] <= utc_hour < s["end"]:
            return s["name"]
    return "off"


def build_snapshot(symbol: str, yahoo_ticker: str, cfg) -> dict | None:
    """Fetch bars from Yahoo and build the LLM snapshot dict."""
    import yfinance as yf

    df = yf.download(yahoo_ticker, period="5d", interval=cfg.data.interval,
                     progress=False, auto_adjust=False)
    if df is None or df.empty:
        log.error("no data for %s (%s)", symbol, yahoo_ticker)
        return None
    if isinstance(df.columns, pd.MultiIndex):  # yfinance>=0.2 multi-ticker cols
        df.columns = df.columns.get_level_values(0)
    df = df.dropna()
    if len(df) < cfg.data.bars // 2:
        log.error("insufficient bars for %s: %d", symbol, len(df))
        return None

    tail = df.tail(cfg.data.bars)
    close = float(tail["Close"].iloc[-1])
    high_low = tail["High"].rolling(14).max() - tail["Low"].rolling(14).min()
    # simple ATR(14): mean of true range proxy
    tr = pd.concat([tail["High"] - tail["Low"],
                    (tail["High"] - tail["Close"].shift()).abs(),
                    (tail["Low"] - tail["Close"].shift()).abs()], axis=1).max(axis=1)
    atr14 = float(tr.rolling(14).mean().iloc[-1])

    recent = tail.tail(10).reset_index()
    recent_rows = [
        [str(r.iloc[0])[:16], round(float(r["Open"]), 5), round(float(r["High"]), 5),
         round(float(r["Low"]), 5), round(float(r["Close"]), 5), int(r.get("Volume", 0) or 0)]
        for _, r in recent.iterrows()
    ]

    now = datetime.now(timezone.utc)
    day_df = df[df.index.tz_convert("UTC").date == now.date()] if df.index.tz is not None else df
    day_open = float(day_df["Open"].iloc[0]) if not day_df.empty else float(df["Open"].iloc[-1])

    return {
        "symbol": symbol,
        "time_utc": now.strftime("%Y-%m-%d %H:%M"),
        "last_close": round(close, 5),
        "spread": None,            # yahoo has no spread
        "atr14": round(atr14, 5),
        "high20": round(float(tail["High"].tail(20).max()), 5),
        "low20": round(float(tail["Low"].tail(20).min()), 5),
        "day_open": round(day_open, 5),
        "recent_candles": recent_rows,
        "open_position": None,     # phase 1 dry-run: no execution
        "session": _session_name(now.hour,
                                 [s.model_dump() for s in cfg.trading.sessions]),
    }
