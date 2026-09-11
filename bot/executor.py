"""Trade execution engine for Phase 2.
Translates verified decisions into broker orders via the MT5 bridge.
Supports dry-run mode (safe simulation) and live demo execution.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional
import requests

from .decision_parser import Decision

log = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    success: bool
    ticket: Optional[int] = None
    volume: float = 0.0
    price: float = 0.0
    action: str = ""
    message: str = ""


def execute_decision(
    decision: Decision,
    snapshot: dict,
    lot: float,
    cfg,
) -> ExecutionResult:
    """Execute a parsed and validated decision.

    If cfg.trading.dry_run is True, logs the trade without sending orders.
    If False, sends order to MT5 bridge.
    """
    symbol = decision.symbol.upper()
    action = decision.action.upper()
    last_price = snapshot["last_close"]

    # Safety checks
    if action not in ("BUY", "SELL", "CLOSE"):
        return ExecutionResult(success=True, action=action, message="no_action_needed")

    if action in ("BUY", "SELL") and lot <= 0.0:
        log.warning("[%s] Order skipped: calculated lot is 0.0", symbol)
        return ExecutionResult(success=False, action=action, message="zero_lot_size")

    # 1. Dry-run Mode (safe simulation)
    if cfg.trading.dry_run:
        log.info(
            "[DRY-RUN] Simulating %s %s %.2f lots @ %s (SL: %s, TP: %s, risk: %.2f%%)",
            action, symbol, lot, last_price, decision.sl_price, decision.tp_price,
            decision.risk_pct or 0.75
        )
        return ExecutionResult(
            success=True,
            ticket=999999,
            volume=lot,
            price=last_price,
            action=action,
            message="dry_run_simulated",
        )

    # 2. Live Demo Execution via MT5 bridge
    base_url = getattr(cfg.trading, "mt5_bridge_url", "http://localhost:5001").rstrip('/')

    if action == "CLOSE":
        try:
            r = requests.post(f"{base_url}/close", json={"symbol": symbol}, timeout=10)
            data = r.json()
            return ExecutionResult(
                success=data.get("success", True),
                action="CLOSE",
                message=str(data.get("closed", [])),
            )
        except Exception as e:
            log.error("[%s] Failed to close position via MT5: %s", symbol, e)
            return ExecutionResult(success=False, action="CLOSE", message=str(e))

    # Action is BUY or SELL
    payload = {
        "symbol": symbol,
        "action": action,
        "volume": float(lot),
        "sl": decision.sl_price,
        "tp": decision.tp_price,
        "comment": f"AI-{cfg.llm.model[:8]}",
    }

    try:
        r = requests.post(f"{base_url}/order", json=payload, timeout=10)
        r.raise_for_status()
        res = r.json()
        log.info(
            "[%s] MT5 ORDER FILLED: ticket=%s %s %.2f lots @ %s (SL=%s, TP=%s)",
            symbol, res.get("ticket"), action, res.get("volume", lot),
            res.get("price", last_price), decision.sl_price, decision.tp_price
        )
        return ExecutionResult(
            success=True,
            ticket=res.get("ticket"),
            volume=res.get("volume", lot),
            price=res.get("price", last_price),
            action=action,
            message="order_filled",
        )
    except Exception as e:
        log.error("[%s] MT5 order execution failed: %s", symbol, e)
        return ExecutionResult(success=False, action=action, message=str(e))
