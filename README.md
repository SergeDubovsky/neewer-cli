# neewer-cli

[![CI](https://github.com/SergeDubovsky/neewer-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/SergeDubovsky/neewer-cli/actions/workflows/ci.yml)
[![Release](https://github.com/SergeDubovsky/neewer-cli/actions/workflows/release.yml/badge.svg)](https://github.com/SergeDubovsky/neewer-cli/actions/workflows/release.yml)

Standalone Neewer BLE command-line utility focused on fast and reliable control.

## Attribution

This project is based on and derives protocol/model support from:

- **NeewerLite-Python** by **Zach Glenwright**
- https://github.com/taburineagle/NeewerLite-Python

## Requirements

- Python 3.9+
- `bleak`

```bash
pip install bleak
```

## Installation

Recommended for end users:

```bash
# one-time install of pipx
python -m pip install --user pipx
python -m pipx ensurepath

# install from GitHub repo
pipx install git+https://github.com/SergeDubovsky/neewer-cli.git
```

Alternative (local user install):

```bash
pip install --user git+https://github.com/SergeDubovsky/neewer-cli.git
```

After installation, run:

```bash
neewer-cli --help
```

## Quick Start

```bash
# list lights discovered over BLE scan
neewer-cli --list

# copy example config to default config location
copy neewer.example.json %USERPROFILE%\.neewer

# run presets from config
neewer-cli --preset studio_on
neewer-cli --preset studio_off
neewer-cli --preset studio_key_fill_default
```

## Config

Default config path:

- `~/.neewer` (for Windows: `%USERPROFILE%\.neewer`)

Config supports:

- `defaults`: default CLI flags
- `lights`: per-MAC metadata (`name`, `cct_only`, `infinity_mode`, `hw_mac`)
- `groups`: named MAC lists
- `presets`: reusable command sets
- `presets.<name>.per_light`: different commands per MAC in one run

See `neewer.example.json`.

## License

MIT. See `LICENSE`.

## Releases

GitHub releases include wheel/sdist artifacts under `Assets`.

- https://github.com/SergeDubovsky/neewer-cli/releases

Maintainer flow:

1. Bump `version` in `pyproject.toml`.
2. Commit and push to `main`.
3. Tag and push (`git tag vX.Y.Z && git push origin vX.Y.Z`).
4. GitHub Actions runs tests/build and publishes release assets.
