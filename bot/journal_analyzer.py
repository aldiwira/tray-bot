"""Phase 1.5: analyze journal decisions — action/skip stats per prompt version."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from .prompt import PROMPT_VERSION


def analyze(journal_path: str, symbol: str | None = None,
            prompt_version: str | None = None) -> dict:
    entries = []
    p = Path(journal_path)
    if not p.exists():
        print(f"no journal at {journal_path}")
        sys.exit(1)
    for line in p.read_text().splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if symbol and e.get("symbol") != symbol:
            continue
        if prompt_version and e.get("prompt_version") != prompt_version:
            continue
        if "error" in e and "decision" not in e:
            continue
        entries.append(e)

    if not entries:
        print("no matching journal entries")
        return {}

    actions = Counter(e["decision"]["action"] for e in entries if "decision" in e)
    skips = Counter(e.get("skip_reason", "") or "-" for e in entries)
    avg_conf = (sum(e["decision"]["confidence"] for e in entries
                    if "decision" in e) / len(entries))
    reasons = Counter((e["decision"].get("reason") or "")[:60]
                      for e in entries if e["decision"]["action"] == "NO_TRADE")

    print(f"entries: {len(entries)}")
    print(f"actions: {dict(actions)}")
    print(f"skip reasons: {dict(skips)}")
    print(f"avg confidence: {avg_conf:.2f}")
    print(f"top NO_TRADE reasons:")
    for r, n in reasons.most_common(5):
        print(f"  {n:4d}  {r}")

    # Confidence-calibration: does higher LLM confidence actually win more?
    buckets: dict[str, list[str]] = {}
    for e in entries:
        fill = e.get("fill") or (e.get("backtest", {}) or {}).get("fill")
        if not fill:
            continue
        outcome = fill.get("outcome")
        if outcome not in ("WIN", "LOSS"):
            continue
        conf = e["decision"]["confidence"]
        bucket = "0.55-0.65" if conf < 0.65 else ("0.65-0.75" if conf < 0.75 else "0.75+")
        buckets.setdefault(bucket, []).append(outcome)
    if buckets:
        print("\nconfidence calibration (journaled fills):")
        for b in ("0.55-0.65", "0.65-0.75", "0.75+"):
            outs = buckets.get(b)
            if outs:
                wr = outs.count("WIN") / len(outs) * 100
                print(f"  {b}: {len(outs)} fills, win rate {wr:.0f}%")
        total = [o for outs in buckets.values() for o in outs]
        print(f"  overall: {len(total)} fills, "
              f"win rate {total.count('WIN') / len(total) * 100:.0f}%")
    else:
        print("\nconfidence calibration: no journaled fill outcomes yet "
              "(run --loop / backtest to accumulate)")

    return {"entries": len(entries), "actions": dict(actions),
            "skips": dict(skips), "avg_confidence": round(avg_conf, 3),
            "calibration": {k: {"fills": len(v), "wins": v.count("WIN")}
                            for k, v in buckets.items()}}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="journal analyzer")
    ap.add_argument("--journal", default="journal/decisions.jsonl")
    ap.add_argument("--symbol")
    ap.add_argument("--prompt-version", default=PROMPT_VERSION)
    a = ap.parse_args()
    analyze(a.journal, a.symbol, a.prompt_version)
