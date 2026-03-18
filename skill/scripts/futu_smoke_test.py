#!/usr/bin/env python3
"""Minimal FUTU OpenD smoke test.

This script verifies that:
1. `futu-api` imports correctly
2. OpenD is reachable
3. Quote and trade sessions are available
4. Account list and positions can be queried

It does not place any orders.
"""

import argparse
import sys

from futu import (
    OpenQuoteContext,
    OpenSecTradeContext,
    RET_OK,
    SecurityFirm,
    TrdEnv,
    TrdMarket,
)


def parse_args():
    parser = argparse.ArgumentParser(description="FUTU OpenD smoke test")
    parser.add_argument("--host", default="127.0.0.1", help="OpenD host")
    parser.add_argument("--port", default=11111, type=int, help="OpenD port")
    parser.add_argument(
        "--market",
        default="HK",
        choices=["HK", "US", "CN", "SG", "JP", "MY", "AU", "CA"],
        help="Trade market for account and position queries",
    )
    parser.add_argument(
        "--env",
        default="REAL",
        choices=["REAL", "SIMULATE"],
        help="Trade environment",
    )
    parser.add_argument(
        "--symbol",
        default="",
        help="Optional symbol for quote snapshot, e.g. HK.00700 or US.AAPL",
    )
    parser.add_argument(
        "--security-firm",
        default="FUTUSECURITIES",
        choices=[
            "FUTUSECURITIES",
            "FUTUINC",
            "FUTUSG",
            "FUTUCA",
            "FUTUJP",
            "FUTUMY",
            "FUTUAU",
            "NONE",
        ],
        help="Broker identifier used by OpenSecTradeContext",
    )
    return parser.parse_args()


def get_enum(enum_cls, name):
    try:
        return getattr(enum_cls, name.upper())
    except AttributeError as exc:
        raise SystemExit(f"Unsupported value {name!r} for {enum_cls.__name__}") from exc


def print_section(title):
    print(f"\n=== {title} ===")


def main():
    args = parse_args()
    trd_market = get_enum(TrdMarket, args.market)
    trd_env = get_enum(TrdEnv, args.env)
    security_firm = get_enum(SecurityFirm, args.security_firm)

    quote_ctx = None
    trade_ctx = None

    try:
        print_section("Connect")
        print(f"host={args.host} port={args.port} market={args.market} env={args.env}")

        quote_ctx = OpenQuoteContext(host=args.host, port=args.port)
        ret, global_state = quote_ctx.get_global_state()
        if ret != RET_OK:
            print(f"Failed to get global state: {global_state}")
            return 1
        print("global_state:", global_state)

        trade_ctx = OpenSecTradeContext(
            filter_trdmarket=trd_market,
            host=args.host,
            port=args.port,
            security_firm=security_firm,
        )

        print_section("Accounts")
        ret, acc_df = trade_ctx.get_acc_list()
        if ret != RET_OK:
            print(f"Failed to get account list: {acc_df}")
            return 1
        print(acc_df.to_string(index=False))

        if acc_df.empty:
            print("No trading accounts returned by OpenD.")
            return 1

        preferred = acc_df[acc_df["trd_env"] == args.env]
        account_row = preferred.iloc[0] if not preferred.empty else acc_df.iloc[0]
        acc_id = int(account_row["acc_id"])
        print(f"\nUsing acc_id={acc_id} trd_env={account_row['trd_env']}")

        print_section("Positions")
        ret, pos_df = trade_ctx.position_list_query(trd_env=trd_env, acc_id=acc_id)
        if ret != RET_OK:
            print(f"Failed to get positions: {pos_df}")
            return 1
        if pos_df.empty:
            print("No positions.")
        else:
            print(pos_df.to_string(index=False))

        if args.symbol:
            print_section("Snapshot")
            ret, snap_df = quote_ctx.get_market_snapshot([args.symbol])
            if ret != RET_OK:
                print(f"Failed to get snapshot for {args.symbol}: {snap_df}")
                return 1
            print(snap_df.to_string(index=False))

        print_section("Result")
        print("Smoke test passed.")
        return 0
    finally:
        if trade_ctx is not None:
            trade_ctx.close()
        if quote_ctx is not None:
            quote_ctx.close()


if __name__ == "__main__":
    sys.exit(main())
