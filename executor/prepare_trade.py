#!/usr/bin/env python3
"""Create a pending FUTU trade from explicit structured fields.

This wrapper is designed for direct OpenClaw agent use, so the agent does not
need to shell-escape a multiline proposal.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
WORKFLOW = BASE_DIR / "workflow.py"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare a pending FUTU trade from explicit fields")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--side", required=True, choices=["BUY", "SELL"])
    parser.add_argument("--qty", required=True, help="Examples: 1手, 100股, 1股")
    parser.add_argument("--price", required=True, help="Examples: 对手价, 最新价, 549.0")
    parser.add_argument("--market", required=True, help="港股 / 美股")
    parser.add_argument("--env", required=True, help="模拟盘 / 实盘")
    parser.add_argument("--remark", required=True)
    parser.add_argument("--thesis", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    proposal = "\n".join(
        [
            f"股票: {args.symbol}",
            f"操作: {'买入' if args.side.upper() == 'BUY' else '卖出'}",
            f"数量: {args.qty}",
            f"价格: {args.price}",
            f"市场: {args.market}",
            f"环境: {args.env}",
            f"备注: {args.remark}",
            f"理由: {args.thesis}",
        ]
    )

    import subprocess

    completed = subprocess.run(
        [sys.executable, str(WORKFLOW), "prepare", "--text", proposal],
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
