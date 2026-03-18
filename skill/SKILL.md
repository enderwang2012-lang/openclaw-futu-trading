---
name: openclaw-futu-trading
description: Build, verify, and operate OpenClaw workflows that use FUTU OpenD and `futu-api` for market data, account inspection, pending-order approval, and guarded order placement. Use when Codex needs to integrate OpenClaw with FUTU, create or update a FUTU trading adapter, validate OpenD connectivity, inspect accounts or positions, or prepare simulation-first automated trading flows with explicit safeguards around real-money orders.
---

# OpenClaw FUTU Trading

Use this skill to connect an OpenClaw-style agent workflow to FUTU OpenD safely.

## Repo Layout

- `scripts/`: reusable FUTU API helpers
- `references/`: integration notes for adapter design
- `../executor/`: conversation-driven execution gateway and approval workflow

## Quick Start

1. Verify that FUTU OpenD is running and logged in.
2. Run [`scripts/futu_smoke_test.py`](./scripts/futu_smoke_test.py) before editing project code.
3. Use [`scripts/futu_client.py`](./scripts/futu_client.py) as the minimal adapter for quotes, accounts, positions, orders, and guarded order placement.
4. For OpenClaw-native analysis flows, send the final structured trade instruction to [`../executor/executor.py`](../executor/executor.py) instead of rebuilding broker logic.
5. Keep all new automation on `SIMULATE` or dry-run until the user explicitly asks for real trading.

## Workflow

### 1. Verify connectivity first

Run the smoke test before making integration changes:

```bash
python3 scripts/futu_smoke_test.py --env SIMULATE
python3 scripts/futu_smoke_test.py --env REAL
```

If `REAL` fails with an agreement or permission error, stop and tell the user to complete the required FUTU confirmation in the app or web flow, then restart OpenD.

### 2. Reuse the bundled adapter

Prefer importing or adapting [`scripts/futu_client.py`](./scripts/futu_client.py) instead of rewriting FUTU access from scratch.

It already provides:
- OpenD connection management
- global state lookup
- account discovery
- account info lookup
- positions lookup
- order lookup
- quote snapshot lookup
- guarded `place_order` with `dry_run=True` by default

Keep the adapter thin. Project-specific orchestration should live in the user's repository, not inside the skill.

### 3. Keep real orders explicitly gated

Treat real-money execution as high risk.

Rules:
- Default to `SIMULATE` for new workflows.
- Default to dry-run for all order submission examples.
- Do not enable real orders unless the user explicitly asks for it.
- Require a visible safety gate for any REAL order path.
- Preserve clear logs or structured output that show symbol, quantity, side, and environment.

### 4. Shape the OpenClaw integration

When integrating with OpenClaw or a similar agent framework, expose small deterministic operations:
- `get_global_state`
- `list_accounts`
- `get_account_info`
- `get_positions`
- `get_orders`
- `get_snapshot`
- `place_order`

Return JSON-serializable dictionaries and lists so the agent layer can reason over tool output cleanly.

For the thinnest production path, have OpenClaw generate a JSON order plan and pass it to the executor:

```bash
python3 executor/executor.py \
  --input-json '{"symbol":"HK.00001","side":"BUY","qty":1,"qty_unit":"LOT","price_mode":"ASK","market":"HK","env":"SIMULATE"}'
```

### 5. Remote-control conversation flow

For a human talking directly to OpenClaw, prefer this flow:

1. OpenClaw analyzes the idea in natural language.
2. If the conclusion is `NO_TRADE`, stop and do not create a pending order.
3. If the conclusion is to trade, OpenClaw creates a pending order with [`../executor/prepare_trade.py`](../executor/prepare_trade.py).
4. OpenClaw asks for a single confirmation.
5. After the user confirms, OpenClaw executes [`../executor/approve_latest_trade.py`](../executor/approve_latest_trade.py).

For REAL execution:

```bash
python3 executor/approve_latest_trade.py --real --confirm "EXECUTE REAL TRADE"
```

Behavior rules:
- If OpenClaw analysis returns `NO_TRADE` or zero quantity, stop and do not create a pending order.
- Never execute a REAL order without an explicit user confirmation message in the same conversation turn.
- Keep risk controls hard-coded in the execution layer, not only in prompts.

### 6. Validate with safe commands

Use representative read-only checks after any change:

```bash
python3 scripts/futu_client.py --env REAL state
python3 scripts/futu_client.py --env REAL accounts
python3 scripts/futu_client.py --env REAL positions
python3 scripts/futu_client.py --env REAL snapshot HK.00001 US.AAPL
python3 scripts/futu_client.py --env SIMULATE place-order --code HK.00001 --price 60 --qty 100 --side BUY
```

The last command is still dry-run unless `--execute` is added.

## Integration Notes

- Use [`references/integration-notes.md`](./references/integration-notes.md) when you need project wiring guidance or example wrapper shapes.
- If the user already has a codebase, preserve its conventions and inject the FUTU adapter behind a narrow interface.
- If the user asks for a new OpenClaw skill or tool, package the adapter and the safety rules together so future runs stay simulation-first.

## Resource Map

- [`scripts/futu_smoke_test.py`](./scripts/futu_smoke_test.py): one-shot connectivity and account/position verification
- [`scripts/futu_client.py`](./scripts/futu_client.py): reusable Python adapter and CLI
- [`references/integration-notes.md`](./references/integration-notes.md): concise implementation guidance for OpenClaw-facing wrappers
- [`../executor/executor.py`](../executor/executor.py): thin execution gateway for OpenClaw-generated trade instructions
- [`../executor/workflow.py`](../executor/workflow.py): pending-order approval workflow
