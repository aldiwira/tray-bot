"""Risk math + simulated lot sizing. The AI never sets lot size directly."""
from __future__ import annotations


def compute_lot(equity: float, risk_pct: float, sl_dist: float,
                pip_value_per_lot: float = 10.0) -> float:
    """Simulated lot for journaling. pip_value_per_lot: USD per lot per 1.0 price move
    is broker-specific; phase 1 uses 10 USD/lot/pip approximation for FX majors."""
    if sl_dist <= 0 or equity <= 0:
        return 0.0
    risk_usd = equity * (risk_pct / 100.0)
    # approx: pips = sl_dist / 0.0001 (FX majors), XAUUSD handled by caller override
    pips = sl_dist / 0.0001
    if pips <= 0:
        return 0.0
    return round(risk_usd / (pips * pip_value_per_lot), 2)


def daily_loss_allowed(day_start_equity: float, current_equity: float,
                       max_daily_loss_pct: float) -> bool:
    if day_start_equity <= 0:
        return True
    loss_pct = (day_start_equity - current_equity) / day_start_equity * 100.0
    return loss_pct < max_daily_loss_pct
