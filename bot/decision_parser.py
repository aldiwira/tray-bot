"""Parse + clamp LLM decision JSON. Anything invalid => NO_TRADE (safe default)."""
from __future__ import annotations

import json
import logging
import re

from pydantic import BaseModel, Field, ValidationError, field_validator

log = logging.getLogger(__name__)

VALID_ACTIONS = {"BUY", "SELL", "CLOSE", "NO_TRADE"}


class Decision(BaseModel):
    action: str
    symbol: str
    confidence: float = 0.0
    sl_price: float | None = None
    tp_price: float | None = None
    risk_pct: float | None = None
    reason: str = ""

    @field_validator("action")
    @classmethod
    def _action(cls, v: str) -> str:
        v = v.upper().strip()
        if v not in VALID_ACTIONS:
            raise ValueError(f"invalid action {v}")
        return v

    @field_validator("confidence")
    @classmethod
    def _conf(cls, v: float) -> float:
        return min(max(float(v), 0.0), 1.0)


def extract_json(text: str) -> dict | None:
    """Find the first JSON object in the response (handles stray prose/fences)."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def parse_decision(raw_text: str, symbol: str, last_price: float,
                   atr: float, spread: float,
                   max_risk_pct: float = 1.0,
                   min_confidence: float = 0.55) -> tuple[Decision, str]:
    """Returns (decision, skip_reason). skip_reason '' means actionable."""
    obj = extract_json(raw_text)
    if obj is None:
        return _no_trade(symbol), "unparseable_llm_output"

    try:
        d = Decision(**{k: v for k, v in obj.items()
                        if k in Decision.model_fields})
    except ValidationError as e:
        log.warning("decision schema invalid: %s", e)
        return _no_trade(symbol), "invalid_schema"

    if d.symbol.upper() != symbol.upper():
        return d, "wrong_symbol"
    if d.action == "NO_TRADE":
        return d, ""
    if d.action == "CLOSE":
        return d, ""
    if d.confidence < min_confidence:
        return d, f"confidence {d.confidence:.2f} < {min_confidence}"

    # Directional trade: enforce SL/TP geometry + clamp risk
    if d.sl_price is None or d.tp_price is None:
        return d, "missing_sl_or_tp"
    if d.action == "BUY":
        if d.sl_price >= last_price or d.tp_price <= last_price:
            return d, "bad_sl_tp_side"
    if d.action == "SELL":
        if d.sl_price <= last_price or d.tp_price >= last_price:
            return d, "bad_sl_tp_side"

    sl_dist = abs(last_price - d.sl_price)
    tp_dist = abs(d.tp_price - last_price)
    if tp_dist < sl_dist:
        return d, "tp_smaller_than_sl"
    if sl_dist < 1.5 * max(spread, atr * 0.1):
        return d, "sl_too_tight"

    d.risk_pct = min(max(d.risk_pct or 0.5, 0.1), max_risk_pct)
    return d, ""


def _no_trade(symbol: str) -> Decision:
    return Decision(action="NO_TRADE", symbol=symbol, confidence=0.0,
                    reason="parser fallback")
