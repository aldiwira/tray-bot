"""Phase 2 tests: MT5 provider and order execution engine."""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.decision_parser import Decision
from bot.executor import execute_decision, ExecutionResult
from bot.mt5_provider import check_mt5_health, get_mt5_account, build_mt5_snapshot


def test_executor_dry_run():
    cfg = MagicMock()
    cfg.trading.dry_run = True
    cfg.llm.model = "gpt-4o-mini"
    decision = Decision(action="BUY", symbol="EURUSD", confidence=0.8,
                        sl_price=1.0800, tp_price=1.0950, risk_pct=0.75)
    snapshot = {"last_close": 1.0850}

    res = execute_decision(decision, snapshot, lot=0.15, cfg=cfg)
    assert res.success is True
    assert res.ticket == 999999
    assert res.action == "BUY"
    assert res.volume == 0.15
    assert res.message == "dry_run_simulated"


def test_executor_no_action_needed():
    cfg = MagicMock()
    decision = Decision(action="NO_TRADE", symbol="EURUSD", confidence=0.7)
    snapshot = {"last_close": 1.0850}

    res = execute_decision(decision, snapshot, lot=0.0, cfg=cfg)
    assert res.success is True
    assert res.message == "no_action_needed"


def test_executor_zero_lot_rejected():
    cfg = MagicMock()
    decision = Decision(action="BUY", symbol="EURUSD", confidence=0.8,
                        sl_price=1.0800, tp_price=1.0950)
    snapshot = {"last_close": 1.0850}

    res = execute_decision(decision, snapshot, lot=0.0, cfg=cfg)
    assert res.success is False
    assert res.message == "zero_lot_size"


@patch("requests.post")
def test_executor_live_order_send(mock_post):
    cfg = MagicMock()
    cfg.trading.dry_run = False
    cfg.trading.mt5_bridge_url = "http://localhost:5001"
    cfg.llm.model = "gpt-4o-mini"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "success": True, "ticket": 1234567, "volume": 0.15, "price": 1.0850, "comment": "done"
    }
    mock_post.return_value = mock_resp

    decision = Decision(action="BUY", symbol="EURUSD", confidence=0.8,
                        sl_price=1.0800, tp_price=1.0950, risk_pct=0.75)
    snapshot = {"last_close": 1.0850}

    res = execute_decision(decision, snapshot, lot=0.15, cfg=cfg)
    assert res.success is True
    assert res.ticket == 1234567
    assert res.message == "order_filled"
    mock_post.assert_called_once()


@patch("requests.get")
def test_mt5_provider_health_check(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "connected", "trade_allowed": True}
    mock_get.return_value = mock_resp

    health = check_mt5_health("http://localhost:5001")
    assert health["status"] == "connected"
    assert health["trade_allowed"] is True
