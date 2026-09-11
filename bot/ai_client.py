"""OpenAI-compatible LLM client (works with any compatible host: OpenAI,
OpenRouter, Ollama, vLLM, LiteLLM, ...).

Reads base_url / model from config, token from LLM_API_KEY env (also loaded
from .env)."""
from __future__ import annotations

import logging

import requests

from .config import Config
from .prompt import SYSTEM_PROMPT

log = logging.getLogger(__name__)


def build_snapshot_prompt(snapshot: dict, sl_mult: float = 1.5, tp_mult: float = 2.5) -> str:
    """Render the market snapshot dict as compact text for the LLM."""
    lines = [f"Symbol: {snapshot['symbol']}",
             f"Time (UTC): {snapshot['time_utc']}",
             f"Current price: {snapshot['last_close']}"]
    if snapshot.get("spread") is not None:
        lines.append(f"Spread: {snapshot['spread']}")
    else:
        lines.append("Spread: unavailable in this data source")

    # Explicit indicator metrics for the LLM
    trend_str = snapshot.get("trend", "UNKNOWN")
    ema20 = snapshot.get("ema20", "-")
    ema50 = snapshot.get("ema50", "-")
    rsi14 = snapshot.get("rsi14", "-")
    range_pct = snapshot.get("range_pos_pct", "-")

    lines.append(f"Trend (EMA20 vs EMA50): {trend_str} (EMA20: {ema20}, EMA50: {ema50})")
    if snapshot.get("htf_trend") and snapshot.get("htf_trend") != "UNKNOWN":
        lines.append(f"Higher Timeframe (H4/14d): Trend is {snapshot['htf_trend']}, 14-day Range {snapshot.get('low_htf')} to {snapshot.get('high_htf')} (Price at {snapshot.get('range_pos_htf')}% of range)")
    lines.append(f"RSI(14): {rsi14}")
    lines.append(f"ATR(14): {snapshot['atr14']}")
    lines.append(f"20-bar Range: {snapshot['low20']} to {snapshot['high20']} (Price at {range_pct}% of range)")
    atr_val = snapshot["atr14"]
    lines.append(f"Suggested SL offset ({sl_mult}x ATR): {round(sl_mult * atr_val, 5)}, TP offset ({tp_mult}x ATR): {round(tp_mult * atr_val, 5)}")
    lines.append(f"Day open: {snapshot['day_open']}")
    lines.append(f"Session now: {snapshot['session']}")
    pos = snapshot.get("open_position")
    lines.append(f"Open position: {pos if pos else 'none'}")
    lines.append("Recent 10 candles (time, O, H, L, C, volume):")
    for row in snapshot["recent_candles"]:
        lines.append("  " + ", ".join(str(x) for x in row))
    lines.append(f"Respond with the JSON decision for {snapshot['symbol']} only.")
    return "\n".join(lines)


def get_decision(cfg: Config, snapshot: dict) -> str:
    """Call the LLM, return raw text content. Raises on transport errors."""
    prompt_text = build_snapshot_prompt(snapshot,
                                        sl_mult=cfg.risk.sl_atr_multiplier,
                                        tp_mult=cfg.risk.tp_atr_multiplier)
    payload = {
        "model": cfg.llm.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt_text},
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
            log.debug("llm call ok: usage=%s", usage)
            return content
        except (requests.RequestException, KeyError, ValueError) as e:
            last_err = e
            log.warning("llm call attempt %d failed: %s", attempt + 1, e)
    raise RuntimeError(f"LLM call failed after 3 attempts: {last_err}")
