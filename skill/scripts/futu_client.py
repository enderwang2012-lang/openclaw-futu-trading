#!/usr/bin/env python3
"""Minimal FUTU client wrapper for OpenClaw integration.

This module provides a small, opinionated wrapper around `futu-api`:
- quote and trade context management
- account discovery
- account info, positions, orders, and quote snapshots
- guarded order placement

By default, real order placement is disabled unless `allow_real_orders=True`
is passed explicitly.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from futu import (
    OpenQuoteContext,
    OpenSecTradeContext,
    RET_OK,
    SecurityFirm,
    TrdEnv,
    TrdMarket,
    TrdSide,
)


class FutuClientError(RuntimeError):
    """Raised when FUTU API returns an error."""


def _enum_by_name(enum_cls, name: str):
    try:
        return getattr(enum_cls, name.upper())
    except AttributeError as exc:
        raise ValueError(f"Unsupported {enum_cls.__name__} value: {name}") from exc


def _df_to_records(df) -> List[Dict[str, Any]]:
    if hasattr(df, "to_dict"):
        return df.to_dict(orient="records")
    return [df]


@dataclass
class OrderRequest:
    code: str
    price: float
    qty: float
    side: str
    order_type: str = "NORMAL"
    remark: Optional[str] = None


class FutuClient:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 11111,
        market: str = "HK",
        env: str = "SIMULATE",
        security_firm: str = "FUTUSECURITIES",
        allow_real_orders: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.market = market.upper()
        self.env = env.upper()
        self.security_firm = security_firm.upper()
        self.allow_real_orders = allow_real_orders

        self._quote_ctx: Optional[OpenQuoteContext] = None
        self._trade_ctx: Optional[OpenSecTradeContext] = None

    def __enter__(self) -> "FutuClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    def trd_market(self):
        return _enum_by_name(TrdMarket, self.market)

    @property
    def trd_env(self):
        return _enum_by_name(TrdEnv, self.env)

    @property
    def security_firm_enum(self):
        return _enum_by_name(SecurityFirm, self.security_firm)

    def connect(self) -> None:
        if self._quote_ctx is None:
            self._quote_ctx = OpenQuoteContext(host=self.host, port=self.port)
        if self._trade_ctx is None:
            self._trade_ctx = OpenSecTradeContext(
                filter_trdmarket=self.trd_market,
                host=self.host,
                port=self.port,
                security_firm=self.security_firm_enum,
            )

    def close(self) -> None:
        if self._trade_ctx is not None:
            self._trade_ctx.close()
            self._trade_ctx = None
        if self._quote_ctx is not None:
            self._quote_ctx.close()
            self._quote_ctx = None

    def _require_quote_ctx(self) -> OpenQuoteContext:
        if self._quote_ctx is None:
            self.connect()
        return self._quote_ctx

    def _require_trade_ctx(self) -> OpenSecTradeContext:
        if self._trade_ctx is None:
            self.connect()
        return self._trade_ctx

    def _call(self, fn, *args, **kwargs):
        ret, data = fn(*args, **kwargs)
        if ret != RET_OK:
            raise FutuClientError(str(data))
        return data

    def get_global_state(self) -> Dict[str, Any]:
        return self._call(self._require_quote_ctx().get_global_state)

    def list_accounts(self) -> List[Dict[str, Any]]:
        df = self._call(self._require_trade_ctx().get_acc_list)
        return _df_to_records(df)

    def resolve_account(self, acc_id: Optional[int] = None) -> Dict[str, Any]:
        accounts = self.list_accounts()
        if not accounts:
            raise FutuClientError("No accounts returned by OpenD")
        if acc_id is not None:
            for account in accounts:
                if int(account["acc_id"]) == int(acc_id):
                    return account
            raise FutuClientError(f"Account {acc_id} not found")
        for account in accounts:
            if str(account.get("trd_env", "")).upper() == self.env:
                return account
        return accounts[0]

    def get_account_info(
        self,
        acc_id: Optional[int] = None,
        currency: str = "HKD",
    ) -> List[Dict[str, Any]]:
        account = self.resolve_account(acc_id)
        df = self._call(
            self._require_trade_ctx().accinfo_query,
            trd_env=self.trd_env,
            acc_id=int(account["acc_id"]),
            currency=currency,
        )
        return _df_to_records(df)

    def get_positions(self, acc_id: Optional[int] = None) -> List[Dict[str, Any]]:
        account = self.resolve_account(acc_id)
        df = self._call(
            self._require_trade_ctx().position_list_query,
            trd_env=self.trd_env,
            acc_id=int(account["acc_id"]),
        )
        return _df_to_records(df)

    def get_orders(
        self,
        acc_id: Optional[int] = None,
        code: str = "",
    ) -> List[Dict[str, Any]]:
        account = self.resolve_account(acc_id)
        df = self._call(
            self._require_trade_ctx().order_list_query,
            trd_env=self.trd_env,
            acc_id=int(account["acc_id"]),
            code=code,
        )
        return _df_to_records(df)

    def get_snapshot(self, codes: List[str]) -> List[Dict[str, Any]]:
        if not codes:
            raise ValueError("At least one code is required")
        df = self._call(self._require_quote_ctx().get_market_snapshot, codes)
        return _df_to_records(df)

    def place_order(
        self,
        order: OrderRequest,
        acc_id: Optional[int] = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        account = self.resolve_account(acc_id)
        payload = {
            "acc_id": int(account["acc_id"]),
            "trd_env": self.env,
            "code": order.code,
            "price": float(order.price),
            "qty": float(order.qty),
            "side": order.side.upper(),
            "order_type": order.order_type.upper(),
            "remark": order.remark,
            "dry_run": dry_run,
        }
        if dry_run:
            return {"status": "dry_run", "request": payload}
        if self.env == "REAL" and not self.allow_real_orders:
            raise FutuClientError(
                "Real order placement is disabled. Pass allow_real_orders=True to enable it."
            )

        df = self._call(
            self._require_trade_ctx().place_order,
            price=order.price,
            qty=order.qty,
            code=order.code,
            trd_side=_enum_by_name(TrdSide, order.side),
            order_type=order.order_type.upper(),
            trd_env=self.trd_env,
            acc_id=int(account["acc_id"]),
            remark=order.remark,
        )
        records = _df_to_records(df)
        return records[0] if records else {"status": "submitted"}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Minimal FUTU client CLI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=11111, type=int)
    parser.add_argument("--market", default="HK")
    parser.add_argument("--env", default="SIMULATE")
    parser.add_argument("--security-firm", default="FUTUSECURITIES")
    parser.add_argument("--allow-real-orders", action="store_true")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("state")
    subparsers.add_parser("accounts")

    account_info = subparsers.add_parser("account-info")
    account_info.add_argument("--acc-id", type=int)
    account_info.add_argument("--currency", default="HKD")

    positions = subparsers.add_parser("positions")
    positions.add_argument("--acc-id", type=int)

    orders = subparsers.add_parser("orders")
    orders.add_argument("--acc-id", type=int)
    orders.add_argument("--code", default="")

    snapshot = subparsers.add_parser("snapshot")
    snapshot.add_argument("codes", nargs="+")

    place = subparsers.add_parser("place-order")
    place.add_argument("--acc-id", type=int)
    place.add_argument("--code", required=True)
    place.add_argument("--price", type=float, required=True)
    place.add_argument("--qty", type=float, required=True)
    place.add_argument("--side", required=True, choices=["BUY", "SELL"])
    place.add_argument("--order-type", default="NORMAL")
    place.add_argument("--remark", default=None)
    place.add_argument("--execute", action="store_true")

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    with FutuClient(
        host=args.host,
        port=args.port,
        market=args.market,
        env=args.env,
        security_firm=args.security_firm,
        allow_real_orders=args.allow_real_orders,
    ) as client:
        if args.command == "state":
            result = client.get_global_state()
        elif args.command == "accounts":
            result = client.list_accounts()
        elif args.command == "account-info":
            result = client.get_account_info(acc_id=args.acc_id, currency=args.currency)
        elif args.command == "positions":
            result = client.get_positions(acc_id=args.acc_id)
        elif args.command == "orders":
            result = client.get_orders(acc_id=args.acc_id, code=args.code)
        elif args.command == "snapshot":
            result = client.get_snapshot(args.codes)
        elif args.command == "place-order":
            result = client.place_order(
                OrderRequest(
                    code=args.code,
                    price=args.price,
                    qty=args.qty,
                    side=args.side,
                    order_type=args.order_type,
                    remark=args.remark,
                ),
                acc_id=args.acc_id,
                dry_run=not args.execute,
            )
        else:
            parser.error(f"Unknown command: {args.command}")
            return 2

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
