# neewer-cli

[![CI](https://github.com/SergeDubovsky/neewer-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/SergeDubovsky/neewer-cli/actions/workflows/ci.yml)
[![Release](https://github.com/SergeDubovsky/neewer-cli/actions/workflows/release.yml/badge.svg)](https://github.com/SergeDubovsky/neewer-cli/actions/workflows/release.yml)
[![License: MIT](https://img.shields.io/github/license/SergeDubovsky/neewer-cli)](LICENSE)

Standalone Neewer BLE command-line utility focused on fast and reliable control without a GUI.

## Why This Tool

- CLI-only workflow for scripting and automation.
- Reliability controls for unstable BLE environments (retries, passes, bounded parallelism).
- Fast fixed-rig operation with config-driven `--skip-discovery`.
- Presets, groups, and per-light command overrides keyed by MAC.

## Attribution

This project is based on and derives protocol/model support from:

- **NeewerLite-Python** by **Zach Glenwright**
- https://github.com/taburineagle/NeewerLite-Python

## Requirements

- Python `3.9+`
- Bluetooth adapter with BLE support

The runtime BLE dependency (`bleak`) is installed automatically by package install commands below.

## Installation

Current recommended install (GitHub source):

```bash
# one-time install of pipx
python -m pip install --user pipx
python -m pipx ensurepath

# install neewer-cli from GitHub
pipx install git+https://github.com/SergeDubovsky/neewer-cli.git
```

Alternative user install:

```bash
python -m pip install --user git+https://github.com/SergeDubovsky/neewer-cli.git
```

After install:

```bash
neewer-cli --help
neewer-cli --version
```

PyPI distribution is planned but not yet published.

## Quick Start

```bash
# 1) discover lights
neewer-cli --list

# 2) copy example config to default config path
# Windows (PowerShell/CMD)
copy neewer.example.json %USERPROFILE%\.neewer

# macOS/Linux
cp neewer.example.json ~/.neewer

# 3) run presets
neewer-cli --preset all_on
neewer-cli --preset all_off
neewer-cli --preset key_cct_5600_30
```

## Common Commands

```bash
# turn configured lights on/off quickly
neewer-cli --preset all_on
neewer-cli --preset all_off

# send direct command to specific MACs
neewer-cli --light D2:E2:75:8B:36:45,F8:46:85:EF:47:70 --mode CCT --temp 5600 --bri 30

# fast fixed-rig mode (no scan)
neewer-cli --light group:studio --preset all_on --skip-discovery

# persistent low-latency mode (keep connections open)
neewer-cli --serve --light group:studio --skip-discovery --debug
```

## Configuration

Default config path:

- `~/.neewer` (Windows: `%USERPROFILE%\.neewer`)

Top-level config keys:

- `defaults`: default CLI flags
- `lights`: per-MAC metadata (`name`, `cct_only`, `infinity_mode`, `hw_mac`, optional feature flags)
- `groups`: named MAC sets
- `presets`: reusable command sets
- `presets.<name>.per_light`: per-light command overrides in one run

Optional per-light feature flags in `lights`:

- `supports_status_query`: override model detection for `--status` query commands
- `supports_extended_scene`: override model detection for extended scene payloads

Reference material:

- Example config: [neewer.example.json](neewer.example.json)
- Wiki configuration guide: https://github.com/SergeDubovsky/neewer-cli/wiki/Configuration

## Reliability Tuning

For flaky BLE environments, tune:

- `--scan-attempts`
- `--resolve-timeout` (short BLE handle resolve scan for `--skip-discovery`)
- `--connect-retries`
- `--write-retries`
- `--passes` (adaptive retries for failed lights only)
- `--parallel`

For stable fixed setups, keep `lights` fully defined in config and use `--skip-discovery` to reduce latency.

## Advanced Protocol (Experimental)

Advanced commands are opt-in behind feature flags and still gated by per-model support.

Status query (power/channel):

```bash
neewer-cli --light group:studio --status --enable-status-query --skip-discovery
```

Extended scene arguments (supported models only):

```bash
neewer-cli --light group:studio --mode SCENE --scene 12 --bri 40 \
  --scene-hue-min 20 --scene-hue-max 240 --scene-speed 7 \
  --enable-extended-scene
```

If auto-detection is wrong for a specific light, set `supports_status_query` or
`supports_extended_scene` for that MAC in config.

### Serve Mode

`--serve` keeps BLE connections open and accepts commands from stdin:

```bash
neewer-cli --serve --light group:studio --skip-discovery --debug
```

Interactive commands:

- `on`
- `off`
- `cct <temp> <bri> [gm]`
- `hsi <hue> <sat> <bri>`
- `scene <effect> <bri>`
- `preset <name>`
- `help`
- `exit`

## Security

- Private vulnerability reporting is enabled.
- Code scanning (CodeQL) is enabled for `python` and `actions`.
- Secret scanning and push protection are enabled.

Please report security issues privately per [SECURITY.md](SECURITY.md).

## Releases

GitHub releases include wheel and source distribution artifacts:

- https://github.com/SergeDubovsky/neewer-cli/releases

Maintainer release flow:

1. Update `version` in `pyproject.toml`.
2. Run local checks (`ruff`, `pytest`, `build`, `twine check`).
3. Commit and push to `main`.
4. Tag and push (`git tag vX.Y.Z && git push origin vX.Y.Z`).
5. Release workflow publishes artifacts to GitHub Releases.

## Project Docs

- Wiki home: https://github.com/SergeDubovsky/neewer-cli/wiki
- Developer guide: https://github.com/SergeDubovsky/neewer-cli/wiki/Developer-Guide
- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md)
- Release process: [RELEASING.md](RELEASING.md)
- Security policy: [SECURITY.md](SECURITY.md)
- Support policy: [SUPPORT.md](SUPPORT.md)
- Code of conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

## License

MIT. See [LICENSE](LICENSE).
