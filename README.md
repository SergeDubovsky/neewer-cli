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

# install from PyPI (preferred once published)
pipx install neewer-cli
```

Alternative before/without PyPI:

```bash
pipx install git+https://github.com/SergeDubovsky/neewer-cli.git
```

After installation, run:

```bash
neewer-cli --help
neewer-cli --version
```

## Quick Start

```bash
# list lights discovered over BLE scan
neewer-cli --list

# copy example config to default config location
# Windows
copy neewer.example.json %USERPROFILE%\.neewer

# macOS/Linux
cp neewer.example.json ~/.neewer

# run presets from config
neewer-cli --preset all_on
neewer-cli --preset all_off
neewer-cli --preset key_cct_5600_30
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

See `neewer.example.json` and the full config reference:

- Wiki config guide: https://github.com/SergeDubovsky/neewer-cli/wiki/Configuration

## License

MIT. See `LICENSE`.

## Project Docs

- Wiki home: https://github.com/SergeDubovsky/neewer-cli/wiki
- Wiki config reference: [docs/wiki/Configuration.md](docs/wiki/Configuration.md)
- Developer guide: [docs/developer-guide.md](docs/developer-guide.md)
- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md)
- Release process: [RELEASING.md](RELEASING.md)
- Security policy: [SECURITY.md](SECURITY.md)
- Support policy: [SUPPORT.md](SUPPORT.md)
- Code of conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

## Releases

GitHub releases include wheel/sdist artifacts under `Assets`.

- https://github.com/SergeDubovsky/neewer-cli/releases

Maintainer flow:

1. Bump `version` in `pyproject.toml`.
2. Commit and push to `main`.
3. Tag and push (`git tag vX.Y.Z && git push origin vX.Y.Z`).
4. GitHub Actions runs tests/build and publishes release assets.
