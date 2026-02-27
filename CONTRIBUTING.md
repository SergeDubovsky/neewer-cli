# Contributing

Thanks for contributing to `neewer-cli`.

## Local Setup

```bash
git clone https://github.com/SergeDubovsky/neewer-cli.git
cd neewer-cli
python -m pip install -U pip
python -m pip install ".[dev]"
```

## Run Checks

```bash
python -m ruff check .
python -m pytest -q
python -m build
python -m twine check dist/*
```

## Scope

- Keep changes focused and testable.
- Add/adjust tests for logic changes.
- For BLE behavior changes, prefer preserving compatibility with existing Neewer models.
- Use PRs against `main` (direct pushes should be avoided for normal changes).

## Developer Docs

- [docs/developer-guide.md](docs/developer-guide.md)
- [docs/wiki/Configuration.md](docs/wiki/Configuration.md)

## Attribution

This project is derived from NeewerLite-Python by Zach Glenwright.
Please preserve attribution and licensing metadata when changing related code.
