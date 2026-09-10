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
