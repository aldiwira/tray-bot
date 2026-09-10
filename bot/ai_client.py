"""OpenAI-compatible LLM client for poolside/laguna (any compatible host works).

Reads base_url / model from config, token from POOLSIDE_API_KEY env.
"""
from __future__ import annotations

import logging

import requests

from .config import Config

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an intraday forex trading analyst. You receive a market
snapshot (recent candles summary, ATR, session high/low, open simulated position)
and must respond with ONLY a JSON object, no prose, no markdown fences:

{"action": "BUY" | "SELL" | "CLOSE" | "NO_TRADE",
 "symbol": "<the symbol you were asked about>",
 "confidence": <0.0-1.0>,
 "sl_price": <number, mandatory unless action is NO_TRADE or CLOSE>,
 "tp_price": <number, mandatory unless action is NO_TRADE or CLOSE>,
 "risk_pct": <0.25-1.0 percent of equity to risk, mandatory unless NO_TRADE/CLOSE>,
 "reason": "<one line rationale>"}

Rules:
- NO_TRADE is a valid and expected answer most of the time. Only trade when
  structure, volatility, and session timing align.
- sl_price must be on the losing side of current price; tp_price on the winning
  side, with tp distance >= sl distance.
- Never invent data you were not given.

Example decision:
{"action": "NO_TRADE", "symbol": "EURUSD", "confidence": 0.8,
 "reason": "price mid-range, no breakout, low conviction"}"""


def build_snapshot_prompt(snapshot: dict) -> str:
    """Render the market snapshot dict as compact text for the LLM."""
    lines = [f"Symbol: {snapshot['symbol']}",
             f"Time (UTC): {snapshot['time_utc']}",
             f"Current price: {snapshot['last_close']}"]
    if snapshot.get("spread") is not None:
        lines.append(f"Spread: {snapshot['spread']}")
    else:
        lines.append("Spread: unavailable in this data source")
    lines.append(f"ATR(14): {snapshot['atr14']}")
    lines.append(f"Session high/low (last 20 bars): {snapshot['high20']} / {snapshot['low20']}")
    lines.append(f"Day open: {snapshot['day_open']}")
    lines.append("Recent 10 candles (time, O, H, L, C, volume):")
    for row in snapshot["recent_candles"]:
        lines.append("  " + ", ".join(str(x) for x in row))
    pos = snapshot.get("open_position")
    lines.append(f"Open position: {pos if pos else 'none'}")
    lines.append(f"Session now: {snapshot['session']}")
    lines.append(f"Respond with the JSON decision for {snapshot['symbol']} only.")
    return "\n".join(lines)


def get_decision(cfg: Config, snapshot: dict) -> str:
    """Call the LLM, return raw text content. Raises on transport errors."""
    payload = {
        "model": cfg.llm.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_snapshot_prompt(snapshot)},
        ],
        "temperature": cfg.llm.temperature,
        "max_tokens": cfg.llm.max_tokens,
    }
    last_err = None
    for attempt in range(3):
        try:
            r = requests.post(
                f"{cfg.llm.base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {cfg.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=cfg.llm.timeout_s,
            )
            r.raise_for_status()
            data = r.json()
            usage = data.get("usage", {})
            content = data["choices"][0]["message"]["content"]
            log.info("llm call ok: usage=%s", usage)
            return content
        except (requests.RequestException, KeyError, ValueError) as e:
            last_err = e
            log.warning("llm call attempt %d failed: %s", attempt + 1, e)
    raise RuntimeError(f"LLM call failed after 3 attempts: {last_err}")
