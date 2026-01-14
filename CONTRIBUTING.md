# Contributing to Minimal POS (v2)

Thank you for your interest in contributing! This document describes the preferred workflow, coding standards, and guidelines to help your contribution be accepted quickly.

## How to contribute

1. Fork the repository and create a feature branch:
   - Branch name format: `feat/<short-description>` or `fix/<short-description>` or `docs/<short-description>`.
   - Keep each branch focused on a single change.

2. Open a Pull Request (PR) against the `claude` branch (or the branch indicated by maintainers). Describe:
   - What the change does.
   - Why it's needed.
   - Any migration/upgrade steps if relevant.

3. Link related issues (if any) and add tests where applicable.

## Development setup

Recommended workflow:

```bash
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
.\.venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

If you don't have a `requirements.txt` yet, install:
- textual
- pandas
- qrcode
- pillow

Run the TUI locally:
```bash
python pos_tui.py
```

Run the CLI demo:
```bash
python pos_cli_demo.py
```

## Testing

- Use `pytest` for tests (not included yet). Example:
  - Install: `pip install pytest`
  - Run: `pytest tests/`

If you add functionality, please include unit tests that cover the main logic paths (business logic and repos).

## Coding style

- Language: Python 3.8+ (3.10+ recommended)
- Follow PEP8 for formatting.
- Type hints are preferred for public functions and methods.
- Keep UI and business logic separated: changes to UI should not modify `pos_business_logic.py` behavior.

Suggested linters / formatters:
- black
- isort
- flake8

## Commit messages

- Use clear, short subject lines (max ~72 chars) and an optional body.
- Examples:
  - feat: add split payment support
  - fix: handle empty barcode lookup
  - docs: improve README and add examples

## Issues & bug reports

When filing a bug report, include:
- Steps to reproduce
- Expected vs actual behavior
- Traceback or logs (if any)
- Version of Python and installed dependencies
- Screenshots or terminal output (if applicable)

## Feature requests

Propose features via issues. If you want to implement a feature, comment on the issue so others know you're working on it.

## Security

Do not add secrets, API keys, or credentials to the repo. Use environment variables or a secure configuration mechanism for production secrets.

## License

By contributing, you agree that your contributions will be licensed under the repository license (see `LICENSE`).

## Code of Conduct

Be respectful and professional. Treat contributors with kindness. If you'd like, we can add a formal `CODE_OF_CONDUCT.md`.