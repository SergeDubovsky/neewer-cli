# Configuration

## File Location and Format

- Default config path: `~/.neewer` (Windows: `%USERPROFILE%\.neewer`).
- Supported formats: JSON (`.json`) and YAML (`.yaml` / `.yml`).
- Root object keys:
  - `defaults`
  - `lights`
  - `groups`
  - `presets`

If the default file does not exist, the CLI continues with built-in defaults.

## Precedence Rules

Effective values are applied in this order:

1. Built-in parser defaults
2. `defaults` from config
3. `preset` values from config
4. Explicit CLI flags

CLI flags always win.

## `defaults`

`defaults` maps directly to CLI argument names (hyphen or underscore style is accepted in config keys).

Example:

```json
{
  "defaults": {
    "scan_timeout": 3,
    "scan_attempts": 2,
    "connect_retries": 3,
    "write_retries": 2,
    "passes": 2,
    "parallel": 1,
    "skip_discovery": true
  }
}
```

Useful defaults for reliability:

- `scan_attempts`: `2-4`
- `connect_retries`: `3-4`
- `write_retries`: `2-3`
- `passes`: `2-3`
- `parallel`: `1` when your adapter is unstable under concurrency

## `lights`

Defines static metadata keyed by MAC address.

Supported per-light fields:

- `name`: friendly display name
- `cct_only`: force CCT-only behavior
- `infinity_mode`: protocol mode (`0`, `1`, `2`)
- `hw_mac`: explicit hardware MAC for Infinity payloads (optional)
- `rssi`: optional static value (used only in skip-discovery path display)

Example:

```json
{
  "lights": {
    "D2:E2:75:8B:36:45": {
      "name": "Key",
      "cct_only": false,
      "infinity_mode": 0
    },
    "F8:46:85:EF:47:70": {
      "name": "Fill",
      "cct_only": false,
      "infinity_mode": 0
    }
  }
}
```

## `groups`

Named light selectors that expand into MAC lists.

`groups.<name>` can be either:

- a list of MAC addresses
- a comma-separated string of MAC addresses

Example:

```json
{
  "groups": {
    "studio": [
      "D2:E2:75:8B:36:45",
      "F8:46:85:EF:47:70"
    ]
  }
}
```

Selector examples:

- `--light group:studio`
- `--light group:studio,AA:BB:CC:DD:EE:FF`
- `--light ALL` (or `*`)

## `presets`

Named command sets. A preset can include normal CLI fields and aliases:

- `brightness` -> `bri`
- `saturation` -> `sat`
- `temperature` -> `temp`
- `effect` -> `scene`
- `power` -> `on/off`

Example:

```json
{
  "presets": {
    "all_on": {
      "lights": "group:studio",
      "power": "ON"
    },
    "key_cct_5600_30": {
      "lights": "group:studio",
      "mode": "CCT",
      "temp": 5600,
      "bri": 30,
      "gm": 0
    }
  }
}
```

### Per-light presets

Use `presets.<name>.per_light` to apply different commands in one run.

Example:

```json
{
  "presets": {
    "stream_setup": {
      "per_light": {
        "D2:E2:75:8B:36:45": { "mode": "CCT", "temp": 5600, "bri": 40 },
        "F8:46:85:EF:47:70": { "mode": "CCT", "temp": 5600, "bri": 100 }
      }
    }
  }
}
```

If `--light` is not explicitly passed, per-light preset addresses are used automatically.

## Skip Discovery for Speed

`--skip-discovery` bypasses BLE scanning and connects directly to configured `lights` addresses.

Best practice:

1. Keep a complete `lights` block.
2. Use presets with `lights` or `per_light`.
3. Set `skip_discovery: true` in `defaults` for your stable setup.

This gives the lowest latency and most deterministic behavior.

## Full Example

```json
{
  "defaults": {
    "scan_timeout": 3,
    "scan_attempts": 2,
    "connect_retries": 4,
    "write_retries": 3,
    "passes": 3,
    "parallel": 1,
    "skip_discovery": true
  },
  "lights": {
    "D2:E2:75:8B:36:45": {
      "name": "Key",
      "cct_only": false,
      "infinity_mode": 0
    },
    "F8:46:85:EF:47:70": {
      "name": "Fill",
      "cct_only": false,
      "infinity_mode": 0
    }
  },
  "groups": {
    "studio": ["D2:E2:75:8B:36:45", "F8:46:85:EF:47:70"]
  },
  "presets": {
    "all_on": {
      "lights": "group:studio",
      "power": "ON"
    },
    "all_off": {
      "lights": "group:studio",
      "power": "OFF"
    },
    "key_fill_default": {
      "per_light": {
        "D2:E2:75:8B:36:45": { "mode": "CCT", "temp": 5600, "bri": 40 },
        "F8:46:85:EF:47:70": { "mode": "CCT", "temp": 5600, "bri": 100 }
      }
    }
  }
}
```
