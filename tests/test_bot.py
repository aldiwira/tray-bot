"""Tests: decision parser + risk math. Run: .venv/bin/python -m pytest tests/ -q"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.decision_parser import parse_decision, extract_json  # noqa: E402
from bot.risk import compute_lot, daily_loss_allowed  # noqa: E402


def test_extract_json_plain():
    assert extract_json('{"action": "BUY"}') == {"action": "BUY"}

def test_extract_json_with_fences_and_prose():
    text = 'Here you go:\n```json\n{"action": "NO_TRADE", "symbol": "EURUSD"}\n```'
    assert extract_json(text)["action"] == "NO_TRADE"

def test_extract_json_garbage():
    assert extract_json("no json here at all") is None
    assert extract_json('{"action": ') is None


def test_parse_valid_buy():
    d, skip = parse_decision(
        '{"action":"BUY","symbol":"EURUSD","confidence":0.8,'
        '"sl_price":1.0800,"tp_price":1.0900,"risk_pct":0.8,"reason":"breakout"}',
        "EURUSD", last_price=1.0850, atr=0.0015, spread=0.0002)
    assert skip == ""
    assert d.action == "BUY"
    assert d.risk_pct == 0.8

def test_parse_risk_clamped():
    d, skip = parse_decision(
        '{"action":"SELL","symbol":"EURUSD","confidence":0.9,'
        '"sl_price":1.0900,"tp_price":1.0780,"risk_pct":5.0}',
        "EURUSD", last_price=1.0850, atr=0.0015, spread=0.0002,
        max_risk_pct=1.0)
    assert skip == ""
    assert d.risk_pct == 1.0

def test_parse_bad_sl_side():
    d, skip = parse_decision(
        '{"action":"BUY","symbol":"EURUSD","confidence":0.9,'
        '"sl_price":1.0900,"tp_price":1.0950,"risk_pct":0.5}',
        "EURUSD", last_price=1.0850, atr=0.0015, spread=0.0002)
    assert skip == "bad_sl_tp_side"

def test_parse_tp_smaller_than_sl():
    d, skip = parse_decision(
        '{"action":"BUY","symbol":"EURUSD","confidence":0.9,'
        '"sl_price":1.0800,"tp_price":1.0870,"risk_pct":0.5}',
        "EURUSD", last_price=1.0850, atr=0.0015, spread=0.0002)
    assert skip == "tp_smaller_than_sl"

def test_parse_low_confidence():
    d, skip = parse_decision(
        '{"action":"BUY","symbol":"EURUSD","confidence":0.3,'
        '"sl_price":1.0800,"tp_price":1.0900,"risk_pct":0.5}',
        "EURUSD", last_price=1.0850, atr=0.0015, spread=0.0002)
    assert "confidence" in skip

def test_parse_wrong_symbol():
    d, skip = parse_decision(
        '{"action":"BUY","symbol":"GBPUSD","confidence":0.9,'
        '"sl_price":1.0800,"tp_price":1.0900,"risk_pct":0.5}',
        "EURUSD", last_price=1.0850, atr=0.0015, spread=0.0002)
    assert skip == "wrong_symbol"

def test_parse_unparseable_falls_back():
    d, skip = parse_decision("garbage output", "EURUSD",
                             1.0850, 0.0015, 0.0002)
    assert d.action == "NO_TRADE"
    assert skip == "unparseable_llm_output"

def test_parse_no_trade_is_clean():
    d, skip = parse_decision(
        '{"action":"NO_TRADE","symbol":"EURUSD","confidence":0.7,"reason":"mid-range"}',
        "EURUSD", 1.0850, 0.0015, 0.0002)
    assert skip == ""
    assert d.action == "NO_TRADE"


def test_lot_math():
    # 10000 * 0.75% = 75 USD risk; 50 pip SL -> 75 / (50*10) = 0.15 lot
    assert compute_lot(10000, 0.75, 0.0050) == 0.15
    assert compute_lot(10000, 0.75, 0) == 0.0

def test_daily_loss_cap():
    assert daily_loss_allowed(10000, 9800, 3.0) is True    # 2% loss
    assert daily_loss_allowed(10000, 9700, 3.0) is False   # 3% loss
