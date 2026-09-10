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
    return {"entries": len(entries), "actions": dict(actions),
            "skips": dict(skips), "avg_confidence": round(avg_conf, 3)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="journal analyzer")
    ap.add_argument("--journal", default="journal/decisions.jsonl")
    ap.add_argument("--symbol")
    ap.add_argument("--prompt-version", default=PROMPT_VERSION)
    a = ap.parse_args()
    analyze(a.journal, a.symbol, a.prompt_version)
