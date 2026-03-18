# Contributing

Thanks for contributing.

## Before Opening a PR

- Keep the executor simulation-first by default.
- Do not weaken REAL-order safety gates.
- Do not add machine-specific absolute paths.
- Do not commit local state such as pending orders, `.env`, or account data.
- Prefer small, reviewable changes.

## Development Checklist

1. Verify FUTU OpenD connectivity with the smoke test.
2. Test executor changes with `SIMULATE` first.
3. Keep risk controls in code, not only in prompts or documentation.
4. Update docs when behavior changes.

## Pull Request Notes

- Explain the user-facing behavior change.
- Call out any changes to risk limits or execution conditions.
- Mention what you tested and in which environment.

## Security

If you find a safety issue in the execution path, avoid publishing exploit details in a public issue. Share a concise repro and impact summary privately with the maintainer first.
