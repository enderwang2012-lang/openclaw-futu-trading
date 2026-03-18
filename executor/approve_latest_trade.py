#!/usr/bin/env python3
"""Approve and execute the latest pending FUTU trade.

This wrapper exists so OpenClaw can execute the approval step with a short,
predictable command.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
WORKFLOW = BASE_DIR / "workflow.py"
REAL_CONFIRM_TEXT = "EXECUTE REAL TRADE"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Approve the latest pending FUTU trade")
    parser.add_argument("--real", action="store_true", help="Execute the latest pending trade in REAL environment")
    parser.add_argument(
        "--confirm",
        default="",
        help=f"Required for REAL execution. Must exactly equal: {REAL_CONFIRM_TEXT}",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    env = os.environ.copy()
    cmd = [sys.executable, str(WORKFLOW), "execute"]

    if args.real:
        if args.confirm != REAL_CONFIRM_TEXT:
            raise SystemExit(
                f"REAL execution blocked. Re-run with --real --confirm '{REAL_CONFIRM_TEXT}'."
            )
        env["OPENCLAW_FUTU_ALLOW_REAL"] = "YES"
        cmd.append("--execute-real")

    completed = subprocess.run(cmd, env=env)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
