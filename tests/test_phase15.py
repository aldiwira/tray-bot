"""Phase 1.5 tests: prompt versioning, backtest fill simulation, journal analyzer."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.backtest import df_snapshot, simulate_fill  # noqa: E402
from bot.prompt import PROMPT_VERSION, SYSTEM_PROMPT  # noqa: E402


def _mk_df(prices):
    idx = pd.date_range("2026-09-01 00:00", periods=len(prices), freq="15min", tz="UTC")
    return pd.DataFrame({"Open": prices, "High": [p + 0.001 for p in prices],
                         "Low": [p - 0.001 for p in prices],
                         "Close": prices, "Volume": [100] * len(prices)}, index=idx)


def test_prompt_version_exists():
    assert PROMPT_VERSION == "v1"
    assert "NO_TRADE" in SYSTEM_PROMPT
    # strict JSON contract present
    assert '"action"' in SYSTEM_PROMPT and '"sl_price"' in SYSTEM_PROMPT


def test_df_snapshot_shape():
    df = _mk_df([1.08 + i * 0.0001 for i in range(60)])
    snap = df_snapshot("EURUSD", df, df.index[-1].to_pydatetime(),
                       [{"name": "london", "start": 0, "end": 23}])
    assert snap["symbol"] == "EURUSD"
    assert len(snap["recent_candles"]) == 10
    assert snap["high20"] > snap["low20"]
    assert snap["session"] == "london"


def test_simulate_fill_buy_win():
    d = type("D", (), {"action": "BUY", "sl_price": 1.0800, "tp_price": 1.0900})()
    bars = _mk_df([1.0850, 1.0870, 1.0905])   # rallies to TP
    f = simulate_fill(d, 1.0850, bars)
    assert f["outcome"] == "WIN" and f["exit"] == 1.0900


def test_simulate_fill_buy_loss():
    d = type("D", (), {"action": "BUY", "sl_price": 1.0800, "tp_price": 1.0900})()
    bars = _mk_df([1.0850, 1.0830, 1.0790])   # drops through SL
    f = simulate_fill(d, 1.0850, bars)
    assert f["outcome"] == "LOSS" and f["exit"] == 1.0800


def test_simulate_fill_sell_win():
    d = type("D", (), {"action": "SELL", "sl_price": 1.0900, "tp_price": 1.0800})()
    bars = _mk_df([1.0850, 1.0820, 1.0795])   # drops to TP
    f = simulate_fill(d, 1.0850, bars)
    assert f["outcome"] == "WIN" and f["exit"] == 1.0800


def test_simulate_fill_timeout_marks_open():
    d = type("D", (), {"action": "BUY", "sl_price": 1.0700, "tp_price": 1.1000})()
    bars = _mk_df([1.0850, 1.0855, 1.0852])   # neither hit
    f = simulate_fill(d, 1.0850, bars)
    assert f["closed"] is False


def test_sl_checked_before_tp_same_bar():
    # single bar touches both SL and TP -> conservative: counts as LOSS
    d = type("D", (), {"action": "BUY", "sl_price": 1.0800, "tp_price": 1.0900})()
    idx = pd.date_range("2026-09-01 00:00", periods=2, freq="15min", tz="UTC")
    bars = pd.DataFrame({"Open": [1.0850, 1.0850], "High": [1.0860, 1.0910],
                         "Low": [1.0840, 1.0790], "Close": [1.0850, 1.0850],
                         "Volume": [100, 100]}, index=idx)
    f = simulate_fill(d, 1.0850, bars)
    assert f["outcome"] == "LOSS"
