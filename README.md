# neewer-cli

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

## Quick Start

```bash
# list lights discovered over BLE scan
python neewer_cli.py --list

# copy example config to default config location
copy neewer.example.json %USERPROFILE%\.neewer

# run presets from config
python neewer_cli.py --preset studio_on
python neewer_cli.py --preset studio_off
python neewer_cli.py --preset studio_key_fill_default
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
