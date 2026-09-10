"""Main loop: on each closed M15 candle per symbol -> snapshot -> LLM -> journal.

Phase 1: dry-run only, decisions journaled, nothing executed.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone

from .ai_client import get_decision
from .config import load_config
from .decision_parser import parse_decision
from .journal import append_entry
from .market_data import build_snapshot
from .risk import compute_lot

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot")


def run_cycle(cfg, symbols: list[str] | None = None) -> int:
    """One pass over symbols. Returns number of cycles completed."""
    done = 0
    for sc in cfg.symbols:
        if symbols and sc.symbol not in symbols:
            continue
        snapshot = build_snapshot(sc.symbol, sc.yahoo, cfg)
        if snapshot is None:
            log.error("[%s] snapshot failed, skipping", sc.symbol)
            append_entry(cfg.journal.path, {"symbol": sc.symbol,
                                            "error": "snapshot_failed"})
            continue
        log.info("[%s] snapshot ok: last=%s atr=%s session=%s",
                 sc.symbol, snapshot["last_close"], snapshot["atr14"],
                 snapshot["session"])

        try:
            raw = get_decision(cfg, snapshot)
        except RuntimeError as e:
            log.error("[%s] LLM failed: %s", sc.symbol, e)
            append_entry(cfg.journal.path, {"symbol": sc.symbol,
                                            "error": str(e),
                                            "snapshot": snapshot["last_close"]})
            continue

        decision, skip = parse_decision(
            raw, sc.symbol, snapshot["last_close"], snapshot["atr14"],
            spread=snapshot["spread"] or 0.0,
            max_risk_pct=cfg.risk.max_risk_pct_allowed,
            min_confidence=cfg.llm.min_confidence)

        lot = 0.0
        if skip == "" and decision.action in ("BUY", "SELL"):
            lot = compute_lot(cfg.risk.equity_simulated, decision.risk_pct,
                              abs(snapshot["last_close"] - decision.sl_price))

        status = (f"[{sc.symbol}] {decision.action} conf={decision.confidence:.2f}"
                  f" lot={lot} skip={skip or '-'} reason={decision.reason[:60]}")
        print(status)

        append_entry(cfg.journal.path, {
            "symbol": sc.symbol,
            "last_close": snapshot["last_close"],
            "raw_llm": raw,
            "decision": decision.model_dump(),
            "skip_reason": skip,
            "simulated_lot": lot,
            "dry_run": cfg.trading.dry_run,
        })
        done += 1
    return done


def next_candle_sleep(interval_sec: int = 900) -> float:
    now = time.time()
    return interval_sec - (now % interval_sec) + 2  # 2s buffer for candle close


def main() -> None:
    ap = argparse.ArgumentParser(description="AI forex bot — phase 1 dry-run")
    ap.add_argument("--once", action="store_true", help="single cycle then exit")
    ap.add_argument("--symbols", nargs="*", help="subset of symbols")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--loop", action="store_true",
                    help="keep running every closed M15 candle")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if not cfg.trading.dry_run:
        log.error("phase 1 supports dry_run only — refusing to start")
        sys.exit(1)

    log.info("bot start: model=%s base=%s symbols=%s dry_run=%s",
             cfg.llm.model, cfg.llm.base_url,
             [s.symbol for s in cfg.symbols], cfg.trading.dry_run)

    if args.once or not args.loop:
        n = run_cycle(cfg, args.symbols)
        log.info("cycle done: %d symbol(s)", n)
        return

    while True:
        wait = next_candle_sleep()
        log.info("waiting %.0fs for next closed M15 candle...", wait)
        time.sleep(wait)
        try:
            run_cycle(cfg, args.symbols)
        except Exception:  # noqa: BLE001 — keep the loop alive
            log.exception("cycle crashed, continuing")


if __name__ == "__main__":
    main()
