"""Lightweight MT5 REST Bridge (runs inside Wine/Windows container).
Exposes official MetaTrader5 Python API via HTTP endpoints.
"""
from __future__ import annotations

import os
import logging
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import MetaTrader5 as mt5

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("mt5_bridge")

app = FastAPI(title="MT5 Bridge API", version="1.0.0")

TIMEFRAME_MAP = {
    "1m": mt5.TIMEFRAME_M1,
    "5m": mt5.TIMEFRAME_M5,
    "15m": mt5.TIMEFRAME_M15,
    "30m": mt5.TIMEFRAME_M30,
    "1h": mt5.TIMEFRAME_H1,
    "4h": mt5.TIMEFRAME_H4,
    "1d": mt5.TIMEFRAME_D1,
}


class OrderRequest(BaseModel):
    symbol: str
    action: str  # BUY | SELL
    volume: float  # lots
    sl: Optional[float] = None
    tp: Optional[float] = None
    deviation: int = 20
    comment: str = "AI-Bot"


class CloseRequest(BaseModel):
    symbol: Optional[str] = None
    ticket: Optional[int] = None


@app.on_event("startup")
def startup():
    account = os.getenv("MT5_ACCOUNT")
    password = os.getenv("MT5_PASSWORD")
    server = os.getenv("MT5_SERVER")

    log.info("Initializing MetaTrader 5 connection...")
    if account and password and server:
        initialized = mt5.initialize(
            login=int(account),
            password=password,
            server=server
        )
    else:
        # Default initialize (connects to already running terminal)
        initialized = mt5.initialize()

    if not initialized:
        err = mt5.last_error()
        log.error("Failed to initialize MT5: %s", err)
    else:
        terminal_info = mt5.terminal_info()
        log.info("MT5 initialized successfully: %s", terminal_info)


@app.get("/health")
def health():
    terminal_info = mt5.terminal_info()
    if terminal_info is None:
        return {"status": "error", "error": mt5.last_error()}
    return {
        "status": "connected" if terminal_info.connected else "disconnected",
        "trade_allowed": terminal_info.trade_allowed,
        "name": terminal_info.name,
        "path": terminal_info.path,
    }


@app.get("/account")
def get_account():
    acc = mt5.account_info()
    if acc is None:
        raise HTTPException(status_code=500, detail=f"Failed to get account info: {mt5.last_error()}")
    return acc._asdict()


@app.get("/symbol_info")
def get_symbol_info(symbol: str):
    sym = mt5.symbol_info(symbol.upper())
    if sym is None:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found: {mt5.last_error()}")
    return {
        "symbol": sym.name,
        "bid": sym.bid,
        "ask": sym.ask,
        "spread": sym.spread,
        "point": sym.point,
        "digits": sym.digits,
        "trade_contract_size": sym.trade_contract_size,
    }


@app.get("/rates")
def get_rates(symbol: str, timeframe: str = "15m", count: int = 100):
    tf = TIMEFRAME_MAP.get(timeframe.lower())
    if tf is None:
        raise HTTPException(status_code=400, detail=f"Invalid timeframe {timeframe}")

    symbol_clean = symbol.upper()
    # Ensure symbol is visible in Market Watch
    if not mt5.symbol_select(symbol_clean, True):
        raise HTTPException(status_code=404, detail=f"Failed to select symbol {symbol_clean}")

    rates = mt5.copy_rates_from_pos(symbol_clean, tf, 0, count)
    if rates is None or len(rates) == 0:
        raise HTTPException(status_code=500, detail=f"Failed to copy rates: {mt5.last_error()}")

    rows = []
    for r in rates:
        rows.append({
            "time": int(r[0]),
            "open": float(r[1]),
            "high": float(r[2]),
            "low": float(r[3]),
            "close": float(r[4]),
            "tick_volume": int(r[5]),
            "spread": int(r[6]),
        })
    return {"symbol": symbol_clean, "timeframe": timeframe, "bars": rows}


@app.get("/positions")
def get_positions(symbol: Optional[str] = None):
    if symbol:
        positions = mt5.positions_get(symbol=symbol.upper())
    else:
        positions = mt5.positions_get()

    if positions is None:
        return {"positions": []}
    return {"positions": [p._asdict() for p in positions]}


@app.post("/order")
def place_order(req: OrderRequest):
    sym_info = mt5.symbol_info(req.symbol.upper())
    if sym_info is None:
        raise HTTPException(status_code=404, detail=f"Symbol {req.symbol} not found")

    action_type = req.action.upper()
    if action_type == "BUY":
        order_type = mt5.ORDER_TYPE_BUY
        price = sym_info.ask
    elif action_type == "SELL":
        order_type = mt5.ORDER_TYPE_SELL
        price = sym_info.bid
    else:
        raise HTTPException(status_code=400, detail=f"Invalid action {req.action}")

    trade_request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": req.symbol.upper(),
        "volume": float(req.volume),
        "type": order_type,
        "price": price,
        "deviation": req.deviation,
        "magic": 123456,
        "comment": req.comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    if req.sl is not None:
        trade_request["sl"] = float(req.sl)
    if req.tp is not None:
        trade_request["tp"] = float(req.tp)

    result = mt5.order_send(trade_request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        err_msg = result.comment if result else str(mt5.last_error())
        retcode = result.retcode if result else -1
        raise HTTPException(status_code=400, detail=f"Order failed (retcode={retcode}): {err_msg}")

    return {
        "success": True,
        "ticket": result.order,
        "volume": result.volume,
        "price": result.price,
        "comment": result.comment,
    }


@app.post("/close")
def close_position(req: CloseRequest):
    positions = []
    if req.ticket:
        positions = mt5.positions_get(ticket=req.ticket)
    elif req.symbol:
        positions = mt5.positions_get(symbol=req.symbol.upper())

    if not positions:
        return {"success": False, "message": "No matching position found"}

    closed = []
    for pos in positions:
        tick = mt5.symbol_info_tick(pos.symbol)
        if pos.type == mt5.ORDER_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask

        close_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": pos.ticket,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": order_type,
            "price": price,
            "deviation": 20,
            "magic": 123456,
            "comment": "AI-Bot Close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(close_request)
        closed.append({
            "ticket": pos.ticket,
            "success": res is not None and res.retcode == mt5.TRADE_RETCODE_DONE,
            "comment": res.comment if res else str(mt5.last_error())
        })

    return {"closed": closed}
