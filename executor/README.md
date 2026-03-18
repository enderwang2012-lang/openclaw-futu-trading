# OpenClaw FUTU Executor

Use OpenClaw to analyze the market and produce a trade instruction, then pass that instruction to `executor.py` for validation and execution through FUTU OpenD.

## Instruction shape

```json
{
  "symbol": "HK.00001",
  "side": "BUY",
  "qty": 1,
  "qty_unit": "LOT",
  "price_mode": "ASK",
  "market": "HK",
  "env": "SIMULATE",
  "remark": "OpenClaw test",
  "thesis": "Momentum continuation"
}
```

## Safe preview

```bash
python3 executor.py --input-json '{"symbol":"HK.00001","side":"BUY","qty":1,"qty_unit":"LOT","price_mode":"ASK","market":"HK","env":"SIMULATE"}'
```

## Real execution

```bash
export OPENCLAW_FUTU_ALLOW_REAL=YES
python3 executor.py --execute-real --input-json '{"symbol":"HK.00001","side":"BUY","qty":1,"qty_unit":"LOT","price":60.0,"price_mode":"MANUAL","market":"HK","env":"REAL"}'
```

REAL execution requires both:
- `--execute-real`
- `OPENCLAW_FUTU_ALLOW_REAL=YES`

## Natural-language approval flow

Ask OpenClaw to output a proposal like:

```text
股票: HK.00001
操作: 买入
数量: 1手
价格: 对手价
市场: 港股
环境: 模拟盘
备注: OpenClaw test
理由: 短线动量转强，先做最小测试单。
```

Store it as a pending order:

```bash
python3 workflow.py prepare --text '股票: HK.00001
操作: 买入
数量: 1手
价格: 对手价
市场: 港股
环境: 模拟盘
备注: OpenClaw test
理由: 短线动量转强，先做最小测试单。'
```

Then execute after your approval:

```bash
python3 workflow.py execute
```

## One-command OpenClaw flow

Run OpenClaw analysis and automatically generate a pending order:

```bash
python3 run_openclaw_trade.py "请分析某只港股是否适合做一笔最小测试交易"
```

This command:
- asks the `financier` OpenClaw agent for a fixed 8-line proposal
- parses the proposal
- creates a pending order via `workflow.py prepare`
- prints the approval summary

Approve the latest pending trade:

```bash
python3 approve_latest_trade.py
```

Approve the latest REAL trade:

```bash
python3 approve_latest_trade.py --real --confirm "EXECUTE REAL TRADE"
```

For direct OpenClaw agent use, prepare a trade without multiline shell quoting:

```bash
python3 prepare_trade.py \
  --symbol HK.00001 \
  --side BUY \
  --qty 1手 \
  --price 对手价 \
  --market 港股 \
  --env 模拟盘 \
  --remark OpenClaw-test \
  --thesis "短线动量转强，先做最小测试单"
```
