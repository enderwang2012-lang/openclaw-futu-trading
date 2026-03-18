#!/usr/bin/env python3
"""Run an OpenClaw agent to generate a trade proposal, then prepare it for approval."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
WORKFLOW = BASE_DIR / "workflow.py"
PROMPT_TEMPLATE = """请先完成分析，再输出一个自然语言交易提案，严格使用下面字段，每行一个，不要输出别的内容：

股票: <FUTU代码，例如 HK.00700 或 US.NVDA>
操作: <买入 或 卖出>
数量: <港股写 1手 / 2手，美股写 1股 / 2股>
价格: <对手价 / 买一 / 卖一 / 最新价 / 具体限价数字>
市场: <港股 / 美股>
环境: <模拟盘>
备注: <一句短备注>
理由: <一句短理由>

要求：
- 如果建议交易，默认给出最小测试单
- 如果不建议交易，也照样输出上述格式
- 如果不建议交易：
  - 操作写 买入
  - 数量写 0手 或 0股
  - 价格写 最新价
  - 备注写 NO_TRADE
  - 理由写不交易原因
- 股票代码必须使用 FUTU 格式
- 最终答案只能包含这 8 行字段

用户任务：
{task}
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run OpenClaw analysis and auto-prepare a pending FUTU order")
    parser.add_argument("task", help="Natural-language trading analysis request for OpenClaw")
    parser.add_argument("--agent", default="financier", help="OpenClaw agent id")
    parser.add_argument("--thinking", default="medium", help="OpenClaw thinking level")
    parser.add_argument("--timeout", default="600", help="OpenClaw timeout in seconds")
    parser.add_argument("--save-raw", action="store_true", help="Save raw OpenClaw JSON response next to the pending order")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    prompt = PROMPT_TEMPLATE.format(task=args.task)

    result = subprocess.run(
        [
            "openclaw",
            "agent",
            "--agent",
            args.agent,
            "--message",
            prompt,
            "--thinking",
            args.thinking,
            "--timeout",
            args.timeout,
            "--json",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    raw_output = result.stdout
    start = raw_output.find("{")
    if start < 0:
        raise RuntimeError("OpenClaw did not return JSON output")

    payload = json.loads(raw_output[start:])
    text = payload["result"]["payloads"][0]["text"].strip()

    prepare = subprocess.run(
        [
            sys.executable,
            str(WORKFLOW),
            "prepare",
            "--text",
            text,
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    print("OpenClaw 交易提案：")
    print(text)
    print("")
    print(prepare.stdout.strip())

    if args.save_raw:
        raw_dir = BASE_DIR / "pending" / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        target = raw_dir / "latest-openclaw-response.json"
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print("")
        print(f"原始 OpenClaw 返回已保存到: {target}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
