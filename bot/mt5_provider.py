"""MetaTrader 5 provider for Phase 2.
Connects to the MT5 REST bridge (running in Docker or Windows) to fetch
real broker tick candles, dynamic spreads, and account equity.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
import pandas as pd
import requests

from .market_data import _session_name, compute_snapshot_metrics

log = logging.getLogger(__name__)


def check_mt5_health(base_url: str = "http://localhost:5001") -> dict:
    """Verify connection to MT5 bridge."""
    try:
        r = requests.get(f"{base_url.rstrip('/')}/health", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.error("MT5 bridge health check failed: %s", e)
        return {"status": "error", "error": str(e)}


def get_mt5_account(base_url: str = "http://localhost:5001") -> dict | None:
    """Fetch live account info (balance, equity, margin, leverage)."""
    try:
        r = requests.get(f"{base_url.rstrip('/')}/account", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.error("Failed to fetch MT5 account info: %s", e)
        return None


def build_mt5_snapshot(symbol: str, cfg) -> dict | None:
    """Fetch real candles and dynamic spread from MT5 bridge and build the snapshot dict."""
    base_url = getattr(cfg.trading, "mt5_bridge_url", "http://localhost:5001").rstrip('/')

    # 1. Fetch M15 candles
    try:
        r = requests.get(
            f"{base_url}/rates",
            params={"symbol": symbol, "timeframe": cfg.data.interval, "count": 960},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        bars = data.get("bars", [])
    except Exception as e:
        log.error("MT5 failed to fetch rates for %s: %s", symbol, e)
        return None

    if len(bars) < cfg.data.bars // 2:
        log.error("MT5 insufficient bars for %s: %d", symbol, len(bars))
        return None

    # Convert bars to pandas DataFrame
    df = pd.DataFrame(bars)
    df["Datetime"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.set_index("Datetime")
    df = df.rename(columns={
        "open": "Open", "high": "High", "low": "Low", "close": "Close",
        "tick_volume": "Volume"
    })

    # 2. Fetch live symbol info (real dynamic spread)
    spread = None
    try:
        r_sym = requests.get(f"{base_url}/symbol_info", params={"symbol": symbol}, timeout=5)
        if r_sym.status_code == 200:
            sym_info = r_sym.json()
            # Spread in price units = sym_info["spread"] * sym_info["point"]
            spread = round(sym_info["spread"] * sym_info["point"], sym_info["digits"])
    except Exception as e:
        log.warning("Could not fetch MT5 dynamic spread for %s: %s", symbol, e)

    # 3. Check for existing open position on this symbol
    open_position = None
    try:
        r_pos = requests.get(f"{base_url}/positions", params={"symbol": symbol}, timeout=5)
        if r_pos.status_code == 200:
            positions = r_pos.json().get("positions", [])
            if positions:
                p = positions[0]
                pos_type = "BUY" if p.get("type") == 0 else "SELL"
                open_position = f"{pos_type} {p.get('volume')} lots @ {p.get('price_open')} (ticket {p.get('ticket')})"
    except Exception as e:
        log.debug("Could not check MT5 open positions: %s", e)

    # Compute technical metrics with 14d warmup
    metrics = compute_snapshot_metrics(df, recent_bars=cfg.data.bars)

    now = datetime.now(timezone.utc)
    today_start = pd.Timestamp(now.date(), tz="UTC")
    day_df = df[df.index >= today_start]
    day_open = float(day_df["Open"].iloc[0]) if not day_df.empty else float(df["Open"].iloc[-1])

    return {
        "symbol": symbol,
        "time_utc": now.strftime("%Y-%m-%d %H:%M"),
        "spread": spread,
        "day_open": round(day_open, 5),
        "open_position": open_position,
        "session": _session_name(now.hour, [s.model_dump() for s in cfg.trading.sessions]),
        **metrics,
    }
