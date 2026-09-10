"""JSONL journal: every cycle's raw LLM output + parsed decision + skip reason."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def append_entry(journal_path: str, entry: dict) -> None:
    p = Path(journal_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": datetime.now(timezone.utc).isoformat(), **entry}
    with open(p, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def read_entries(journal_path: str, symbol: str | None = None) -> list[dict]:
    p = Path(journal_path)
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if symbol is None or e.get("symbol") == symbol:
            out.append(e)
    return out
