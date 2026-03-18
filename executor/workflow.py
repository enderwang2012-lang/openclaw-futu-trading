#!/usr/bin/env python3
"""Natural-language proposal workflow for OpenClaw -> FUTU execution.

Flow:
1. OpenClaw outputs a human-readable proposal in a fixed field format.
2. `workflow.py prepare` parses it, stores a pending order, and prints a summary.
3. After user approval, `workflow.py execute` submits the stored order.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from executor import ExecutionError, main as executor_main  # type: ignore


BASE_DIR = Path(__file__).resolve().parent
PENDING_DIR = BASE_DIR / "pending"
LATEST_FILE = PENDING_DIR / "latest.json"


FIELD_MAP = {
    "股票": "symbol",
    "代码": "symbol",
    "操作": "side",
    "数量": "qty",
    "价格": "price_text",
    "市场": "market",
    "环境": "env",
    "备注": "remark",
    "理由": "thesis",
}


def ensure_pending_dir() -> None:
    PENDING_DIR.mkdir(parents=True, exist_ok=True)


def clear_latest_if_exists() -> None:
    if LATEST_FILE.exists():
        LATEST_FILE.unlink()


def read_text(args: argparse.Namespace) -> str:
    if args.text:
        return args.text
    if args.file:
        return Path(args.file).read_text(encoding="utf-8")
    raise ExecutionError("Provide --text or --file")


def parse_lines(text: str) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r"^([^:：]+)\s*[:：]\s*(.+)$", line)
        if not match:
            continue
        key = match.group(1).strip()
        value = match.group(2).strip()
        mapped = FIELD_MAP.get(key)
        if mapped:
            parsed[mapped] = value
    return parsed


def normalize_side(value: str) -> str:
    upper = value.strip().upper()
    if upper in {"BUY", "买入", "做多"}:
        return "BUY"
    if upper in {"SELL", "卖出", "SELL_SHORT", "减仓"}:
        return "SELL"
    raise ExecutionError(f"Unsupported side: {value}")


def normalize_market(value: str) -> str:
    mapping = {
        "港股": "HK",
        "HK": "HK",
        "美股": "US",
        "US": "US",
        "A股": "CN",
        "CN": "CN",
    }
    result = mapping.get(value.strip().upper(), mapping.get(value.strip(), None))
    if result:
        return result
    raise ExecutionError(f"Unsupported market: {value}")


def normalize_env(value: str) -> str:
    mapping = {
        "模拟": "SIMULATE",
        "模拟盘": "SIMULATE",
        "SIMULATE": "SIMULATE",
        "实盘": "REAL",
        "真实": "REAL",
        "REAL": "REAL",
    }
    result = mapping.get(value.strip().upper(), mapping.get(value.strip(), None))
    if result:
        return result
    raise ExecutionError(f"Unsupported env: {value}")


def normalize_qty(value: str) -> tuple[float, str]:
    text = value.strip().lower().replace(" ", "")
    if text.endswith("手"):
        count = float(text[:-1])
        return count, "LOT"
    if text.endswith("张"):
        count = float(text[:-1])
        return count, "CONTRACT"
    if text.endswith("股"):
        count = float(text[:-1])
        return count, "SHARE"
    return float(text), "SHARE"


def normalize_price(price_text: str, market: str, symbol: str, qty_value: float) -> Dict[str, object]:
    text = price_text.strip().lower()
    if text in {"ask", "对手价", "卖一", "买入对手价"}:
        return {"price": None, "price_mode": "ASK"}
    if text in {"bid", "买一", "卖出对手价"}:
        return {"price": None, "price_mode": "BID"}
    if text in {"last", "最新价", "现价"}:
        return {"price": None, "price_mode": "LAST"}
    return {"price": float(price_text), "price_mode": "MANUAL"}


def convert_to_instruction(parsed: Dict[str, str]) -> Dict[str, object]:
    required = ["symbol", "side", "qty", "price_text", "market", "env"]
    missing = [key for key in required if key not in parsed]
    if missing:
        raise ExecutionError(f"Missing required fields: {', '.join(missing)}")

    market = normalize_market(parsed["market"])
    raw_qty, qty_unit = normalize_qty(parsed["qty"])
    symbol = parsed["symbol"].strip().upper()
    qty = raw_qty

    pricing = normalize_price(parsed["price_text"], market, symbol, raw_qty)

    return {
        "symbol": symbol,
        "side": normalize_side(parsed["side"]),
        "qty": qty,
        "qty_unit": qty_unit,
        "price": pricing["price"],
        "price_mode": pricing["price_mode"],
        "market": market,
        "env": normalize_env(parsed["env"]),
        "order_type": "NORMAL",
        "remark": parsed.get("remark", "OpenClaw proposal"),
        "thesis": parsed.get("thesis", ""),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_text": parsed,
    }


def maybe_expand_lot_quantity(instruction: Dict[str, object]) -> Dict[str, object]:
    # Defer expansion to execution time by querying current lot size using executor.
    # Here we keep a companion field so execute can convert lots -> shares.
    return instruction


def save_pending(instruction: Dict[str, object]) -> Path:
    ensure_pending_dir()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = PENDING_DIR / f"{timestamp}.json"
    target.write_text(json.dumps(instruction, ensure_ascii=False, indent=2), encoding="utf-8")
    LATEST_FILE.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def is_no_trade(instruction: Dict[str, object]) -> bool:
    remark = str(instruction.get("remark", "")).strip().upper()
    qty = float(instruction.get("qty", 0) or 0)
    return remark == "NO_TRADE" or qty <= 0


def load_pending(path: Optional[str]) -> Dict[str, object]:
    target = Path(path) if path else LATEST_FILE
    if not target.exists():
        raise ExecutionError("No pending order found. Run `prepare` first.")
    return json.loads(target.read_text(encoding="utf-8"))


def present_summary(instruction: Dict[str, object], path: Path) -> None:
    qty = instruction["qty"]
    qty_text = f"{qty}手" if instruction.get("qty_unit") == "LOT" else str(qty)
    print("已创建待执行交易单：")
    print(f"- 文件: {path}")
    print(f"- 股票: {instruction['symbol']}")
    print(f"- 操作: {instruction['side']}")
    print(f"- 数量: {qty_text}")
    print(f"- 价格模式: {instruction['price_mode']}")
    print(f"- 环境: {instruction['env']}")
    print(f"- 备注: {instruction.get('remark')}")
    print("")
    print("确认后执行：")
    print("python3 workflow.py execute")


def cmd_prepare(args: argparse.Namespace) -> int:
    text = read_text(args)
    parsed = parse_lines(text)
    instruction = maybe_expand_lot_quantity(convert_to_instruction(parsed))
    if is_no_trade(instruction):
        clear_latest_if_exists()
        print("本次分析结果为不交易，已自动终止，不生成待执行单。")
        print(f"- 股票: {instruction['symbol']}")
        print(f"- 备注: {instruction.get('remark')}")
        print(f"- 理由: {instruction.get('thesis')}")
        return 0
    path = save_pending(instruction)
    present_summary(instruction, path)
    return 0


def build_executor_payload(instruction: Dict[str, object]) -> Dict[str, object]:
    payload = dict(instruction)
    payload.pop("created_at", None)
    payload.pop("source_text", None)
    return payload


def cmd_execute(args: argparse.Namespace) -> int:
    instruction = load_pending(args.file)
    if is_no_trade(instruction):
        clear_latest_if_exists()
        raise ExecutionError("Latest pending item is NO_TRADE and has been cleared. Run analysis again.")
    payload = build_executor_payload(instruction)

    argv = [
        "executor.py",
        "--input-json",
        json.dumps(payload, ensure_ascii=False),
    ]
    if args.execute_real:
        argv.append("--execute-real")

    import sys
    old_argv = sys.argv
    try:
        sys.argv = argv
        return executor_main()
    finally:
        sys.argv = old_argv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenClaw FUTU approval workflow")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Parse a natural-language trade proposal and store it as pending")
    prepare.add_argument("--text", help="Proposal text")
    prepare.add_argument("--file", help="Proposal file path")

    execute = subparsers.add_parser("execute", help="Execute the latest pending trade proposal")
    execute.add_argument("--file", help="Pending JSON file path")
    execute.add_argument("--execute-real", action="store_true", help="Actually place the REAL order")

    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "prepare":
        return cmd_prepare(args)
    if args.command == "execute":
        return cmd_execute(args)
    raise ExecutionError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ExecutionError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(1)
