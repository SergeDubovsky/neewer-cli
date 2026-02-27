# Developer Guide

## Purpose and Scope

`neewer-cli` is a single-file Python CLI focused on:

- deterministic BLE command delivery
- minimal startup overhead
- practical reliability controls for flaky BLE environments

It intentionally avoids GUI and thread-heavy architecture.

## High-Level Flow

Main execution path:

1. `main()` parses CLI args
2. `async_main()` loads config and resolves command
3. discovery path:
   - BLE scan with retries (`discover_with_retries`)
   - or static config path (`--skip-discovery`)
4. connect with retries (`connect_light`)
5. send command for N passes (`send_command_once`)
6. disconnect (`disconnect_light`)

Key reliability controls:

- `scan_attempts`
- `connect_retries`
- `write_retries`
- `passes`
- bounded concurrency via `parallel`

## Data Model

`LightInfo` stores discovered/configured light metadata:

- `name`, `realname`, `address`, `rssi`
- protocol traits: `cct_only`, `infinity_mode`
- runtime state: `client`, `ble_device`, `hw_mac`

`AppConfig` stores runtime behavior knobs from merged CLI/config values.

## Config Merge Semantics (Important)

Order of application in `async_main()`:

1. `load_user_config()`
2. `apply_defaults_from_config()`
3. `apply_preset_from_config()`
4. explicit CLI flags always preserved

This means presets are overrideable per invocation without editing config.

## Protocol and Payload Notes

### Checksums

`tag_checksum(payload)` appends 8-bit checksum used by Neewer packets.

### Temperature Handling

`parse_temp_value()` accepts either:

- protocol-scale values (`56`)
- Kelvin-style values (`5600`) and converts to protocol-scale

### CCT-only lights

For `cct_only` lights, CCT commands are split into two writes:

- brightness packet (`0x82`)
- temperature packet (`0x83`)

HSI/scene commands are rejected for these models.

### Infinity modes

`infinity_mode` drives packet path:

- `0`: classic protocol
- `1`: Infinity protocol with MAC embedded in payload
- `2`: hybrid path for specific newer models

Non-obvious behavior:

- classic non-Infinity CCT packets ignore GM channel intentionally
- Infinity scene mode can include explicit power-cycle packets around effect command for compatibility

## Discovery Strategy

`discover_devices()` tries `BleakScanner.discover(..., return_adv=True)` first, then falls back for older `bleak` signatures.

For speed-critical fixed rigs, `--skip-discovery` uses configured MACs directly, avoiding scan latency.

## Error Handling

All user-facing config/command validation should end as `ConfigError` for clean CLI output.

Recent hardening:

- `build_base_command()` wraps invalid command values as `ConfigError`
- per-light preset command build errors are address-scoped and explicit

## Tests

Tests are in `tests/test_neewer_cli.py` and focus on deterministic logic:

- config normalization/merge behavior
- selector and preset parsing
- payload generation and mode guards
- command send path with fake client

BLE hardware integration tests are intentionally not part of CI.

## CI/Release Workflows

`CI` workflow:

- matrix Python `3.9`-`3.13`
- lint (`ruff`)
- tests (`pytest`)
- build (`python -m build`)
- metadata check (`twine check`)
- install smoke (`python -m neewer_cli --version`)

`Release` workflow:

- tag-triggered and manual-dispatch with explicit `tag`
- runs same quality gates
- uploads wheel + sdist
- publishes GitHub release assets

## Extending the CLI Safely

When adding a new mode or payload behavior:

1. add parser flags
2. implement payload path in `calculate_bytestring()` and/or `build_payload_sequence()`
3. ensure `ConfigError`-based user errors
4. add tests for:
   - normal path
   - invalid inputs
   - model-specific behavior (`cct_only`/Infinity)
5. run full local gate:

```bash
python -m ruff check .
python -m pytest -q
python -m build
python -m twine check dist/*
```
