# Developer Guide

## Local Setup

```bash
git clone https://github.com/SergeDubovsky/neewer-cli.git
cd neewer-cli
python -m pip install -U pip
python -m pip install ".[dev]"
```

Optional TUI dependency:

```bash
python -m pip install -e ".[tui]"
```

## Validation

```bash
python -m ruff check .
python -m pytest -q
python -m build
python -m twine check dist/*
```

## Entrypoints

- `neewer_cli.py`: runtime command dispatcher and BLE operations
- `neewer_config_cli.py`: wizard configuration editor
- `neewer_config_tui.py`: Textual tree configuration editor

## Test Focus

- Keep parser and validation helpers covered with unit tests.
- For config editors, validate both parse helpers and UI mount/load behavior.
- Preserve backward compatibility in config schema and preset semantics.
