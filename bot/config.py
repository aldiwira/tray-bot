"""Config loader — single source of truth for bot settings."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


def _load_dotenv(path: str | Path = ".env") -> None:
    """Minimal .env loader: KEY=VALUE lines, quotes stripped, no export needed."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        os.environ.setdefault(key, value)


class LlmConfig(BaseModel):
    base_url: str
    model: str
    temperature: float = 0.2
    max_tokens: int = 500
    timeout_s: int = 60
    min_confidence: float = 0.55


class SymbolCfg(BaseModel):
    symbol: str
    yahoo: str


class DataConfig(BaseModel):
    provider: str = "yahoo"
    interval: str = "15m"
    bars: int = 100


class RiskConfig(BaseModel):
    equity_simulated: float = 10000.0
    risk_pct: float = 0.75
    max_daily_loss_pct: float = 3.0
    max_risk_pct_allowed: float = 1.0


class SessionCfg(BaseModel):
    name: str
    start: int
    end: int


class TradingConfig(BaseModel):
    dry_run: bool = True
    one_position_per_symbol: bool = True
    sessions: list[SessionCfg] = Field(default_factory=list)


class JournalConfig(BaseModel):
    path: str = "journal/decisions.jsonl"


class Config(BaseModel):
    llm: LlmConfig
    symbols: list[SymbolCfg]
    data: DataConfig
    risk: RiskConfig
    trading: TradingConfig
    journal: JournalConfig

    @property
    def api_key(self) -> str:
        key = os.environ.get("POOLSIDE_API_KEY", "")
        if not key:
            raise RuntimeError("POOLSIDE_API_KEY env var not set")
        return key


def load_config(path: str | Path = "config.yaml") -> Config:
    _load_dotenv()
    with open(path) as f:
        return Config(**yaml.safe_load(f))
