# Integration Notes

## Recommended adapter shape

Use `FutuClient` as the lowest-level integration point. Add one thin wrapper in the target project that converts project-specific config into:
- `host`
- `port`
- `market`
- `env`
- `security_firm`
- `allow_real_orders`

Keep business logic outside the adapter.

## Suggested OpenClaw-facing tool surface

Expose a small set of functions or actions:

```python
from futu_client import FutuClient, OrderRequest


def get_positions(config):
    with FutuClient(**config) as client:
        return client.get_positions()


def place_order(config, code, price, qty, side, dry_run=True):
    with FutuClient(**config) as client:
        return client.place_order(
            OrderRequest(code=code, price=price, qty=qty, side=side),
            dry_run=dry_run,
        )
```

## Safety defaults

- Start with `env="SIMULATE"`.
- Keep `allow_real_orders=False`.
- Require an explicit user-visible switch before passing `--execute` or `dry_run=False`.
- Log every order request before submission.

## Troubleshooting

- Import fails on macOS log paths:
  Run outside restrictive sandboxes or ensure FUTU log directories are writable.
- OpenD connects but trading queries fail:
  Confirm the user has accepted required FUTU agreements and restarted OpenD.
- Account exists but no market access:
  Inspect `trdmarket_auth` from `list_accounts()` and align the configured market.
- Dependency conflicts from `protobuf`:
  Prefer a dedicated virtual environment for FUTU/OpenClaw work.
