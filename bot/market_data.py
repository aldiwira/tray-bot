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


def compute_snapshot_metrics(tail: pd.DataFrame, recent_bars: int = 100) -> dict:
    """Calculate technical indicators and summary metrics from candles DataFrame."""
    df = tail
    m15_tail = df.tail(recent_bars) if len(df) > recent_bars else df
    close = m15_tail["Close"]
    last_close = float(close.iloc[-1])

    # EMA20, EMA50 for trend
    ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
    ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
    if last_close > ema20 > ema50:
        trend = "BULLISH"
    elif last_close < ema20 < ema50:
        trend = "BEARISH"
    else:
        trend = "SIDEWAYS"

    # RSI(14)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean().iloc[-1]
    avg_loss = loss.rolling(14).mean().iloc[-1]
    if pd.isna(avg_loss) or avg_loss == 0:
        rsi14 = 100.0 if (not pd.isna(avg_gain) and avg_gain > 0) else 50.0
    else:
        rs = avg_gain / avg_loss
        rsi14 = 100.0 - (100.0 / (1.0 + rs))

    # ATR(14)
    tr = pd.concat([m15_tail["High"] - m15_tail["Low"],
                    (m15_tail["High"] - close.shift()).abs(),
                    (m15_tail["Low"] - close.shift()).abs()], axis=1).max(axis=1)
    atr14 = float(tr.rolling(14).mean().iloc[-1])

    high20 = float(m15_tail["High"].tail(20).max())
    low20 = float(m15_tail["Low"].tail(20).min())
    span = high20 - low20
    range_pos_pct = round(((last_close - low20) / span * 100.0), 1) if span > 0 else 50.0

    recent = m15_tail.tail(10).reset_index()
    recent_rows = [
        [str(r.iloc[0])[:16], round(float(r["Open"]), 5), round(float(r["High"]), 5),
         round(float(r["Low"]), 5), round(float(r["Close"]), 5), int(r.get("Volume", 0) or 0)]
        for _, r in recent.iterrows()
    ]

    # HTF metrics (14-day / macro context from full df)
    high_htf = round(float(df["High"].max()), 5)
    low_htf = round(float(df["Low"].min()), 5)
    span_htf = high_htf - low_htf
    range_pos_htf = round(((last_close - low_htf) / span_htf * 100.0), 1) if span_htf > 0 else 50.0

    htf_trend = "UNKNOWN"
    if len(df) >= 30:
        h4 = df.resample("4h").agg({"Close": "last"}).dropna()
        if len(h4) >= 20:
            h4_e20 = float(h4["Close"].ewm(span=20, adjust=False).mean().iloc[-1])
            h4_e50 = float(h4["Close"].ewm(span=50, adjust=False).mean().iloc[-1]) if len(h4) >= 50 else None
            if h4_e50 is not None:
                htf_trend = "BULLISH" if last_close > h4_e20 > h4_e50 else ("BEARISH" if last_close < h4_e20 < h4_e50 else "SIDEWAYS")
            else:
                htf_trend = "BULLISH" if last_close > h4_e20 else "BEARISH"

    return {
        "last_close": round(last_close, 5),
        "trend": trend,
        "ema20": round(ema20, 5),
        "ema50": round(ema50, 5),
        "rsi14": round(float(rsi14), 1),
        "atr14": round(atr14, 5),
        "high20": round(high20, 5),
        "low20": round(low20, 5),
        "range_pos_pct": range_pos_pct,
        "htf_trend": htf_trend,
        "high_htf": high_htf,
        "low_htf": low_htf,
        "range_pos_htf": range_pos_htf,
        "recent_candles": recent_rows,
    }


def build_snapshot(symbol: str, yahoo_ticker: str, cfg) -> dict | None:
    """Fetch bars from Yahoo and build the LLM snapshot dict."""
    import yfinance as yf

    period = getattr(cfg.data, "period", "14d")
    df = yf.download(yahoo_ticker, period=period, interval=cfg.data.interval,
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

    metrics = compute_snapshot_metrics(df, recent_bars=cfg.data.bars)

    now = datetime.now(timezone.utc)
    day_df = df[df.index.tz_convert("UTC").date == now.date()] if df.index.tz is not None else df
    day_open = float(day_df["Open"].iloc[0]) if not day_df.empty else float(df["Open"].iloc[-1])

    return {
        "symbol": symbol,
        "time_utc": now.strftime("%Y-%m-%d %H:%M"),
        "spread": None,            # yahoo has no spread
        "day_open": round(day_open, 5),
        "open_position": None,     # phase 1 dry-run: no execution
        "session": _session_name(now.hour,
                                 [s.model_dump() for s in cfg.trading.sessions]),
        **metrics,
    }
