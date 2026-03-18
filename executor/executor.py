#!/usr/bin/env python3
"""Thin FUTU execution gateway for OpenClaw-generated trade plans.

OpenClaw should use its own model stack to decide:
- symbol
- side
- quantity
- price or pricing mode
- rationale

This script only validates and executes through FUTU OpenD.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


class ExecutionError(RuntimeError):
    """Raised when validation or FUTU execution fails."""


def enum_by_name(enum_cls, name: str):
    try:
        return getattr(enum_cls, name.upper())
    except AttributeError as exc:
        raise ExecutionError(f"Unsupported {enum_cls.__name__} value: {name}") from exc


def to_records(df) -> List[Dict[str, Any]]:
    if hasattr(df, "to_dict"):
        return df.to_dict(orient="records")
    return [df]


@dataclass
class TradeInstruction:
    symbol: str
    side: str
    qty: float
    qty_unit: str = "SHARE"
    price: Optional[float] = None
    price_mode: str = "MANUAL"
    market: str = "US"
    env: str = "SIMULATE"
    order_type: str = "NORMAL"
    acc_id: Optional[int] = None
    remark: Optional[str] = None
    thesis: Optional[str] = None


class FutuExecutor:
    def __init__(
        self,
        host: str,
        port: int,
        security_firm: str = "FUTUSECURITIES",
        allow_real_orders: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.security_firm = security_firm.upper()
        self.allow_real_orders = allow_real_orders
        self._quote_ctx = None
        self._trade_ctx = None

    def __enter__(self) -> "FutuExecutor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _import_futu(self):
        try:
            from futu import (  # type: ignore
                OpenQuoteContext,
                OpenSecTradeContext,
                RET_OK,
                SecurityFirm,
                TrdEnv,
                TrdMarket,
                TrdSide,
            )
        except ModuleNotFoundError as exc:
            raise ExecutionError(
                "Missing `futu-api` in this Python environment. Install it with `pip install futu-api`."
            ) from exc

        return {
            "OpenQuoteContext": OpenQuoteContext,
            "OpenSecTradeContext": OpenSecTradeContext,
            "RET_OK": RET_OK,
            "SecurityFirm": SecurityFirm,
            "TrdEnv": TrdEnv,
            "TrdMarket": TrdMarket,
            "TrdSide": TrdSide,
        }

    def _connect(self, market: str) -> None:
        futu = self._import_futu()
        if self._quote_ctx is None:
            self._quote_ctx = futu["OpenQuoteContext"](host=self.host, port=self.port)
        if self._trade_ctx is None:
            self._trade_ctx = futu["OpenSecTradeContext"](
                filter_trdmarket=enum_by_name(futu["TrdMarket"], market),
                host=self.host,
                port=self.port,
                security_firm=enum_by_name(futu["SecurityFirm"], self.security_firm),
            )

    def close(self) -> None:
        if self._trade_ctx is not None:
            self._trade_ctx.close()
            self._trade_ctx = None
        if self._quote_ctx is not None:
            self._quote_ctx.close()
            self._quote_ctx = None

    def _call(self, fn, *args, **kwargs):
        futu = self._import_futu()
        ret, data = fn(*args, **kwargs)
        if ret != futu["RET_OK"]:
            raise ExecutionError(str(data))
        return data

    def get_global_state(self, market: str) -> Dict[str, Any]:
        self._connect(market)
        return self._call(self._quote_ctx.get_global_state)

    def list_accounts(self, market: str) -> List[Dict[str, Any]]:
        self._connect(market)
        return to_records(self._call(self._trade_ctx.get_acc_list))

    def resolve_account(
        self,
        market: str,
        env: str,
        acc_id: Optional[int],
    ) -> Dict[str, Any]:
        accounts = self.list_accounts(market)
        if acc_id is not None:
            for account in accounts:
                if int(account["acc_id"]) == int(acc_id):
                    return account
            raise ExecutionError(f"Account {acc_id} not found")

        for account in accounts:
            if (
                str(account.get("trd_env", "")).upper() == env.upper()
                and market.upper() in list(account.get("trdmarket_auth", []))
                and str(account.get("acc_status", "")).upper() == "ACTIVE"
            ):
                return account

        raise ExecutionError(f"No ACTIVE {env.upper()} account with {market.upper()} permission was found")

    def get_snapshot(self, market: str, symbol: str) -> Dict[str, Any]:
        self._connect(market)
        rows = to_records(self._call(self._quote_ctx.get_market_snapshot, [symbol]))
        if not rows:
            raise ExecutionError(f"No snapshot returned for {symbol}")
        return rows[0]

    def ensure_regular_session(self, market: str) -> str:
        state = self.get_global_state(market)
        key_map = {
            "HK": "market_hk",
            "US": "market_us",
            "CN": "market_sh",
        }
        state_key = key_map.get(market.upper())
        if not state_key:
            return "UNKNOWN"

        market_state = str(state.get(state_key, "UNKNOWN")).upper()
        allowed_states = {"MORNING", "AFTERNOON"}
        if market_state not in allowed_states:
            raise ExecutionError(
                f"{market.upper()} market is not in a regular trading session ({market_state}). "
                "After-hours, pre-market, auction, and closed sessions are blocked."
            )
        return market_state

    def place_order(self, instruction: TradeInstruction, dry_run: bool) -> Dict[str, Any]:
        self._connect(instruction.market)
        account = self.resolve_account(instruction.market, instruction.env, instruction.acc_id)
        session_state = self.ensure_regular_session(instruction.market)
        snapshot = self.get_snapshot(instruction.market, instruction.symbol)
        actual_qty = resolve_actual_qty(instruction, snapshot)
        selected_price = resolve_price(instruction, snapshot)

        payload = {
            "symbol": instruction.symbol,
            "side": instruction.side.upper(),
            "qty": float(actual_qty),
            "requested_qty": float(instruction.qty),
            "qty_unit": instruction.qty_unit.upper(),
            "price": selected_price,
            "price_mode": instruction.price_mode.upper(),
            "market": instruction.market.upper(),
            "env": instruction.env.upper(),
            "order_type": instruction.order_type.upper(),
            "acc_id": int(account["acc_id"]),
            "remark": instruction.remark,
            "thesis": instruction.thesis,
            "snapshot": {
                "bid_price": snapshot.get("bid_price"),
                "ask_price": snapshot.get("ask_price"),
                "last_price": snapshot.get("last_price"),
                "lot_size": snapshot.get("lot_size"),
            },
            "session_state": session_state,
            "dry_run": dry_run,
        }

        if dry_run:
            return {"status": "dry_run", "request": payload}

        if instruction.env.upper() == "REAL" and not self.allow_real_orders:
            raise ExecutionError(
                "REAL order placement is blocked. Set OPENCLAW_FUTU_ALLOW_REAL=YES and pass --execute-real."
            )

        futu = self._import_futu()
        trd_env = enum_by_name(futu["TrdEnv"], instruction.env)
        trd_side = enum_by_name(futu["TrdSide"], instruction.side)

        df = self._call(
            self._trade_ctx.place_order,
            price=selected_price,
            qty=actual_qty,
            code=instruction.symbol,
            trd_side=trd_side,
            order_type=instruction.order_type.upper(),
            trd_env=trd_env,
            acc_id=int(account["acc_id"]),
            remark=instruction.remark,
        )
        rows = to_records(df)
        return {
            "status": "submitted",
            "request": payload,
            "broker_response": rows[0] if rows else {},
        }


def resolve_price(instruction: TradeInstruction, snapshot: Dict[str, Any]) -> float:
    mode = instruction.price_mode.upper()
    if mode == "MANUAL":
        if instruction.price is None:
            raise ExecutionError("`price` is required when price_mode=MANUAL")
        return float(instruction.price)
    if mode == "ASK":
        return float(snapshot.get("ask_price") or snapshot.get("last_price"))
    if mode == "BID":
        return float(snapshot.get("bid_price") or snapshot.get("last_price"))
    if mode == "LAST":
        return float(snapshot.get("last_price"))
    raise ExecutionError(f"Unsupported price_mode: {instruction.price_mode}")


def resolve_actual_qty(instruction: TradeInstruction, snapshot: Dict[str, Any]) -> float:
    unit = instruction.qty_unit.upper()
    qty = float(instruction.qty)
    if unit == "LOT":
        if qty > 1:
            raise ExecutionError("Risk control: quantity may not exceed 1 lot per trade")
        lot_size = float(snapshot.get("lot_size") or 1)
        return qty * lot_size
    if unit == "CONTRACT":
        if qty > 1:
            raise ExecutionError("Risk control: quantity may not exceed 1 contract per trade")
        return qty
    if unit == "SHARE":
        if qty > 1:
            raise ExecutionError("Risk control: quantity may not exceed 1 share per trade")
        return qty
    raise ExecutionError(f"Unsupported qty_unit: {instruction.qty_unit}")


def validate_instruction(raw: Dict[str, Any]) -> TradeInstruction:
    missing = [field for field in ["symbol", "side", "qty"] if field not in raw]
    if missing:
        raise ExecutionError(f"Missing required fields: {', '.join(missing)}")

    side = str(raw["side"]).upper()
    if side not in {"BUY", "SELL"}:
        raise ExecutionError("`side` must be BUY or SELL")

    qty = float(raw["qty"])
    if qty <= 0:
        raise ExecutionError("`qty` must be greater than 0")

    return TradeInstruction(
        symbol=str(raw["symbol"]).upper(),
        side=side,
        qty=qty,
        qty_unit=str(raw.get("qty_unit", "SHARE")).upper(),
        price=float(raw["price"]) if raw.get("price") is not None else None,
        price_mode=str(raw.get("price_mode", "MANUAL")).upper(),
        market=str(raw.get("market", "US")).upper(),
        env=str(raw.get("env", "SIMULATE")).upper(),
        order_type=str(raw.get("order_type", "NORMAL")).upper(),
        acc_id=int(raw["acc_id"]) if raw.get("acc_id") is not None else None,
        remark=raw.get("remark"),
        thesis=raw.get("thesis"),
    )


def read_instruction(args: argparse.Namespace) -> Dict[str, Any]:
    if args.input_json:
        return json.loads(args.input_json)
    if args.input_file:
        with open(args.input_file, "r", encoding="utf-8") as fh:
            return json.load(fh)
    if not sys.stdin.isatty():
        return json.load(sys.stdin)
    raise ExecutionError("Provide --input-json, --input-file, or pipe JSON on stdin")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenClaw FUTU execution gateway")
    parser.add_argument("--input-json", help="Trade instruction as a JSON string")
    parser.add_argument("--input-file", help="Path to a JSON trade instruction file")
    parser.add_argument("--host", default=os.getenv("FUTU_OPEND_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("FUTU_OPEND_PORT", "11111")))
    parser.add_argument("--security-firm", default=os.getenv("FUTU_SECURITY_FIRM", "FUTUSECURITIES"))
    parser.add_argument("--execute-real", action="store_true", help="Actually place the order")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    raw = read_instruction(args)
    instruction = validate_instruction(raw)

    # Keep REAL trades behind both an explicit flag and an env var.
    allow_real = os.getenv("OPENCLAW_FUTU_ALLOW_REAL") == "YES"
    dry_run = not args.execute_real
    if instruction.env == "REAL" and args.execute_real and not allow_real:
        raise ExecutionError(
            "REAL order placement is blocked. Set OPENCLAW_FUTU_ALLOW_REAL=YES before using --execute-real."
        )

    with FutuExecutor(
        host=args.host,
        port=args.port,
        security_firm=args.security_firm,
        allow_real_orders=allow_real,
    ) as executor:
        result = {
            "instruction": raw,
            "validated_instruction": instruction.__dict__,
            "global_state": executor.get_global_state(instruction.market),
            "selected_account": executor.resolve_account(instruction.market, instruction.env, instruction.acc_id),
            "result": executor.place_order(instruction, dry_run=dry_run),
        }

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ExecutionError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(1)
